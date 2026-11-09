"""Export only the fields required by the independent Monte Carlo add-on."""

from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from atr_breakout.contract_v1 import BAR_MINUTES
from atr_breakout.data.partitions import MARKET_ZONES
from atr_breakout.trade_export import RETURN_COLUMNS, TRADE_FILENAME

PUBLIC_FIELDS = ("market", "window", "case", "benchmark", "seed", "status")
SCHEMA = pa.schema([
    ("market", pa.string()), ("window", pa.string()), ("case", pa.string()),
    ("benchmark", pa.string()), ("seed", pa.int64()), ("status", pa.string()),
    ("day_index", pa.int32()), ("r", pa.float64()),
])
DATE_FIELDS = ("market", "window", "signal_ts_utc")
STUDY_WINDOWS = pa.array(["dev", "oos"])
CASES = pa.array(list(RETURN_COLUMNS))


def _market_dates(batch):
    # The trade file stores the signal bar close. Window assignment uses its open.
    opened = pc.subtract(batch["signal_ts_utc"], pa.scalar(timedelta(minutes=BAR_MINUTES)))
    if opened.null_count:
        raise ValueError("Every signal needs a timestamp to derive its trading day")
    for market in pc.unique(batch["market"]).to_pylist():
        key = "FX_GOLD" if market == "FXGOLD" else market
        if key not in MARKET_ZONES:
            raise ValueError("Unrecognized trade market")
        mask = pc.equal(batch["market"], market)
        local = pc.local_timestamp(opened.filter(mask).cast(pa.timestamp("us", tz=MARKET_ZONES[key])))
        yield market, mask, local.cast(pa.date32())


def _day_orders(parquet):
    dates = {}
    for batch in parquet.iter_batches(columns=list(DATE_FIELDS)):
        if pc.any(pc.equal(batch["window"], "holdout")).as_py():
            raise ValueError("Anonymised export refuses files containing holdout rows")
        if not pc.all(pc.is_in(batch["window"], value_set=STUDY_WINDOWS)).as_py():
            raise ValueError("Expected dev or oos trade rows")
        for market, _, days in _market_dates(batch):
            dates.setdefault(market, set()).update(pc.unique(days).to_pylist())
    return {market: pa.array(sorted(days), type=pa.date32()) for market, days in dates.items()}


def _export_batch(batch, orders):
    if not pc.all(pc.is_in(batch["case"], value_set=CASES)).as_py():
        raise ValueError("Unrecognized trade cost case")
    days = pa.nulls(batch.num_rows, type=pa.int32())
    for market, mask, dates in _market_dates(batch):
        days = pc.replace_with_mask(days, mask, pc.index_in(dates, value_set=orders[market]))

    returns = pa.nulls(batch.num_rows, type=pa.float64())
    for case, column in RETURN_COLUMNS.items():
        taken = pc.and_(pc.equal(batch["case"], case), pc.equal(batch["status"], "TAKEN"))
        returns = pc.if_else(taken, batch[column], returns)
    return pa.RecordBatch.from_arrays(
        [batch[name] for name in PUBLIC_FIELDS] + [days, returns], schema=SCHEMA,
    )


def export_anon(run: Path, out: Path) -> None:
    """Scan twice for dense date indices and publish an allowlisted Parquet file."""
    if out.exists():
        raise FileExistsError(out)
    with pq.ParquetFile(run / TRADE_FILENAME) as parquet:
        orders = _day_orders(parquet)
        with TemporaryDirectory(dir=out.parent) as temporary:
            path = Path(temporary) / "anon.parquet"
            with path.open("xb") as output:
                path.chmod(0o600)
                with pq.ParquetWriter(output, SCHEMA, compression="zstd") as writer:
                    columns = [*PUBLIC_FIELDS, "signal_ts_utc", *RETURN_COLUMNS.values()]
                    for batch in parquet.iter_batches(columns=columns):
                        writer.write_batch(_export_batch(batch, orders))
            out.hardlink_to(path)
