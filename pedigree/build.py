"""Write the lineage graph into one Relate file, `pedigree.rl`.

    (:Model {id, author, name, licence, downloads, likes, created, library, pipeline, in_snapshot})
    (:Model)-[:DERIVED_FROM {relation}]->(:Model)          finetune | adapter | merge | quantized | base
    (:Model)-[:DECLARES]->(:Licence {id, name})
    (:Licence)-[:REQUIRES]->(:Obligation {licence, kind, clause, text, source})
    (:Snapshot {dataset, revision, rows, built})
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import relate

from pedigree.lineage import Model

BATCH = 5_000

# `license:other` hides the real licence: the card's license_name says which one. These names map to licences whose
# texts are in the clause table (sources/obligations.csv).
OTHER_NAMES = {
    "qwen": "qwen",
    "qwen-research": "qwen-research",
    "mrl": "mrl",
    "mnpl": "mnpl",
    "deepseek": "deepseek",
    "deepseek-license": "deepseek",
    "gemma-terms-of-use": "gemma",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _batches(items: list[dict[str, Any]], size: int = BATCH) -> Iterable[list[dict[str, Any]]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def licence_of(model: Model, other_names: Mapping[str, str]) -> str | None:
    """The clause-table id of the licence a model declares, `other` resolved through its license_name."""
    if model.licence == "other":
        name = other_names.get(model.id, "").strip().lower()
        # A name the clause table covers maps to it; any other name stays as itself, with no obligations attached.
        return OTHER_NAMES.get(name, name or "other")
    return model.licence


def build(
    path: Path,
    models: Mapping[str, Model],
    keep: set[str],
    sources: Path,
    snapshot: Mapping[str, Any],
    other_names: Mapping[str, str] | None = None,
) -> dict[str, int]:
    """Write the models in `keep`, their parents and their licences to a new store at `path`."""
    if path.exists():
        raise FileExistsError(f"{path} exists; a build writes a new store")
    other_names = other_names or {}
    licences = read_csv(sources / "licence-names.csv")
    obligations = read_csv(sources / "obligations.csv")
    ids = set(keep)
    for model_id in keep:
        ids.update(models[model_id].parents if model_id in models else [])

    nodes, edges, declares = [], [], []
    for model_id in sorted(ids):
        model = models.get(model_id)
        if model is None:
            nodes.append({"id": model_id, "author": model_id.split("/", 1)[0], "name": model_id.split("/", 1)[-1],
                          "licence": None, "downloads": 0, "likes": 0, "created": "", "library": "", "pipeline": "",
                          "in_snapshot": False})  # fmt: skip
            continue
        lic = licence_of(model, other_names)
        nodes.append({"id": model.id, "author": model.author, "name": model.name, "licence": lic,
                      "downloads": model.downloads, "likes": model.likes, "created": model.created,
                      "library": model.library, "pipeline": model.pipeline, "in_snapshot": True})  # fmt: skip
        if lic:
            declares.append({"model": model.id, "licence": lic})
        if model_id in keep:
            edges.extend({"child": model.id, "parent": p, "relation": r} for p, r in sorted(model.parents.items()))

    conn = relate.connect(str(path))
    try:
        conn.execute("CREATE INDEX model_id IF NOT EXISTS FOR (m:Model) ON (m.id)")
        conn.execute("CREATE INDEX licence_id IF NOT EXISTS FOR (l:Licence) ON (l.id)")
        conn.execute(
            "UNWIND $rows AS r CREATE (:Licence {id: r.licence, name: r.name})",
            {"rows": [*licences, *({"licence": d, "name": d} for d in sorted({x["licence"] for x in declares} - {r["licence"] for r in licences}))]},
        )
        conn.execute(
            "UNWIND $rows AS r MATCH (l:Licence {id: r.licence}) "
            "CREATE (l)-[:REQUIRES]->(:Obligation {licence: r.licence, kind: r.kind, clause: r.clause, "
            "text: r.text, source: r.source})",
            {"rows": obligations},
        )
        for batch in _batches(nodes):
            conn.execute(
                "UNWIND $rows AS r CREATE (:Model {id: r.id, author: r.author, name: r.name, licence: r.licence, "
                "downloads: r.downloads, likes: r.likes, created: r.created, library: r.library, "
                "pipeline: r.pipeline, in_snapshot: r.in_snapshot})",
                {"rows": batch},
            )
        for batch in _batches(edges):
            conn.execute(
                "UNWIND $rows AS r MATCH (c:Model {id: r.child}), (p:Model {id: r.parent}) "
                "CREATE (c)-[:DERIVED_FROM {relation: r.relation}]->(p)",
                {"rows": batch},
            )
        for batch in _batches(declares):
            conn.execute(
                "UNWIND $rows AS r MATCH (m:Model {id: r.model}), (l:Licence {id: r.licence}) CREATE (m)-[:DECLARES]->(l)",
                {"rows": batch},
            )
        conn.execute("CREATE (:Snapshot $s)", {"s": dict(snapshot)})
    finally:
        conn.close()
    return {"models": len(nodes), "derived_from": len(edges), "declares": len(declares), "obligations": len(obligations)}
