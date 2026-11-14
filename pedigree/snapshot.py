"""Read one pinned snapshot of `librarian-bots/model_cards_with_metadata` (the Hub's model cards, re-published daily).

Only the columns lineage needs are read, with HTTP range requests: the card text, which is most of the 1.6 GB, is
never downloaded. The revision is a dataset commit, so a rebuild reads the same rows.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

DATASET = "librarian-bots/model_cards_with_metadata"
COLUMNS = ["modelId", "tags", "downloads", "likes", "createdAt", "library_name", "pipeline_tag"]


def shard_paths(revision: str) -> list[str]:
    from huggingface_hub import HfFileSystem

    fs = HfFileSystem()
    root = f"datasets/{DATASET}@{revision}/data"
    return sorted(str(p) for p in fs.ls(root, detail=False) if str(p).endswith(".parquet"))


def read_rows(revision: str, batch_rows: int = 50_000) -> Iterator[dict[str, Any]]:
    """Every row of the snapshot, the lineage columns only."""
    import pyarrow.parquet as pq
    from huggingface_hub import HfFileSystem

    fs = HfFileSystem()
    for path in shard_paths(revision):
        with fs.open(path, "rb", block_size=8 * 1024 * 1024) as handle:
            parquet = pq.ParquetFile(handle)
            for batch in parquet.iter_batches(batch_size=batch_rows, columns=COLUMNS):
                yield from batch.to_pylist()


def read_cache(path: str) -> Iterator[dict[str, Any]]:
    """The same rows from a local Parquet file that holds only the lineage columns (written by `save_cache`)."""
    import pyarrow.parquet as pq

    parquet = pq.ParquetFile(path)
    for batch in parquet.iter_batches(batch_size=50_000, columns=COLUMNS):
        yield from batch.to_pylist()


def save_cache(revision: str, path: str) -> int:
    """Copy the lineage columns of a pinned snapshot into one local Parquet file."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    from huggingface_hub import HfFileSystem

    fs = HfFileSystem()
    tables = []
    for shard in shard_paths(revision):
        with fs.open(shard, "rb", block_size=8 * 1024 * 1024) as handle:
            tables.append(pq.ParquetFile(handle).read(columns=COLUMNS))
    table = pa.concat_tables(tables)
    pq.write_table(table, path)
    return int(table.num_rows)
