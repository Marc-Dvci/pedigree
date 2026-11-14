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
    build(
        store,
        parsed.models,
        keep,
        ROOT / "sources",
        {"dataset": "test", "revision": "r"},
        {"Qwen/Qwen2.5-3B": "qwen-research"},
    )
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


def test_inheritors_count_every_model_below_a_licence(conn: relate.Connection) -> None:
    from pedigree import stats

    # Under llama3.1: the instruct model, two fine-tunes, the quantisation and the merge.
    assert stats.inheritors(conn, "llama3.1") == 5


def test_the_declared_breakdown_counts_what_inheritors_declare(conn: relate.Connection) -> None:
    from pedigree import stats

    got = {r["declared"]: r["models"] for r in stats.declared_breakdown(conn, "llama3.1")}
    assert got == {"llama3.1": 2, "apache-2.0": 1, "none": 2}


def test_naming_counts_trained_models_and_those_with_the_prefix(conn: relate.Connection) -> None:
    from pedigree import stats

    # Trained under llama3.1: Llama-3.1-8B-Instruct, Hermes-ft, Llama-3.1-Hermes and the merge.
    assert stats.naming(conn, "llama3.1", "Llama") == {"trained": 4, "prefixed": 2}


def test_the_family_owners_own_models_can_be_left_out(conn: relate.Connection) -> None:
    from pedigree import stats

    assert stats.inheritors(conn, "llama3.1", exclude=["meta-llama"]) == 4
    assert stats.naming(conn, "llama3.1", "Llama", exclude=["meta-llama"]) == {"trained": 3, "prefixed": 1}


def test_the_summary_covers_every_licence_with_obligations_beyond_a_notice(conn: relate.Connection) -> None:
    from pedigree import stats

    s = stats.summary(conn, exclude=["meta-llama"])
    assert s["licences"]["llama3.1"]["inheritors"] == 4
    assert s["licences"]["llama3.1"]["naming"] == {"prefix": "Llama", "trained": 3, "prefixed": 1}
    assert s["licences"]["qwen-research"]["inheritors"] == 2  # the research fine-tune and the merge
    assert "apache-2.0" not in s["licences"]


def test_the_page_slice_gives_the_same_pedigree_as_the_full_graph(conn: relate.Connection, tmp_path: Path) -> None:
    from pedigree.export import export

    counts = export(conn, tmp_path, per_licence=10, stats={"licences": {}})
    assert counts["models"] >= 5
    copy = relate.connect(":memory:")
    for statement in (tmp_path / "slice.cypher").read_text(encoding="utf-8").split(";\n"):
        if statement.strip():
            copy.execute(statement)
    for model_id in ["fan/Hermes-ft", "lab/merged", "quant/Hermes-ft-GGUF"]:
        assert checks.check(copy, model_id)["inherited"] == checks.check(conn, model_id)["inherited"]
    assert (tmp_path / "queries.json").exists() and (tmp_path / "stats.json").exists()


def test_a_cypher_literal_is_written_for_every_property_type() -> None:
    from pedigree.export import literal

    assert [literal(v) for v in (None, True, 3, 1.5, 'a "b"', ["x", 2])] == [
        "null",
        "true",
        "3",
        "1.5",
        '"a \\"b\\""',
        '["x", 2]',
    ]
    with pytest.raises(TypeError):
        literal({"a": 1})


def test_a_licence_named_only_in_the_card_claims_no_difference(tmp_path: Path) -> None:
    rows_ = [
        {"modelId": "meta-llama/Llama-3.1-8B", "tags": ["license:llama3.1"]},
        {"modelId": "fan/own-terms", "tags": ["base_model:finetune:meta-llama/Llama-3.1-8B", "license:other"]},
    ]
    parsed = parse_rows(rows_)
    store = tmp_path / "p.rl"
    build(
        store,
        parsed.models,
        descendants(parsed.models, ["meta-llama/Llama-3.1-8B"]),
        ROOT / "sources",
        {"dataset": "t"},
    )
    c = relate.connect(str(store), read_only=True)
    try:
        result = checks.check(c, "fan/own-terms")
    finally:
        c.close()
    assert result["declared_unresolved"] is True
    assert result["differs"] == []
    assert result["upstream_licences"] == ["llama3.1"]  # what it inherits is still reported


def test_a_declared_licence_differs_only_where_its_wording_differs(tmp_path: Path) -> None:
    # Llama 3 asks for "Built with Meta Llama 3" and a "Llama 3" name; Llama 3.1 for "Built with Llama" and a "Llama"
    # name. Their notice, use-policy and user-threshold clauses read the same.
    rows_ = [
        {"modelId": "meta-llama/Llama-3.1-8B", "tags": ["license:llama3.1"]},
        {"modelId": "fan/Hermes-like", "tags": ["base_model:finetune:meta-llama/Llama-3.1-8B", "license:llama3"]},
    ]
    parsed = parse_rows(rows_)
    store = tmp_path / "p.rl"
    build(
        store,
        parsed.models,
        descendants(parsed.models, ["meta-llama/Llama-3.1-8B"]),
        ROOT / "sources",
        {"dataset": "t"},
    )
    c = relate.connect(str(store), read_only=True)
    try:
        result = checks.check(c, "fan/Hermes-like")
    finally:
        c.close()
    assert {(d["licence"], d["kind"]) for d in result["differs"]} == {
        ("llama3.1", "attribution"),
        ("llama3.1", "naming"),
    }
    assert {i["kind"] for i in result["inherited"]} >= {"notice", "use_policy", "user_threshold"}
