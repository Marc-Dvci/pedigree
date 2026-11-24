"""Check the graph against its sources: every quoted obligation against its licence text, and every lineage edge on the
agent evaluation's models against the model's live Hugging Face card.

    python experiments/verify_sources.py

1. Quotes. Each row of sources/obligations.csv is fetched from its source URL. A quote passes when every fragment of it
   (fragments are separated by "...") appears in the licence text, word for word, ignoring case, line breaks, markup and
   the shape of quotation marks.
2. Lineage. For each of the 21 models of evidence/agent-eval/questions.json, every DERIVED_FROM edge on the path to each
   ancestor whose licence it inherits is compared with the child's live Hub tags: the edge passes when the child's card
   still names that parent with that relation (`base_model:<relation>:<parent>`).

Writes evidence/sources-check.json.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import relate  # noqa: E402

from pedigree.checks import check  # noqa: E402

AGENT = {"User-Agent": "pedigree-source-check/1.0"}


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers=AGENT)
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 (fixed https URLs from the table)
        data: bytes = response.read()
    return data


def normal(text: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = text.translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "*": " ", "`": " ", "#": " "}))
    return re.sub(r"\s+", " ", text).strip().lower()


def fragments(quote: str) -> list[str]:
    parts = re.split(r"\.\.\.|…", quote)
    return [normal(p).strip(" ,;:.\"'") for p in parts if normal(p).strip(" ,;:.\"'")]


def check_quotes() -> dict[str, Any]:
    with (ROOT / "sources" / "obligations.csv").open(encoding="utf-8", newline="") as handle:
        table = list(csv.DictReader(handle))
    texts: dict[str, str] = {}
    sources = []
    for url in sorted({row["source"] for row in table}):
        data = fetch(url)
        texts[url] = normal(data.decode("utf-8", errors="replace"))
        sources.append({"url": url, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    missing = [
        {"licence": row["licence"], "kind": row["kind"], "clause": row["clause"], "fragment": fragment}
        for row in table
        for fragment in fragments(row["text"])
        if fragment not in texts[row["source"]]
    ]
    failed = {(m["licence"], m["kind"]) for m in missing}
    return {"obligations": len(table), "found": len(table) - len(failed), "missing": missing, "sources": sources}


def live_tags(model_id: str) -> list[str] | None:
    try:
        info = json.loads(fetch(f"https://huggingface.co/api/models/{model_id}"))
    except OSError:
        return None
    return [str(t).lower() for t in info.get("tags", [])]


def check_lineage() -> dict[str, Any]:
    questions = json.loads((ROOT / "evidence" / "agent-eval" / "questions.json").read_text(encoding="utf-8"))
    conn = relate.connect(str(ROOT / "pedigree.rl"), read_only=True)
    edges: dict[tuple[str, str], str] = {}
    try:
        for q in questions:
            result = check(conn, q["id"])
            for item in result["inherited"]:
                chain = item["nearest"]["chain"]
                relations = item["nearest"]["relations"]
                for child, parent, relation in zip(chain, chain[1:], relations, strict=False):
                    edges[(child, parent)] = relation
    finally:
        conn.close()
    differ = []
    tags_of: dict[str, list[str] | None] = {}
    for (child, parent), relation in sorted(edges.items()):
        if child not in tags_of:
            tags_of[child] = live_tags(child)
            time.sleep(0.3)
        tags = tags_of[child]
        if tags is None or f"base_model:{relation}:{parent}".lower() not in tags:
            differ.append({"child": child, "parent": parent, "relation": relation, "card_found": tags is not None})
    return {"models": len(questions), "edges": len(edges), "match": len(edges) - len(differ), "differ": differ}


def main() -> None:
    result = {
        "checked": dt.date.today().isoformat(),
        "quotes": check_quotes(),
        "lineage": check_lineage(),
    }
    out = ROOT / "evidence" / "sources-check.json"
    out.write_bytes((json.dumps(result, indent=2) + "\n").encode("utf-8"))
    q, line = result["quotes"], result["lineage"]
    print(
        f"quotes: {q['found']} of {q['obligations']} found in their source; lineage: {line['match']} of {line['edges']}"
    )


if __name__ == "__main__":
    main()
