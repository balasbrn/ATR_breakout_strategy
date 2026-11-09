"""Write the private cumulative per-signal Parquet artifact."""

from contextlib import contextmanager
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from atr_breakout.core.bars import BAR_SIZE

TRADE_FILENAME = "trades.parquet"
RETURN_COLUMNS = {"gross": "r_gross", "base": "r_net_base", "stress": "r_net_stress"}
UTC = pa.timestamp("us", tz="UTC")
TRADE_SCHEMA = pa.schema([
    ("trade_id", pa.string()), ("market", pa.string()), ("symbol", pa.string()),
    ("window", pa.string()), ("case", pa.string()),
    ("signal_ts_utc", UTC), ("entry_ts_utc", UTC), ("exit_ts_utc", UTC),
    ("direction", pa.string()), ("status", pa.string()), ("exit_reason", pa.string()),
    ("one_r_price", pa.float64()), ("r_gross", pa.float64()),
    ("r_net_base", pa.float64()), ("r_net_stress", pa.float64()),
    ("crosses_overnight", pa.bool_()), ("atr_rank_prev", pa.float64()),
    ("impulse_atr", pa.float64()), ("benchmark", pa.string()), ("seed", pa.int64()),
])
BATCH_SIZE = 2048


class TradeExport:
    def __init__(self, market, writer):
        self.market = "FXGOLD" if market == "FX_GOLD" else market
        self.writer = writer
        self.count = 0
        self.rows = []
        self._frame = None
        self._columns = {}

    def append_previous(self, previous):
        if previous.is_file():
            with pq.ParquetFile(previous) as parquet:
                if not parquet.schema_arrow.equals(TRADE_SCHEMA):
                    raise ValueError("Previous trades.parquet schema does not match")
                for batch in parquet.iter_batches(batch_size=BATCH_SIZE):
                    self.writer.write_batch(batch)
                    self.count += batch.num_rows

    def record(self, symbol, bars, result, *, case, window, benchmark=None, seed=None):
        if self._frame is not bars:
            self._frame = bars
            self._columns = {key: bars[key].array for key in ("ts_utc", "open", "close", "atr", "atr_rank_30d")}
        columns = self._columns
        index = result.signal_bar
        timestamps = columns["ts_utc"]
        trade = result.trade
        prior_rank = columns["atr_rank_30d"][index - 1] if index else None
        prior_atr = columns["atr"][index - 1] if index else None
        rank = float(prior_rank) if pd.notna(prior_rank) else None
        impulse = (
            float(result.direction * (columns["close"][index] - columns["open"][index]) / prior_atr)
            if pd.notna(prior_atr) and prior_atr > 0 else None
        )
        self.count += 1
        row = {
            "trade_id": f"{self.market}:{self.count}", "market": self.market, "symbol": symbol,
            "case": case, "window": window, "signal_ts_utc": timestamps[index] + BAR_SIZE,
            "entry_ts_utc": timestamps[trade.entry_bar] if trade else None,
            "exit_ts_utc": timestamps[trade.exit_bar] + BAR_SIZE if trade else None,
            "direction": "LONG" if result.direction == 1 else "SHORT", "status": result.status,
            "exit_reason": trade.exit_reason if trade else None,
            "one_r_price": trade.one_r_price if trade else None,
            "crosses_overnight": trade.crosses_overnight if trade else None,
            "atr_rank_prev": rank, "impulse_atr": impulse, "benchmark": benchmark, "seed": seed,
        }
        if trade:
            row[RETURN_COLUMNS[case]] = trade.r_gross if case == "gross" else trade.r_net
        self.rows.append(row)
        if len(self.rows) >= BATCH_SIZE:
            self.flush()

    def flush(self):
        if self.rows:
            self.writer.write_table(pa.Table.from_pylist(self.rows, schema=TRADE_SCHEMA))
            self.rows.clear()


@contextmanager
def write_trade_export(directory: Path, market: str, *, append: bool):
    """Build privately, then replace the artifact atomically after success."""
    target = directory / TRADE_FILENAME
    with TemporaryDirectory(dir=directory.parent) as temporary:
        path = Path(temporary) / TRADE_FILENAME
        with path.open("xb") as output:
            path.chmod(0o600)
            with pq.ParquetWriter(output, TRADE_SCHEMA, compression="zstd") as writer:
                export = TradeExport(market, writer)
                if append:
                    export.append_previous(target)
                yield export
                export.flush()
        path.replace(target)


def trade_digest(directory: Path) -> str:
    with (directory / TRADE_FILENAME).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()
