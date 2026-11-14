"""MCP server: a model's pedigree as tools for any agent.

    python -m pedigree mcp [--store pedigree.rl]

The lineage graph is opened read-only for every call. Every claim about a licence must quote the clause a tool
returned.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import relate
from mcp.server.mcpserver import MCPServer

from pedigree import checks

ROW_CAP = 200

INSTRUCTIONS = """\
Pedigree holds the family tree of open models on Hugging Face: which model each one was fine-tuned, adapted, merged
or quantised from, the licence each declares, and the obligations each licence passes to derivatives (attribution,
naming, notice, use policy, non-commercial terms, user thresholds), with the clause and its source.

Before recommending or downloading a model, call check_model. Report what it inherits, from which ancestor, and where
the declared terms differ from upstream terms. Quote the clause the tool returns; never paraphrase a licence from
memory. Say "declared terms differ from upstream terms", not that anyone broke a licence.
"""


def plain(value: Any) -> Any:
    if isinstance(value, relate.Node):
        return {"labels": list(value.labels), **{k: plain(v) for k, v in value.properties.items()}}
    if isinstance(value, relate.Relationship):
        return {"type": value.type, **{k: plain(v) for k, v in value.properties.items()}}
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [plain(v) for v in value]
    return value


def build_server(store: Path) -> MCPServer:
    server: MCPServer = MCPServer(name="pedigree", instructions=INSTRUCTIONS)

    def connect() -> relate.Connection:
        return relate.connect(str(store), read_only=True)

    @server.tool()
    def check_model(model_id: str) -> dict[str, Any]:
        """A model's pedigree: its declared licence, every obligation its ancestors' licences pass down (with the
        ancestor, the path and the clause), where the declared terms differ, the naming clause, and non-commercial
        terms upstream. model_id is the Hugging Face id, for example 'NousResearch/Hermes-3-Llama-3.1-8B'."""
        conn = connect()
        try:
            return checks.check(conn, model_id)
        except KeyError:
            return {"error": f"{model_id} is not in the lineage graph"}
        finally:
            conn.close()

    @server.tool()
    def find_models(text: str, limit: int = 20) -> list[dict[str, Any]]:
        """Models whose id contains the text (case-insensitive), most downloaded first."""
        conn = connect()
        try:
            return checks.rows(
                conn,
                "MATCH (m:Model) WHERE toLower(m.id) CONTAINS toLower($t) "
                "RETURN m.id AS id, m.licence AS licence, m.downloads AS downloads ORDER BY downloads DESC LIMIT $n",
                {"t": text, "n": max(1, min(limit, 100))},
            )
        finally:
            conn.close()

    @server.tool()
    def read_cypher(query: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run a read-only Cypher query on the lineage graph. Rows are capped at 200."""
        conn = connect()
        try:
            cursor = conn.execute(query, params or {})
            result = [plain(dict(row)) for row in cursor.fetch(ROW_CAP + 1)]
        except relate.Error as exc:
            return {"error": str(exc)}
        finally:
            conn.close()
        return {"rows": result[:ROW_CAP], "truncated": len(result) > ROW_CAP}

    @server.tool()
    def get_schema() -> dict[str, Any]:
        """Labels, relationship types and the snapshot the graph was built from."""
        conn = connect()
        try:
            return {
                "labels": checks.rows(conn, "MATCH (n) UNWIND labels(n) AS l RETURN l AS label, count(*) AS nodes"),
                "relationships": checks.rows(conn, "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS n"),
                "snapshot": checks.rows(conn, "MATCH (s:Snapshot) RETURN properties(s) AS snapshot"),
            }
        finally:
            conn.close()

    return server


def run(store: Path) -> None:
    build_server(store).run("stdio")
