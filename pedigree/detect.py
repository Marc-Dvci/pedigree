"""Find the Hugging Face model ids a command or a piece of code is about to download.

Used by the coding-agent hook: before a Bash command runs, or code lands in a file, every model id it names is checked.
Covers `from_pretrained`, `pipeline(model=...)`, `snapshot_download`, `hf_hub_download`, `hf download`,
`huggingface-cli download`, `vllm serve`, `ollama run hf.co/...` and `llama.cpp -hf`.
"""

from __future__ import annotations

import re

_ID = r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*"
_PATTERNS = [
    rf"""from_pretrained\(\s*["']({_ID})["']""",
    rf"""pipeline\([^)]*?model\s*=\s*["']({_ID})["']""",
    rf"""snapshot_download\(\s*(?:repo_id\s*=\s*)?["']({_ID})["']""",
    rf"""hf_hub_download\(\s*(?:repo_id\s*=\s*)?["']({_ID})["']""",
    rf"""\b(?:hf|huggingface-cli)\s+download\s+({_ID})""",
    rf"""\bvllm\s+serve\s+({_ID})""",
    rf"""\bollama\s+(?:run|pull)\s+hf\.co/({_ID})""",
    rf"""(?:^|\s)-hf(?:r)?\s+({_ID})""",
    rf"""huggingface\.co/({_ID})""",
]
_COMPILED = [re.compile(p) for p in _PATTERNS]
_NOT_MODELS = {"datasets", "spaces", "api", "docs", "blog", "settings", "papers", "learn"}


def model_ids(text: str) -> list[str]:
    """Model ids the text would download, in order of first mention, without duplicates."""
    found: list[str] = []
    for pattern in _COMPILED:
        for match in pattern.finditer(text):
            model_id = match.group(1).rstrip(".")
            model_id = re.sub(r":[A-Za-z0-9_.-]+$", "", model_id)  # ollama quant tags, e.g. ...-GGUF:Q4_K_M
            if model_id.split("/", 1)[0].lower() in _NOT_MODELS:
                continue
            if model_id not in found:
                found.append(model_id)
    order = {m: text.find(m) for m in found}
    return sorted(found, key=lambda m: order[m])
