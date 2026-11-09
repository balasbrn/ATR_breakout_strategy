from datetime import datetime

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from atr_breakout.anon_export import export_anon
from atr_breakout.trade_export import TRADE_SCHEMA


def test_export_indexes_signal_bar_date_separately_for_each_market(tmp_path):
    source = tmp_path / "trades.parquet"
    rows = [
        ("CRYPTO", "2022-01-02T00:15:00+00:00"),
        ("CRYPTO", "2022-01-02T00:00:00+00:00"),
        ("US", "2022-01-02T00:15:00+00:00"),
        ("US", "2022-01-02T05:15:00+00:00"),
    ]
    pq.write_table(pa.Table.from_pylist([
        {"market": market, "window": "oos", "case": "base", "status": "TAKEN",
         "signal_ts_utc": datetime.fromisoformat(stamp), "r_net_base": 0.5}
        for market, stamp in rows
    ], schema=TRADE_SCHEMA), source, row_group_size=1)
    out = tmp_path / "anon.parquet"
    export_anon(tmp_path, out)
    result = pq.read_table(out)
    assert result["day_index"].to_pylist() == [1, 0, 0, 1]
    assert result["r"].to_pylist() == [0.5] * 4


def test_export_refuses_holdout_even_if_skipped_s8(tmp_path):
    pq.write_table(pa.Table.from_pylist([
        {"window": "holdout", "status": "SKIPPED_GAP"},
    ], schema=TRADE_SCHEMA), tmp_path / "trades.parquet")
    out = tmp_path / "anon.parquet"
    with pytest.raises(ValueError, match="refuses files containing holdout"):
        export_anon(tmp_path, out)
    assert not out.exists()
