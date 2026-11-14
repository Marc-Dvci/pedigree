"""Time the per-model check on the committed graph: the 21 models of the agent evaluation and the page's examples.

    python experiments/timings.py

Each model is checked once to warm the store, then 5 times; evidence/timings.json records the median of each model and,
over all models, the median and the slowest of those medians.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import relate  # noqa: E402

from pedigree.checks import check  # noqa: E402

REPEATS = 5


def main() -> None:
    questions = json.loads((ROOT / "evidence" / "agent-eval" / "questions.json").read_text(encoding="utf-8"))
    examples = json.loads((ROOT / "web" / "data" / "examples.json").read_text(encoding="utf-8"))
    models = list(dict.fromkeys([q["id"] for q in questions] + examples))
    conn = relate.connect(str(ROOT / "pedigree.rl"), read_only=True)
    per_model = {}
    try:
        for model_id in models:
            check(conn, model_id)
            runs = []
            for _ in range(REPEATS):
                started = time.perf_counter()
                check(conn, model_id)
                runs.append((time.perf_counter() - started) * 1000)
            per_model[model_id] = round(statistics.median(runs), 2)
    finally:
        conn.close()
    medians = sorted(per_model.values())
    result = {
        "models": len(per_model),
        "repeats": REPEATS,
        "median_ms": round(statistics.median(medians), 2),
        "slowest_ms": medians[-1],
        "per_model_ms": per_model,
    }
    (ROOT / "evidence" / "timings.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"{result['models']} models: median {result['median_ms']} ms, slowest {result['slowest_ms']} ms")


if __name__ == "__main__":
    main()
