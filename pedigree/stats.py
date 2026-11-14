"""Population figures on the lineage graph, all in Cypher: who inherits each licence's terms, what they declare
instead, and how the naming clause is followed."""

from __future__ import annotations

from typing import Any

import relate

from pedigree.checks import MAX_DEPTH, TRAINED, rows

# Models below an ancestor that declares the licence (the ancestor itself excluded).
UNDER = f"""
MATCH (l:Licence {{id: $licence}})<-[:DECLARES]-(a:Model)
MATCH p = ANY SHORTEST (a)<-[:DERIVED_FROM]-{{1,{MAX_DEPTH}}}(m:Model)
WITH DISTINCT m WHERE NOT m.author IN $exclude
"""


def inheritors(conn: relate.Connection, licence: str, exclude: list[str] | None = None) -> int:
    return int(rows(conn, UNDER + "RETURN count(m) AS n", {"licence": licence, "exclude": exclude or []})[0]["n"])


def declared_breakdown(conn: relate.Connection, licence: str, exclude: list[str] | None = None) -> list[dict[str, Any]]:
    """What the models under a licence declare: the same licence, another one, or nothing."""
    return rows(
        conn,
        UNDER + "RETURN coalesce(m.licence, 'none') AS declared, count(m) AS models ORDER BY models DESC, declared",
        {"licence": licence, "exclude": exclude or []},
    )


def naming(conn: relate.Connection, licence: str, prefix: str, exclude: list[str] | None = None) -> dict[str, int]:
    """Among fine-tunes, adapters and merges under the licence: how many names begin with the prefix."""
    pattern = "^" + "[-_ .]*".join(part for part in prefix.lower().split()) + ".*"
    found = rows(
        conn,
        UNDER
        + "MATCH (m)-[d:DERIVED_FROM]->() WHERE d.relation IN $trained WITH DISTINCT m "
        + "RETURN count(m) AS trained, sum(CASE WHEN toLower(m.name) =~ $pattern THEN 1 ELSE 0 END) AS prefixed",
        {"licence": licence, "trained": list(TRAINED), "pattern": pattern, "exclude": exclude or []},
    )[0]
    return {"trained": int(found["trained"]), "prefixed": int(found["prefixed"] or 0)}


def summary(conn: relate.Connection, exclude: list[str] | None = None) -> dict[str, Any]:
    """Every figure, for third-party models: the family owners' own models are left out."""
    licences = [
        r["id"]
        for r in rows(conn, "MATCH (l:Licence)-[:REQUIRES]->(:Obligation {kind: 'naming'}) RETURN DISTINCT l.id AS id")
    ]
    restrictive = [
        r["id"]
        for r in rows(
            conn,
            "MATCH (l:Licence)-[:REQUIRES]->(o:Obligation) WHERE o.kind IN ['naming','use_policy','non_commercial','user_threshold'] "
            "RETURN DISTINCT l.id AS id ORDER BY id",
        )
    ]
    out: dict[str, Any] = {"licences": {}}
    for licence in restrictive:
        out["licences"][licence] = {
            "inheritors": inheritors(conn, licence, exclude),
            "declared": declared_breakdown(conn, licence, exclude),
        }
    prefixes = {
        r["licence"]: r["text"]
        for r in rows(conn, "MATCH (o:Obligation {kind: 'naming'}) RETURN o.licence AS licence, o.text AS text")
    }
    import re

    for licence in licences:
        match = re.search(r'"([^"]+)" at the beginning', prefixes.get(licence, ""))
        if match:
            out["licences"].setdefault(licence, {})["naming"] = {
                "prefix": match.group(1),
                **naming(conn, licence, match.group(1), exclude),
            }
    return out
