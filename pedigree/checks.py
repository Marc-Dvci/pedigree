"""The checks for one model: what its ancestors' licences require, and where its declared terms differ.

All of it is Cypher on the lineage graph. A finding names the ancestor whose licence carries the obligation, the path
to it, and the clause, so a person can read the source.
"""

from __future__ import annotations

import re
from typing import Any

import relate

MAX_DEPTH = 30
TRAINED = ("finetune", "adapter", "merge")  # relations that create a new model (a quantisation repackages one)


def rows(conn: relate.Connection, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(query, params or {})]


def model(conn: relate.Connection, model_id: str) -> dict[str, Any] | None:
    found = rows(
        conn,
        "MATCH (m:Model {id: $id}) OPTIONAL MATCH (m)-[d:DERIVED_FROM]->(p:Model) "
        "RETURN m.id AS id, m.name AS name, m.licence AS licence, m.downloads AS downloads, "
        "collect({parent: p.id, relation: d.relation}) AS parents",
        {"id": model_id},
    )
    if not found:
        return None
    row = found[0]
    row["parents"] = [p for p in row["parents"] if p["parent"] is not None]
    return row


# One shortest path to each ancestor (ANY SHORTEST): dense families of merges have far more paths than ancestors.
INHERITED = f"""
MATCH p = ANY SHORTEST (m:Model {{id: $id}})-[:DERIVED_FROM]->{{1,{MAX_DEPTH}}}(a:Model)
MATCH (a)-[:DECLARES]->(l:Licence)-[:REQUIRES]->(o:Obligation)
WITH l, o, a, [n IN nodes(p) | n.id] AS chain, [r IN relationships(p) | r.relation] AS relations
ORDER BY size(chain) ASC, a.id ASC
WITH l.id AS licence, o.kind AS kind, collect({{ancestor: a.id, chain: chain, relations: relations, clause: o.clause, text: o.text, source: o.source}})[0] AS nearest
RETURN licence, kind, nearest
ORDER BY licence, kind
"""


def inherited(conn: relate.Connection, model_id: str) -> list[dict[str, Any]]:
    """Every obligation an ancestor's licence carries, from the nearest ancestor that declares it."""
    return rows(conn, INHERITED, {"id": model_id})


def own(conn: relate.Connection, model_id: str) -> list[dict[str, Any]]:
    return rows(
        conn,
        "MATCH (:Model {id: $id})-[:DECLARES]->(l:Licence)-[:REQUIRES]->(o:Obligation) "
        "RETURN l.id AS licence, o.kind AS kind ORDER BY kind",
        {"id": model_id},
    )


def _prefix(text: str) -> str | None:
    match = re.search(r'"([^"]+)" at the beginning', text)
    return match.group(1) if match else None


def _starts_with(name: str, prefix: str) -> bool:
    normal = re.sub(r"[-_\s.]+", " ", name.lower()).strip()
    return normal.startswith(re.sub(r"[-_\s.]+", " ", prefix.lower()).strip())


def check(conn: relate.Connection, model_id: str) -> dict[str, Any]:
    """A model's pedigree: its declared licence, what it inherits, and where the two differ."""
    found = model(conn, model_id)
    if found is None:
        raise KeyError(model_id)
    upstream = inherited(conn, model_id)
    declared = found["licence"]
    differs = [u for u in upstream if u["licence"] != declared]
    naming = []
    own_relations = {p["relation"] for p in found["parents"]}
    if own_relations & set(TRAINED):
        for u in upstream:
            prefix = _prefix(u["nearest"]["text"]) if u["kind"] == "naming" else None
            if prefix and not _starts_with(found["name"], prefix):
                naming.append({"licence": u["licence"], "prefix": prefix, "clause": u["nearest"]["clause"]})
    non_commercial = [u for u in upstream if u["kind"] == "non_commercial"]
    return {
        "model": found["id"],
        "declared": declared,
        "parents": found["parents"],
        "inherited": upstream,
        "differs": differs,
        "naming": naming,
        "non_commercial": non_commercial,
        "upstream_licences": sorted({u["licence"] for u in upstream}),
    }
