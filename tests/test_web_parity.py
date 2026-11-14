"""The browser page answers as the command line does.

web/test/parity.json holds the Python answers for the page's example models and others in its slice. This test
proves the file matches the Python code on the committed graph; `node web/test/parity.mjs` (CI's web job) proves the
browser code, on Relate's WebAssembly build and the page's slice, gives the same answers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import relate

from pedigree.checks import check

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "web" / "test" / "parity.json"
MODELS = [
    "NousResearch/Hermes-3-Llama-3.1-8B",
    "RedHatAI/Llama-3.2-1B-Instruct-FP8-dynamic",
    "jinaai/jina-embeddings-v5-text-small-retrieval",
    "Comfy-Org/Qwen-Image-2.1",
    "Comfy-Org/ltx-2",
    "casperhansen/llama-3.3-70b-instruct-awq",
    "meta-llama/Llama-3.1-8B-Instruct",
]


def python_answers() -> list[dict[str, Any]]:
    conn = relate.connect(str(ROOT / "pedigree.rl"), read_only=True)
    try:
        out = []
        for model_id in MODELS:
            r = check(conn, model_id)
            out.append(
                {
                    "model": model_id,
                    "declared": r["declared"],
                    "upstream_licences": r["upstream_licences"],
                    "inherited": sorted(
                        [i["licence"], i["kind"], i["nearest"]["ancestor"], i["nearest"]["chain"]]
                        for i in r["inherited"]
                    ),
                    "differs": sorted([d["licence"], d["kind"]] for d in r["differs"]),
                    "naming": sorted([n["licence"], n["prefix"]] for n in r["naming"]),
                }
            )
        return out
    finally:
        conn.close()


def test_the_parity_fixture_matches_the_python_answers() -> None:
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == python_answers()


if __name__ == "__main__":
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(python_answers(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {FIXTURE.relative_to(ROOT)}")
