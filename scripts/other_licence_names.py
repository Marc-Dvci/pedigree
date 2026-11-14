"""Fetch the licence name behind `license:other` for the family owners' own models, from the Hub API.

    python scripts/other_licence_names.py

Writes sources/other-licence-names.json: model id -> the card's license_name (for example qwen, mrl, deepseek).
Only the owners' models are fetched: they are the roots whose obligations flow down.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OWNERS = ["meta-llama", "google", "Qwen", "mistralai", "deepseek-ai"]


def page(url: str) -> tuple[list[dict[str, object]], str | None]:
    req = urllib.request.Request(url, headers={"User-Agent": "pedigree-build"})
    with urllib.request.urlopen(req, timeout=60) as response:
        data = json.load(response)
        link = response.headers.get("Link") or ""
    nxt = None
    for part in link.split(","):
        if 'rel="next"' in part:
            nxt = part.split(";")[0].strip().strip("<>")
    return data, nxt


def main() -> None:
    names: dict[str, str] = {}
    for owner in OWNERS:
        query = urllib.parse.urlencode({"author": owner, "filter": "license:other", "limit": "1000"})
        url: str | None = f"https://huggingface.co/api/models?{query}&expand[]=cardData"
        while url:
            items, url = page(url)
            for item in items:
                card = item.get("cardData") or {}
                name = card.get("license_name") if isinstance(card, dict) else None
                if name:
                    names[str(item["id"])] = str(name)
        print(owner, sum(1 for k in names if k.split("/")[0] == owner), file=sys.stderr)
    out = ROOT / "sources" / "other-licence-names.json"
    out.write_text(json.dumps(dict(sorted(names.items())), indent=2) + "\n", encoding="utf-8")
    print(f"{len(names)} names -> {out.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
