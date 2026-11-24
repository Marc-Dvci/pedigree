"""Command line: `python -m pedigree <command>`.

build   read a pinned snapshot of the Hub's model cards and write the lineage graph to pedigree.rl
check   a model's pedigree: what its ancestors' licences require, and where its declared terms differ
hook    run as a coding-agent hook: check every model a command or new code would download
mcp     serve the checks to agents over MCP (stdio)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from pedigree.checks import FAMILIES

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STORE = ROOT / "pedigree.rl"


def _connect(store: Path) -> Any:
    import relate

    if not store.exists():
        raise SystemExit(f"no lineage graph at {store}; build it with: python -m pedigree build")
    return relate.connect(str(store), read_only=True)


def no_inheritance(result: dict[str, Any]) -> str:
    """Why a model inherits nothing: no ancestor in the graph (its own licence sets its terms), or none with terms."""
    if result["parents"]:
        return "No ancestor in the graph declares a licence with obligations."
    if result.get("declared_unresolved"):
        return "No ancestor in the graph: the licence named in its card sets its terms."
    if result["declared"]:
        return f"No ancestor in the graph: its own licence, {result['declared']}, sets its terms."
    return "No ancestor in the graph, and no licence declared."


OWN_LINEAGE = {
    "not_in_snapshot": "Licence and lineage unknown: other cards name it as a base model, but the snapshot holds no card for it.",
    "outside": "Lineage unknown: it sits outside the traced family trees, so its own base models are not followed.",
}


def _names(ids: list[str]) -> str:
    return ", ".join(ids) if len(ids) <= 3 else f"{', '.join(ids[:3])} and {len(ids) - 3} more"


def lineage_lines(result: dict[str, Any]) -> list[str]:
    """Where the graph cannot follow the declared family tree: the model itself, or ancestors beyond which it stops."""
    lines = []
    if result.get("lineage", "traced") != "traced":
        lines.append(f"  {OWN_LINEAGE[result['lineage']]}")
    ends = result.get("lineage_unknown") or []
    missing = [e["model"] for e in ends if e["not_in_snapshot"]]
    outside = [e["model"] for e in ends if not e["not_in_snapshot"]]
    if len(missing) == 1:
        lines.append(f"  Lineage unknown beyond {missing[0]}: its card is not in the snapshot")
    elif missing:
        lines.append(
            f"  Lineage unknown beyond {len(missing)} ancestors whose cards are not in the snapshot: {_names(missing)}"
        )
    if len(outside) == 1:
        lines.append(f"  Lineage unknown beyond {outside[0]}: it sits outside the traced family trees")
    elif outside:
        lines.append(
            f"  Lineage unknown beyond {len(outside)} ancestors outside the traced family trees: {_names(outside)}"
        )
    return lines


def declared_terms_line(result: dict[str, Any]) -> str | None:
    """The declared terms Pedigree cannot compare: a licence named only in the card, or one its terms table lacks."""
    if result.get("declared_terms") != "unknown" or not result["inherited"]:
        return None
    if result.get("declared_unresolved"):
        return (
            "  Declared terms unknown: the licence is named only in its card. Compare it with the upstream terms above."
        )
    return (
        f"  Declared terms unknown: the terms table does not hold {result['declared']}."
        " Compare it with the upstream terms above."
    )


def render(result: dict[str, Any]) -> str:
    declared = "a licence named in its card (Hub id other)" if result.get("declared_unresolved") else result["declared"]
    lines = [f"{result['model']}: declares {declared or 'no licence'}"]
    if result.get("lineage") == "not_in_snapshot":
        lines = [f"{result['model']}: its card is not in the snapshot"]
    if result.get("lineage", "traced") != "traced" and not result["inherited"]:
        return "\n".join(lines + lineage_lines(result))
    if not result["inherited"]:
        lines.append(f"  {no_inheritance(result)}")
        return "\n".join(lines + lineage_lines(result))
    by_licence: dict[str, list[dict[str, Any]]] = {}
    for item in result["inherited"]:
        by_licence.setdefault(item["licence"], []).append(item)
    for licence, items in by_licence.items():
        nearest = items[0]["nearest"]
        lines.append(f"  Inherits {licence} from {nearest['ancestor']}")
        lines.append(f"    path: {' -> '.join(nearest['chain'])}")
        for item in items:
            lines.append(f"    {item['kind']}: clause {item['nearest']['clause']}: {item['nearest']['text']}")
    if result["differs"]:
        kinds = sorted({d["kind"] for d in result["differs"]})
        lines.append(f"  Declared terms differ from upstream terms: {', '.join(kinds)}")
    unknown = declared_terms_line(result)
    if unknown:
        lines.append(unknown)
    for n in result["naming"]:
        lines.append(
            f"  Name: {n['licence']} clause {n['clause']} asks derivative models to begin with '{n['prefix']}'"
        )
    if result["non_commercial"]:
        lines.append(
            f"  Non-commercial terms upstream: {', '.join(sorted({u['licence'] for u in result['non_commercial']}))}"
        )
    return "\n".join(lines + lineage_lines(result))


def not_in_graph(model_id: str, coverage: dict[str, Any]) -> str:
    """What to say about a model the graph does not hold: its pedigree is unknown here, and what the graph covers."""
    snapshot = f"{str(coverage.get('revision', ''))[:7]}, {coverage.get('built', '')}".strip(", ")
    return (
        f"{model_id} is not in the lineage graph, so its pedigree is unknown here. The graph holds the "
        f"{coverage['models']:,} models of the family trees rooted in releases by {', '.join(coverage['families'])}, "
        f"as their cards declare them in the Hub snapshot ({snapshot})."
    )


def cmd_check(a: argparse.Namespace) -> int:
    from pedigree.checks import check, coverage

    conn = _connect(a.store)
    try:
        try:
            result = check(conn, a.model)
        except KeyError:
            print(not_in_graph(a.model, coverage(conn)), file=sys.stderr)
            return 2
    finally:
        conn.close()
    print(json.dumps(result, indent=2) if a.json else render(result))
    return 0


def needs_review(result: dict[str, Any]) -> bool:
    """The hook reports a model whose upstream terms the declared licence does not carry, or cannot be compared with."""
    unknown = result.get("declared_terms") == "unknown" and bool(result["inherited"])
    return bool(result["differs"] or result["naming"] or result["non_commercial"] or unknown)


def _seen_file(session_id: str) -> Path | None:
    """Where the hook keeps the models it has already reported in one agent session."""
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_")
    if not safe:
        return None
    import tempfile

    return Path(os.environ.get("PEDIGREE_HOOK_STATE", tempfile.gettempdir())) / f"pedigree-hook-{safe}.txt"


def cmd_hook(a: argparse.Namespace) -> int:
    """Claude Code PreToolUse hook: reads the tool call on stdin, reports inherited terms on stderr (exit 2).

    Each model is reported once per agent session: the first call stops so the agent can show the terms to the person,
    and the call made after they agree goes through."""
    from pedigree.checks import check
    from pedigree.detect import model_ids

    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    tool_input = payload.get("tool_input") or {}
    text = " ".join(str(tool_input.get(k, "")) for k in ("command", "content", "new_string"))
    ids = model_ids(text)
    if not ids or not a.store.exists():
        return 0
    seen_file = _seen_file(str(payload.get("session_id") or ""))
    seen = set(seen_file.read_text(encoding="utf-8").split()) if seen_file and seen_file.exists() else set()
    conn = _connect(a.store)
    reports = []
    reported = []
    try:
        for model_id in ids:
            try:
                result = check(conn, model_id)
            except KeyError:
                continue
            if result["model"] in seen:
                continue
            if needs_review(result):
                reports.append(render(result))
                reported.append(result["model"])
    finally:
        conn.close()
    if not reports:
        return 0
    if seen_file:
        try:
            seen_file.write_text("\n".join(sorted(seen | set(reported))) + "\n", encoding="utf-8")
        except OSError:
            pass
    print(
        "Pedigree: check these inherited licence terms before using the model.\n\n"
        + "\n\n".join(reports)
        + "\n\nShow these terms to the person. Once they accept them, the same call goes through: Pedigree reports each"
        " model once per session.",
        file=sys.stderr,
    )
    return 2


def cmd_build(a: argparse.Namespace) -> int:
    from pedigree.build import build
    from pedigree.lineage import descendants, family_roots, parse_rows
    from pedigree.snapshot import DATASET, read_cache, read_rows, save_cache

    if a.cache and not a.cache.exists():
        save_cache(a.revision, str(a.cache))
    rows = list(read_cache(str(a.cache)) if a.cache else read_rows(a.revision))
    # The snapshot leaves out gated repositories (every meta-llama model): add the owners' models from the Hub API.
    owner_file = ROOT / "sources" / "owner-models.json"
    owner_rows = json.loads(owner_file.read_text(encoding="utf-8")) if owner_file.exists() else []
    in_snapshot = {str(r["modelId"]) for r in rows}
    added = [r for r in owner_rows if r["modelId"] not in in_snapshot]
    parsed = parse_rows(rows + added)
    roots = family_roots(parsed.models, a.family)
    keep = descendants(parsed.models, roots)
    other = json.loads(a.other_names.read_text(encoding="utf-8")) if a.other_names and a.other_names.exists() else {}
    staging = a.out.with_name(a.out.stem + ".staging.rl")
    staging.unlink(missing_ok=True)
    counts = build(
        staging,
        parsed.models,
        keep,
        ROOT / "sources",
        {
            "dataset": DATASET,
            "revision": a.revision,
            "rows": len(rows),
            "owner_rows_added": len(added),
            "families": a.family,
            "roots": len(roots),
            "self_loops": parsed.self_loops,
            "built": dt.date.today().isoformat(),
        },  # fmt: skip
        other,
    )
    # Bulk loading leaves a large write-ahead log in the file; `relate clone` writes a compact copy of the same graph.
    cli = a.relate or shutil.which("relate")
    a.out.unlink(missing_ok=True)
    if cli:
        subprocess.run([cli, "clone", str(staging), str(a.out)], check=True, env={**os.environ, "DO_NOT_TRACK": "1"})
        staging.unlink()
    else:
        staging.rename(a.out)
    print(json.dumps({"rows": len(rows), "roots": len(roots), "bytes": a.out.stat().st_size, **counts}))
    return 0


def cmd_mcp(a: argparse.Namespace) -> int:
    from pedigree.mcp_server import run

    run(a.store)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="pedigree", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    s = sub.add_parser("check", help="a model's pedigree")
    s.add_argument("model")
    s.add_argument("--store", type=Path, default=DEFAULT_STORE)
    s.add_argument("--json", action="store_true")
    s.set_defaults(handler=cmd_check)
    s = sub.add_parser("hook", help="run as a coding-agent PreToolUse hook")
    s.add_argument("--store", type=Path, default=DEFAULT_STORE)
    s.set_defaults(handler=cmd_hook)
    s = sub.add_parser("build", help="write the lineage graph from a pinned snapshot")
    s.add_argument("--revision", required=True, help="the dataset commit to read")
    s.add_argument("--out", type=Path, default=DEFAULT_STORE)
    s.add_argument("--family", action="append", default=None, help="an owner whose models are family roots")
    s.add_argument("--other-names", type=Path, default=ROOT / "sources" / "other-licence-names.json")
    s.add_argument("--relate", help="the relate CLI, to compact the result (default: relate on the PATH)")
    s.add_argument(
        "--cache", type=Path, help="a local Parquet copy of the snapshot's lineage columns (made if missing)"
    )
    s.set_defaults(handler=cmd_build)
    s = sub.add_parser("mcp", help="serve the checks over MCP (stdio)")
    s.add_argument("--store", type=Path, default=DEFAULT_STORE)
    s.set_defaults(handler=cmd_mcp)
    return ap


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    if getattr(a, "family", None) is None and a.command == "build":
        a.family = FAMILIES
    code: int = a.handler(a)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
