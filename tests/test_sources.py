"""The graph against its sources, as recorded by experiments/verify_sources.py in evidence/sources-check.json."""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_every_quoted_obligation_is_found_word_for_word_in_its_licence_text() -> None:
    result = json.loads((ROOT / "evidence" / "sources-check.json").read_text(encoding="utf-8"))["quotes"]
    with (ROOT / "sources" / "obligations.csv").open(encoding="utf-8", newline="") as handle:
        table = list(csv.DictReader(handle))
    assert result["obligations"] == len(table) == 41
    assert result["found"] == 41 and result["missing"] == []
    assert {s["url"] for s in result["sources"]} == {row["source"] for row in table}


def test_every_lineage_edge_on_the_evaluation_models_paths_matches_the_live_hub_card() -> None:
    result = json.loads((ROOT / "evidence" / "sources-check.json").read_text(encoding="utf-8"))["lineage"]
    assert result["models"] == 21
    assert result["match"] == result["edges"] == 34 and result["differ"] == []


def test_the_coverage_figures_are_those_of_the_committed_graph() -> None:
    import relate

    from pedigree import stats

    recorded = json.loads((ROOT / "evidence" / "stats.json").read_text(encoding="utf-8"))["coverage"]
    conn = relate.connect(str(ROOT / "pedigree.rl"), read_only=True)
    try:
        assert stats.coverage(conn) == recorded
    finally:
        conn.close()
    assert (recorded["models"], recorded["traced_on_every_branch"]) == (213_928, 205_775)
