"""The checks for one model: what its ancestors' licences require, and where its declared terms differ.

All of it is Cypher on the lineage graph. A finding names the ancestor whose licence carries the obligation, the path
to it, and the clause, so a person can read the source. Where the graph cannot tell (a declared licence the terms
table does not hold, an ancestor whose card is not in the snapshot), the result says so.
"""

from __future__ import annotations

import re
from typing import Any

import relate

MAX_DEPTH = 30
TRAINED = ("finetune", "adapter", "merge")  # relations that create a new model (a quantisation repackages one)
# The owners whose releases root the family trees the graph traces (the build's --family default).
FAMILIES = ["meta-llama", "google", "Qwen", "mistralai", "deepseek-ai"]


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
        "RETURN m.id AS id, m.name AS name, m.author AS author, m.licence AS licence, m.downloads AS downloads, "
        "m.in_snapshot AS in_snapshot, collect({parent: p.id, relation: d.relation}) AS parents",
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


# Where the declared family tree leaves the graph: an ancestor whose card is not in the snapshot (its licence and base
# models are unknown), or one outside the families' trees whose own base models the build did not follow.
BEYOND = f"""
MATCH p = ANY SHORTEST (m:Model {{id: $id}})-[:DERIVED_FROM]->{{1,{MAX_DEPTH}}}(a:Model)
WHERE a.in_snapshot = false OR (NOT EXISTS {{ (a)-[:DERIVED_FROM]->() }} AND NOT a.author IN $families)
RETURN a.id AS model, a.in_snapshot = false AS not_in_snapshot, length(p) AS steps
ORDER BY steps, model
"""


def beyond(conn: relate.Connection, model_id: str) -> list[dict[str, Any]]:
    """The ancestors where the declared family tree leaves the graph, nearest first."""
    return rows(conn, BEYOND, {"id": model_id, "families": FAMILIES})


def query_texts() -> dict[str, Any]:
    """The Cypher the browser page runs, written to web/data/queries.json by the export."""
    return {"inherited": INHERITED, "own": OWN, "beyond": BEYOND, "families": FAMILIES}


def coverage(conn: relate.Connection) -> dict[str, Any]:
    """What the graph holds: its size, the families it traces and the snapshot it was built from."""
    snap = rows(conn, "MATCH (s:Snapshot) RETURN s.revision AS revision, s.built AS built")
    found = rows(conn, "MATCH (m:Model) RETURN count(m) AS models")
    return {"models": int(found[0]["models"]), "families": FAMILIES, **(snap[0] if snap else {})}


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
    # `other` is the Hub's id for a licence named only in the card: it may be the upstream licence itself.
    unresolved = declared == "other"
    own_terms = own(conn, model_id)
    # The model's own lineage is unknown when its card is not in the snapshot, or when it sits outside the families'
    # trees (it is in the graph only as a base model of others).
    if found["in_snapshot"] is False:
        lineage = "not_in_snapshot"
    elif not found["parents"] and found["author"] not in FAMILIES:
        lineage = "outside"
    else:
        lineage = "traced"
    # The declared terms are compared only when the terms table holds the declared licence. A licence named only in the
    # card, one the table does not hold, or a card outside the snapshot leaves them unknown: the upstream terms are
    # listed and no difference is claimed.
    if lineage == "not_in_snapshot":
        declared_terms = "unknown"
    else:
        declared_terms = "none" if declared is None else "compared" if own_terms else "unknown"
    # An upstream term differs when the declared licence has no term of the same kind in the same words: Llama 3's
    # "Built with Meta Llama 3" is not Llama 3.1's "Built with Llama", while their notice clauses read the same.
    carried = {(o["kind"], o["text"]) for o in own_terms}
    differs = (
        [] if declared_terms == "unknown" else [u for u in upstream if (u["kind"], u["nearest"]["text"]) not in carried]
    )
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
        "declared_terms": declared_terms,
        "lineage": lineage,
        "lineage_unknown": beyond(conn, model_id),
        "parents": found["parents"],
        "inherited": upstream,
        "differs": differs,
        "naming": naming,
        "non_commercial": non_commercial,
        "upstream_licences": sorted({u["licence"] for u in upstream}),
    }
