"""Filtered Parquet reads for the Trade555 validated layer."""

from datetime import datetime

import pyarrow.compute as pc
import pyarrow.dataset as ds


def straddling_groups(fragment: ds.ParquetFileFragment, cutoff: datetime) -> int:
    """Count crossing row groups from timestamp footer statistics only."""
    fragment.ensure_complete_metadata()
    footer = fragment.metadata
    column = footer.schema.names.index("ts")
    total = 0
    for index in range(footer.num_row_groups):
        bounds = footer.row_group(index).column(column).statistics
        if bounds is not None and bounds.has_min_max:
            total += int(bounds.min < cutoff <= bounds.max)
    return total


def price_batches(
    fragment: ds.ParquetFileFragment, *, columns: list[str],
    predicate: ds.Expression, cutoff: datetime,
):
    """Yield only pre-cutoff rows, including when a row group spans the cutoff."""
    selected = list(dict.fromkeys(["ts", *columns]))
    for batch in fragment.to_batches(
        columns=selected, filter=predicate & (ds.field("ts") < cutoff),
        batch_size=65_536, use_threads=False,
    ):
        batch = batch.filter(pc.less(batch["ts"], cutoff))
        if batch.num_rows:
            yield batch.select(columns)
