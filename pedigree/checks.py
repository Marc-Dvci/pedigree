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


HUB_URL = re.compile(r"^(?:https?://)?(?:www\.)?(?:huggingface\.co|hf\.co)/", re.IGNORECASE)


def resolve(conn: relate.Connection, text: str) -> str | None:
    """The graph's id for a model id as a person types it: a Hub URL works, and the Hub ignores case in ids."""
    model_id = HUB_URL.sub("", text.strip()).strip("/")
    if rows(conn, "MATCH (m:Model {id: $id}) RETURN m.id AS id", {"id": model_id}):
        return model_id
    found = rows(conn, "MATCH (m:Model) WHERE toLower(m.id) = $id RETURN m.id AS id", {"id": model_id.lower()})
    return found[0]["id"] if len(found) == 1 else None


def model(conn: relate.Connection, model_id: str) -> dict[str, Any] | None:
    resolved = resolve(conn, model_id)
    if resolved is None:
        return None
    model_id = resolved
    found = rows(
        conn,
        "MATCH (m:Model {id: $id}) OPTIONAL MATCH (m)-[d:DERIVED_FROM]->(p:Model) "
        "RETURN m.id AS id, m.name AS name, m.licence AS licence, m.downloads AS downloads, "
        "collect({parent: p.id, relation: d.relation}) AS parents",
        {"id": model_id},
    )
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


OWN = """
MATCH (:Model {id: $id})-[:DECLARES]->(l:Licence)-[:REQUIRES]->(o:Obligation)
RETURN l.id AS licence, o.kind AS kind, o.text AS text
ORDER BY kind
"""


def own(conn: relate.Connection, model_id: str) -> list[dict[str, Any]]:
    """The obligations of the model's own declared licence."""
    return rows(conn, OWN, {"id": model_id})


def query_texts() -> dict[str, str]:
    """The Cypher the browser page runs, written to web/data/queries.json by the export."""
    return {"inherited": INHERITED, "own": OWN}


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
    model_id = found["id"]
    upstream = inherited(conn, model_id)
    declared = found["licence"]
    # `other` is the Hub's id for a licence named only in the card: it may be the upstream licence itself, so the
    # declared terms are unresolved and no difference is claimed.
    unresolved = declared == "other"
    # An upstream term differs when the declared licence has no term of the same kind in the same words: Llama 3's
    # "Built with Meta Llama 3" is not Llama 3.1's "Built with Llama", while their notice clauses read the same.
    carried = {(o["kind"], o["text"]) for o in own(conn, model_id)}
    differs = [] if unresolved else [u for u in upstream if (u["kind"], u["nearest"]["text"]) not in carried]
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
        "declared_unresolved": unresolved,
        "parents": found["parents"],
        "inherited": upstream,
        "differs": differs,
        "naming": naming,
        "non_commercial": non_commercial,
        "upstream_licences": sorted({u["licence"] for u in upstream}),
    }
