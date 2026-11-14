"""Export a slice of the lineage graph for the browser page, which runs it on Relate's WebAssembly build.

The slice holds the most downloaded models under each licence with obligations, every ancestor of those models, the
licences and their obligations. The page runs the same check query as the command line (pedigree/checks.py).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import relate

from pedigree.checks import INHERITED, MAX_DEPTH, rows

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def literal(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list | tuple):
        return "[" + ", ".join(literal(v) for v in value) + "]"
    raise TypeError(type(value).__name__)


def _props(props: dict[str, Any]) -> str:
    return (
        "{"
        + ", ".join(f"{k}: {literal(v)}" for k, v in sorted(props.items()) if v is not None and _NAME.match(k))
        + "}"
    )


def pick(conn: relate.Connection, per_licence: int) -> list[str]:
    """The most downloaded models under each licence that carries obligations beyond a notice, and their ancestors."""
    # Licences whose obligations go beyond keeping a notice (the permissive licences only ask for that).
    licences = [
        r["id"]
        for r in rows(
            conn,
            "MATCH (l:Licence)-[:REQUIRES]->(o:Obligation) WHERE o.kind <> 'notice' RETURN DISTINCT l.id AS id",
        )
    ]
    chosen: set[str] = set()
    for licence in licences:
        anchors = [
            r["id"]
            for r in rows(conn, "MATCH (:Licence {id: $l})<-[:DECLARES]-(a:Model) RETURN a.id AS id", {"l": licence})
        ]
        best: dict[str, int] = {}
        for start in range(0, len(anchors), 200):
            found = rows(
                conn,
                f"UNWIND $anchors AS aid MATCH (a:Model {{id: aid}}) "
                f"MATCH p = ANY SHORTEST (a)<-[:DERIVED_FROM]-{{1,{MAX_DEPTH}}}(m:Model) "
                "WITH DISTINCT m.id AS id, m.downloads AS d ORDER BY d DESC LIMIT $n RETURN id, d",
                {"anchors": anchors[start : start + 200], "n": per_licence},
            )
            best.update({r["id"]: int(r["d"] or 0) for r in found})
        chosen.update(sorted(best, key=lambda i: (-best[i], i))[:per_licence])
    ids = sorted(chosen)
    ancestors = rows(
        conn,
        f"UNWIND $ids AS id MATCH (m:Model {{id: id}}) MATCH p = ANY SHORTEST (m)-[:DERIVED_FROM]->{{1,{MAX_DEPTH}}}(a:Model) "
        "RETURN DISTINCT a.id AS id",
        {"ids": ids},
    )
    return sorted(chosen | {r["id"] for r in ancestors})


def slice_script(conn: relate.Connection, ids: list[str]) -> str:
    models = rows(conn, "UNWIND $ids AS id MATCH (m:Model {id: id}) RETURN properties(m) AS p", {"ids": ids})
    edges = rows(
        conn,
        "UNWIND $ids AS id MATCH (m:Model {id: id})-[d:DERIVED_FROM]->(p:Model) WHERE p.id IN $ids "
        "RETURN m.id AS c, p.id AS p, d.relation AS r",
        {"ids": ids},
    )
    licences = rows(conn, "MATCH (l:Licence) RETURN properties(l) AS p")
    obligations = rows(conn, "MATCH (l:Licence)-[:REQUIRES]->(o:Obligation) RETURN l.id AS l, properties(o) AS p")
    snapshot = rows(conn, "MATCH (s:Snapshot) RETURN properties(s) AS p")
    out = ["CREATE INDEX model_id IF NOT EXISTS FOR (m:Model) ON (m.id);"]
    out += [f"CREATE (:Licence {_props(dict(r['p']))});" for r in licences]
    out += [
        f"MATCH (l:Licence {{id: {literal(r['l'])}}}) CREATE (l)-[:REQUIRES]->(:Obligation {_props(dict(r['p']))});"
        for r in obligations
    ]
    out += [f"CREATE (:Model {_props(dict(r['p']))});" for r in models]
    out += [
        f"MATCH (c:Model {{id: {literal(e['c'])}}}), (p:Model {{id: {literal(e['p'])}}}) "
        f"CREATE (c)-[:DERIVED_FROM {{relation: {literal(e['r'])}}}]->(p);"
        for e in edges
    ]
    out.append("MATCH (m:Model), (l:Licence) WHERE m.licence = l.id CREATE (m)-[:DECLARES]->(l);")
    out += [f"CREATE (:Snapshot {_props(dict(r['p']))});" for r in snapshot]
    return "\n".join(out) + "\n"


def export(
    conn: relate.Connection, out_dir: Path, per_licence: int = 60, stats: dict[str, Any] | None = None
) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    ids = pick(conn, per_licence)
    (out_dir / "slice.cypher").write_text(slice_script(conn, ids), encoding="utf-8")
    (out_dir / "queries.json").write_text(json.dumps({"inherited": INHERITED}, indent=2) + "\n", encoding="utf-8")
    if stats is not None:
        (out_dir / "stats.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    return {"models": len(ids)}
