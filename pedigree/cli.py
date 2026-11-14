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
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STORE = ROOT / "pedigree.rl"
FAMILIES = ["meta-llama", "google", "Qwen", "mistralai", "deepseek-ai"]


def _connect(store: Path) -> Any:
    import relate

    if not store.exists():
        raise SystemExit(f"no lineage graph at {store}; build it with: python -m pedigree build")
    return relate.connect(str(store), read_only=True)


def render(result: dict[str, Any]) -> str:
    lines = [f"{result['model']}: declares {result['declared'] or 'no licence'}"]
    if not result["inherited"]:
        lines.append("  No ancestor in the graph declares a licence with obligations.")
        return "\n".join(lines)
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
    for n in result["naming"]:
        lines.append(
            f"  Name: {n['licence']} clause {n['clause']} asks derivative models to begin with '{n['prefix']}'"
        )
    if result["non_commercial"]:
        lines.append(
            f"  Non-commercial terms upstream: {', '.join(sorted({u['licence'] for u in result['non_commercial']}))}"
        )
    return "\n".join(lines)


def cmd_check(a: argparse.Namespace) -> int:
    from pedigree.checks import check

    conn = _connect(a.store)
    try:
        try:
            result = check(conn, a.model)
        except KeyError:
            print(f"{a.model} is not in the lineage graph", file=sys.stderr)
            return 2
    finally:
        conn.close()
    print(json.dumps(result, indent=2) if a.json else render(result))
    return 0


def cmd_hook(a: argparse.Namespace) -> int:
    """Claude Code PreToolUse hook: reads the tool call on stdin, reports inherited terms on stderr (exit 2)."""
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
    conn = _connect(a.store)
    reports = []
    try:
        for model_id in ids:
            try:
                result = check(conn, model_id)
            except KeyError:
                continue
            if result["differs"] or result["naming"] or result["non_commercial"]:
                reports.append(render(result))
    finally:
        conn.close()
    if not reports:
        return 0
    print(
        "Pedigree: check these inherited licence terms before using the model.\n\n" + "\n\n".join(reports),
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
    parsed = parse_rows(rows)
    roots = family_roots(parsed.models, a.family)
    keep = descendants(parsed.models, roots)
    other = json.loads(a.other_names.read_text(encoding="utf-8")) if a.other_names and a.other_names.exists() else {}
    counts = build(
        a.out,
        parsed.models,
        keep,
        ROOT / "sources",
        {
            "dataset": DATASET,
            "revision": a.revision,
            "rows": len(rows),
            "families": a.family,
            "roots": len(roots),
            "self_loops": parsed.self_loops,
            "built": dt.date.today().isoformat(),
        },  # fmt: skip
        other,
    )
    print(json.dumps({"rows": len(rows), "roots": len(roots), **counts}))
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
    s.add_argument("--cache", type=Path, help="a local Parquet copy of the snapshot's lineage columns (made if missing)")
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
