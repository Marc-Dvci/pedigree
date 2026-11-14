"""Per-model checks on a small lineage built with the real builder into a temporary .rl file."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import relate

from pedigree import checks
from pedigree.build import build
from pedigree.lineage import descendants, parse_rows

ROOT = Path(__file__).resolve().parents[1]
ROWS = [
    {"modelId": "meta-llama/Llama-3.1-8B", "tags": ["license:llama3.1"]},
    {"modelId": "meta-llama/Llama-3.1-8B-Instruct", "tags": ["base_model:finetune:meta-llama/Llama-3.1-8B", "license:llama3.1"]},
    {"modelId": "fan/Hermes-ft", "tags": ["base_model:finetune:meta-llama/Llama-3.1-8B-Instruct", "license:apache-2.0"]},
    {"modelId": "fan/Llama-3.1-Hermes", "tags": ["base_model:finetune:meta-llama/Llama-3.1-8B-Instruct", "license:llama3.1"]},
    {"modelId": "quant/Hermes-ft-GGUF", "tags": ["base_model:quantized:fan/Hermes-ft"]},
    {"modelId": "Qwen/Qwen2.5-3B", "tags": ["license:other"]},
    {"modelId": "lab/research-ft", "tags": ["base_model:finetune:Qwen/Qwen2.5-3B", "license:mit"]},
    {"modelId": "lab/merged", "tags": ["base_model:merge:fan/Hermes-ft", "base_model:merge:lab/research-ft"]},
]  # fmt: skip


@pytest.fixture(scope="module")
def conn(tmp_path_factory: pytest.TempPathFactory) -> Iterator[relate.Connection]:
    parsed = parse_rows(ROWS)
    keep = descendants(parsed.models, ["meta-llama/Llama-3.1-8B", "Qwen/Qwen2.5-3B"])
    store = tmp_path_factory.mktemp("graph") / "pedigree.rl"
    build(store, parsed.models, keep, ROOT / "sources", {"dataset": "test", "revision": "r"}, {"Qwen/Qwen2.5-3B": "qwen-research"})
    c = relate.connect(str(store), read_only=True)
    yield c
    c.close()


def test_a_fine_tune_inherits_every_obligation_of_its_ancestors_licence(conn: relate.Connection) -> None:
    result = checks.check(conn, "fan/Hermes-ft")
    kinds = {i["kind"] for i in result["inherited"] if i["licence"] == "llama3.1"}
    assert kinds == {"attribution", "naming", "notice", "use_policy", "user_threshold"}


def test_the_nearest_ancestor_carrying_the_licence_is_named_with_the_path(conn: relate.Connection) -> None:
    item = next(i for i in checks.check(conn, "fan/Hermes-ft")["inherited"] if i["kind"] == "naming")
    assert item["nearest"]["ancestor"] == "meta-llama/Llama-3.1-8B-Instruct"
    assert item["nearest"]["chain"] == ["fan/Hermes-ft", "meta-llama/Llama-3.1-8B-Instruct"]
    assert item["nearest"]["clause"] == "1.b.i"


def test_a_different_declared_licence_is_reported(conn: relate.Connection) -> None:
    result = checks.check(conn, "fan/Hermes-ft")
    assert result["declared"] == "apache-2.0"
    assert {d["licence"] for d in result["differs"]} == {"llama3.1"}


def test_the_same_declared_licence_differs_from_nothing(conn: relate.Connection) -> None:
    assert checks.check(conn, "fan/Llama-3.1-Hermes")["differs"] == []


def test_the_naming_clause_applies_to_a_fine_tune_without_the_prefix(conn: relate.Connection) -> None:
    assert [n["prefix"] for n in checks.check(conn, "fan/Hermes-ft")["naming"]] == ["Llama"]
    assert checks.check(conn, "fan/Llama-3.1-Hermes")["naming"] == []


def test_a_quantisation_inherits_but_is_not_a_newly_trained_model(conn: relate.Connection) -> None:
    result = checks.check(conn, "quant/Hermes-ft-GGUF")
    assert "llama3.1" in result["upstream_licences"] and result["naming"] == []
    assert result["declared"] is None


def test_a_research_licence_upstream_shows_as_non_commercial(conn: relate.Connection) -> None:
    result = checks.check(conn, "lab/research-ft")
    assert [u["licence"] for u in result["non_commercial"]] == ["qwen-research"]


def test_a_merge_inherits_from_both_parents(conn: relate.Connection) -> None:
    assert checks.check(conn, "lab/merged")["upstream_licences"] == ["apache-2.0", "llama3.1", "mit", "qwen-research"]


def test_a_root_inherits_nothing(conn: relate.Connection) -> None:
    assert checks.check(conn, "meta-llama/Llama-3.1-8B")["inherited"] == []


def test_an_unknown_model_is_refused(conn: relate.Connection) -> None:
    with pytest.raises(KeyError):
        checks.check(conn, "nobody/nothing")
