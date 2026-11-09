from datetime import datetime, timezone

import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq
import pytest

from atr_breakout.data.validated_parquet import price_batches, straddling_groups


@pytest.mark.parametrize("row_group_size", [1, 2])
def test_study_price_scan_excludes_reserved_rows_s8(tmp_path, row_group_size):
    path = tmp_path / "bars.parquet"
    cutoff = datetime(2023, 1, 1, tzinfo=timezone.utc)
    pq.write_table(pa.table({
        "ts": pa.array([datetime(2022, 12, 31, 23, 59, tzinfo=timezone.utc), cutoff],
                       type=pa.timestamp("us", tz="UTC")),
        "close": [1.0, 2.0],
    }), path, row_group_size=row_group_size)
    fragment = next(ds.dataset(path).get_fragments())
    batches = list(price_batches(fragment, columns=["close"], predicate=ds.scalar(True), cutoff=cutoff))
    assert pa.Table.from_batches(batches)["close"].to_pylist() == [1.0]
    assert straddling_groups(fragment, cutoff) == row_group_size - 1


def test_batch_mask_defends_against_unfiltered_decoder_s8():
    cutoff = datetime(2023, 1, 1, tzinfo=timezone.utc)

    class Unfiltered:
        def to_batches(self, *, columns, **kwargs):
            assert "filter" in kwargs
            batch = pa.record_batch({
                "ts": [datetime(2022, 12, 31, tzinfo=timezone.utc), cutoff],
                "close": [1, 2],
            })
            yield batch.select(columns)

    batches = list(price_batches(Unfiltered(), columns=["close"], predicate=ds.scalar(True), cutoff=cutoff))
    assert batches[0]["close"].to_pylist() == [1]
