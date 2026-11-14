"""Agent evaluation: which licences' terms does a model inherit? One model answers in two ways.

    python experiments/agent_eval.py freeze            # choose the models and write the answers from the graph
    python experiments/agent_eval.py cards             # fetch each model's card from the Hub (the baseline's input)
    python experiments/agent_eval.py run --repeats 3   # ask the model (needs DASHSCOPE_API_KEY or ~/.bailian)
    python experiments/agent_eval.py grade             # grade the recorded answers (no key needed)

- **card**: the model reads the model's own Hugging Face card, as an engineer or an agent would before downloading.
- **tools**: the model calls the Pedigree tools (the MCP server's tools, run in process on Relate).

The models are chosen by a fixed rule: under each licence with obligations, the most downloaded third-party models
whose declared licence differs from that licence. Answers come from the graph and are frozen before any model runs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import relate  # noqa: E402

from pedigree.checks import MAX_DEPTH, check, rows  # noqa: E402
from pedigree.mcp_server import build_server  # noqa: E402

OUT = ROOT / "evidence" / "agent-eval"
STORE = ROOT / "pedigree.rl"
MODEL = "qwen3.8-flash"
OWNERS = ["meta-llama", "google", "Qwen", "mistralai", "deepseek-ai"]
PER_LICENCE = 2
MAX_TOOL_ROUNDS = 8
SYSTEM = (
    "You answer questions about the licences of open AI models on Hugging Face. A model inherits the terms of a "
    "licence when a model it was fine-tuned, adapted, merged or quantised from (directly or further up its family "
    "tree) declares that licence. Use Hugging Face licence ids such as llama3.1, gemma, apache-2.0, mit, qwen. "
    'Reply with JSON only, as {"answer": [list of licence ids]}.'
)


def choose(conn: relate.Connection) -> list[str]:
    licences = [
        r["id"]
        for r in rows(
            conn,
            "MATCH (l:Licence)-[:REQUIRES]->(o:Obligation) WHERE o.kind <> 'notice' RETURN DISTINCT l.id AS id ORDER BY id",
        )
    ]
    chosen: list[str] = []
    for licence in licences:
        found = rows(
            conn,
            f"MATCH (:Licence {{id: $l}})<-[:DECLARES]-(a:Model) "
            f"MATCH p = ANY SHORTEST (a)<-[:DERIVED_FROM]-{{1,{MAX_DEPTH}}}(m:Model) "
            "WHERE NOT m.author IN $owners AND m.in_snapshot AND coalesce(m.licence, 'none') <> $l "
            "WITH DISTINCT m.id AS id, m.downloads AS d ORDER BY d DESC, id LIMIT $n RETURN id",
            {"l": licence, "owners": OWNERS, "n": PER_LICENCE},
        )
        chosen += [r["id"] for r in found if r["id"] not in chosen]
    return chosen


def freeze() -> None:
    conn = relate.connect(str(STORE), read_only=True)
    try:
        items = []
        for model_id in choose(conn):
            result = check(conn, model_id)
            items.append(
                {
                    "id": model_id,
                    "question": f"Which licences' terms does the Hugging Face model {model_id} inherit from the models "
                    "it was built on? List the licences declared by its ancestors, not its own.",
                    "answer": result["upstream_licences"],
                    "declared": result["declared"],
                }
            )
    finally:
        conn.close()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "questions.json").write_text(json.dumps(items, indent=2) + "\n", encoding="utf-8")
    print(f"{len(items)} questions")


def fetch_cards() -> None:
    items = json.loads((OUT / "questions.json").read_text(encoding="utf-8"))
    cards: dict[str, str] = {}
    for item in items:
        url = f"https://huggingface.co/{item['id']}/raw/main/README.md"
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers={"User-Agent": "pedigree-eval"}), timeout=60
            ) as r:
                cards[item["id"]] = r.read().decode("utf-8", "replace")[:30_000]
        except OSError as exc:
            cards[item["id"]] = f"(card not available: {exc})"
        time.sleep(0.5)
    (OUT / "cards.json").write_text(json.dumps(cards, indent=2) + "\n", encoding="utf-8")
    print(f"{len(cards)} cards")


def credentials() -> tuple[str, str]:
    key = os.environ.get("DASHSCOPE_API_KEY")
    base = os.environ.get("DASHSCOPE_BASE_URL", "https://dashscope-intl.aliyuncs.com")
    if not key:
        data = json.loads((Path.home() / ".bailian" / "config.json").read_text(encoding="utf-8"))
        key, base = data["api_key"], data.get("base_url", base)
    return key, base.rstrip("/") + "/compatible-mode/v1/chat/completions"


def chat(url: str, key: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None) -> dict[str, Any]:
    body: dict[str, Any] = {"model": MODEL, "messages": messages, "temperature": 0}
    if tools:
        body["tools"] = tools
    data = json.dumps(body).encode()
    for attempt in range(4):
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {key}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=600) as response:
                result: dict[str, Any] = json.load(response)
            return result
        except (TimeoutError, OSError):
            if attempt == 3:
                raise
            time.sleep(10 * (attempt + 1))  # a slow or dropped call is retried; the request is the same
    raise RuntimeError("unreachable")


def tools_and_runner() -> tuple[list[dict[str, Any]], Any]:
    server = build_server(STORE)
    manager = server._tool_manager  # noqa: SLF001 - the tools exactly as the MCP server registers them
    specs, fns = [], {}
    for tool in manager.list_tools():
        specs.append(
            {
                "type": "function",
                "function": {"name": tool.name, "description": tool.description, "parameters": tool.parameters},
            }
        )
        fns[tool.name] = tool.fn

    def run(name: str, arguments: dict[str, Any]) -> str:
        try:
            return json.dumps(fns[name](**arguments), default=str)[:40_000]
        except Exception as exc:  # the model sent bad arguments: tell it, as the MCP server would
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})

    return specs, run


def ask(
    mode: str, item: dict[str, Any], card: str, url: str, key: str, specs: list[dict[str, Any]], run: Any
) -> dict[str, Any]:
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM}]
    if mode == "card":
        messages.append(
            {"role": "user", "content": f"The model card of {item['id']}:\n\n{card}\n\nQuestion: {item['question']}"}
        )
    else:
        messages.append({"role": "user", "content": item["question"]})
    calls: list[dict[str, Any]] = []
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    for _ in range(MAX_TOOL_ROUNDS + 1):
        reply = chat(url, key, messages, specs if mode == "tools" else None)
        for k in usage:
            usage[k] += int(reply.get("usage", {}).get(k, 0))
        message = reply["choices"][0]["message"]
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            return {"text": message.get("content") or "", "tool_calls": calls, "usage": usage}
        messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": tool_calls})
        for call in tool_calls:
            try:
                arguments = json.loads(call["function"].get("arguments") or "{}")
            except ValueError:
                arguments = {}
            calls.append({"name": call["function"]["name"], "arguments": arguments})
            messages.append(
                {"role": "tool", "tool_call_id": call["id"], "content": run(call["function"]["name"], arguments)}
            )
    return {"text": "", "tool_calls": calls, "usage": usage}


def parse(text: str) -> Any:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0)).get("answer")
    except (ValueError, AttributeError):
        return None


def correct(truth: list[str], given: Any) -> bool:
    return isinstance(given, list) and {str(x).strip().lower() for x in given} == {t.lower() for t in truth}


def grade(items: list[dict[str, Any]], runs: list[dict[str, Any]]) -> dict[str, Any]:
    truth = {i["id"]: i for i in items}
    table: dict[str, dict[str, Any]] = {}
    for r in runs:
        row = table.setdefault(r["mode"], {"answers": 0, "correct": 0, "tool_calls": 0, "prompt_tokens": 0})
        row["answers"] += 1
        row["correct"] += correct(truth[r["id"]]["answer"], parse(r["text"]))
        row["tool_calls"] += len(r["tool_calls"])
        row["prompt_tokens"] += r["usage"]["prompt_tokens"]
    for row in table.values():
        row["share"] = round(row["correct"] / row["answers"], 3) if row["answers"] else None
    return table


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["freeze", "cards", "run", "grade"])
    ap.add_argument("--repeats", type=int, default=3)
    a = ap.parse_args()
    if a.step == "freeze":
        freeze()
        return
    if a.step == "cards":
        fetch_cards()
        return
    items = json.loads((OUT / "questions.json").read_text(encoding="utf-8"))
    rfile = OUT / "runs.jsonl"
    if a.step == "run":
        cards = json.loads((OUT / "cards.json").read_text(encoding="utf-8"))
        key, url = credentials()
        specs, run = tools_and_runner()
        done = set()
        if rfile.exists():  # resume: answers already recorded are kept
            for line in rfile.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    done.add((r["id"], r["mode"], r["repeat"]))
        with rfile.open("a", encoding="utf-8") as sink:
            for repeat in range(a.repeats):
                for mode in ("card", "tools"):
                    for item in items:
                        if (item["id"], mode, repeat) in done:
                            continue
                        started = time.time()
                        result = ask(mode, item, cards.get(item["id"], ""), url, key, specs, run)
                        sink.write(json.dumps({"id": item["id"], "mode": mode, "repeat": repeat, "model": MODEL,
                                               "seconds": round(time.time() - started, 1), **result}) + "\n")  # fmt: skip
                        sink.flush()
                        print(item["id"], mode, repeat, correct(item["answer"], parse(result["text"])))
    runs = [json.loads(line) for line in rfile.read_text(encoding="utf-8").splitlines() if line.strip()]
    summary = grade(items, runs)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
