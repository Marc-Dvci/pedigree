"""Lineage from Hub tags."""

from __future__ import annotations

from pedigree.lineage import descendants, family_roots, parse_rows, parse_tags


def test_a_typed_tag_gives_the_relation() -> None:
    licence, parents, loop = parse_tags("u/m", ["base_model:x/y", "base_model:finetune:x/y", "license:llama3.1"])
    assert (licence, parents, loop) == ("llama3.1", {"x/y": "finetune"}, False)


def test_an_untyped_tag_alone_is_a_plain_base() -> None:
    assert parse_tags("u/m", ["base_model:x/y"])[1] == {"x/y": "base"}


def test_a_merge_keeps_every_parent() -> None:
    _, parents, _ = parse_tags(
        "u/m", ["base_model:merge:a/b", "base_model:merge:c/d", "base_model:a/b", "base_model:c/d"]
    )
    assert parents == {"a/b": "merge", "c/d": "merge"}


def test_a_card_naming_the_model_as_its_own_base_is_dropped_and_counted() -> None:
    licence, parents, loop = parse_tags("u/m", ["base_model:u/m", "base_model:finetune:u/m", "license:mit"])
    assert (parents, loop, licence) == ({}, True, "mit")


def test_no_licence_tag_gives_none() -> None:
    assert parse_tags("u/m", ["transformers"])[0] is None


def test_a_parent_named_with_other_casing_resolves_to_the_hub_id() -> None:
    parsed = parse_rows(
        [{"modelId": "Org/Base", "tags": []}, {"modelId": "u/ft", "tags": ["base_model:finetune:org/base"]}]
    )
    assert parsed.models["u/ft"].parents == {"Org/Base": "finetune"}
    assert parsed.unknown_parents == 0


def test_a_parent_outside_the_snapshot_is_kept_and_counted() -> None:
    parsed = parse_rows([{"modelId": "u/ft", "tags": ["base_model:finetune:gone/model"]}])
    assert parsed.models["u/ft"].parents == {"gone/model": "finetune"}
    assert parsed.unknown_parents == 1


def test_descendants_follow_every_level_and_merges() -> None:
    parsed = parse_rows(
        [
            {"modelId": "meta-llama/L", "tags": []},
            {"modelId": "a/ft", "tags": ["base_model:finetune:meta-llama/L"]},
            {"modelId": "b/q", "tags": ["base_model:quantized:a/ft"]},
            {"modelId": "c/merge", "tags": ["base_model:merge:a/ft", "base_model:merge:z/other"]},
            {"modelId": "z/other", "tags": []},
        ]
    )
    assert descendants(parsed.models, ["meta-llama/L"]) == {"meta-llama/L", "a/ft", "b/q", "c/merge"}


def test_family_roots_are_the_owners_models() -> None:
    parsed = parse_rows([{"modelId": "Qwen/A", "tags": []}, {"modelId": "qwen-fan/B", "tags": []}])
    assert family_roots(parsed.models, ["qwen"]) == ["Qwen/A"]
