"""List the family owners' own models from the Hub API, with their tags.

    python scripts/owner_models.py

The model-card snapshot leaves out gated repositories, and every meta-llama model is gated: thousands of fine-tunes
name a Llama model as their base, but the base itself is not a row. The Hub API lists gated models with their tags
(licence and base model), so this file adds the owners' models the snapshot does not hold. Writes
sources/owner-models.json: a list of {modelId, tags, downloads, likes, createdAt}.
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
    rows = []
    for owner in OWNERS:
        query = urllib.parse.urlencode({"author": owner, "limit": "1000"})
        url: str | None = (
            f"https://huggingface.co/api/models?{query}&expand[]=tags&expand[]=downloads&expand[]=likes&expand[]=createdAt"
        )
        count = 0
        while url:
            items, url = page(url)
            for item in items:
                rows.append(
                    {
                        "modelId": item["id"],
                        "tags": item.get("tags") or [],
                        "downloads": item.get("downloads") or 0,
                        "likes": item.get("likes") or 0,
                        "createdAt": item.get("createdAt") or "",
                    }
                )
                count += 1
        print(owner, count, file=sys.stderr)
    out = ROOT / "sources" / "owner-models.json"
    out.write_text(json.dumps(sorted(rows, key=lambda r: str(r["modelId"])), indent=1) + "\n", encoding="utf-8")
    print(f"{len(rows)} models -> {out.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
