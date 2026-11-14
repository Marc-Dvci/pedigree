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
    return sorted(p for p in fs.ls(root, detail=False) if str(p).endswith(".parquet"))


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
