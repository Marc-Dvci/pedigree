"""Find the Hugging Face model ids a command or a piece of code is about to download.

Used by the coding-agent hook: before a Bash command runs, or code lands in a file, every model id it names is checked.
Covers `from_pretrained`, `pipeline(model=...)`, `snapshot_download`, `hf_hub_download`, `hf download`,
`huggingface-cli download` (options before the repository id included), `vllm serve`, `ollama run hf.co/...` and
`llama.cpp -hf`. When code calls one of the loaders, every quoted `author/name` string in it counts too, so
`MODEL_ID = "..."` then `from_pretrained(MODEL_ID)` is found; the hook skips ids that are not models in the graph.
"""

from __future__ import annotations

import re

_ID = r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*"
_PATTERNS = [
    rf"""from_pretrained\(\s*["']({_ID})["']""",
    rf"""pipeline\([^)]*?model\s*=\s*["']({_ID})["']""",
    rf"""snapshot_download\(\s*(?:repo_id\s*=\s*)?["']({_ID})["']""",
    rf"""hf_hub_download\(\s*(?:repo_id\s*=\s*)?["']({_ID})["']""",
    rf"""\bvllm\s+serve\s+({_ID})""",
    rf"""\bollama\s+(?:run|pull)\s+hf\.co/({_ID})""",
    rf"""(?:^|\s)-hf(?:r)?\s+({_ID})""",
    rf"""huggingface\.co/({_ID})""",
]
_COMPILED = [re.compile(p) for p in _PATTERNS]
_LOADER = re.compile(r"\b(?:from_pretrained|pipeline|snapshot_download|hf_hub_download)\s*\(")
_QUOTED = re.compile(rf"""["']({_ID})["']""")
_NOT_MODELS = {"datasets", "spaces", "api", "docs", "blog", "settings", "papers", "learn"}
# `hf download` and `huggingface-cli download`, up to the end of the command.
_DOWNLOAD = re.compile(r"\b(?:hf|huggingface-cli)\s+download\b([^\n;&|]*)")
# Their options that take a value: the value is not the repository id.
_VALUE_OPTIONS = {
    "--repo-type",
    "--revision",
    "--include",
    "--exclude",
    "--cache-dir",
    "--local-dir",
    "--local-dir-use-symlinks",
    "--token",
    "--max-workers",
}


def _download_ids(text: str) -> list[str]:
    """The repository of each `hf download`: its first argument that is not an option, unless it is not a model."""
    ids: list[str] = []
    for match in _DOWNLOAD.finditer(text):
        tokens = match.group(1).split()
        repo, repo_type, i = "", "model", 0
        while i < len(tokens):
            name, eq, value = tokens[i].partition("=")
            if name.startswith("-"):
                if name in _VALUE_OPTIONS and not eq:
                    i += 1
                    value = tokens[i] if i < len(tokens) else ""
                if name == "--repo-type":
                    repo_type = value.strip("\"'")
            elif not repo:
                repo = tokens[i].strip("\"'")
            i += 1
        if repo_type == "model" and re.fullmatch(_ID, repo):
            ids.append(repo)
    return ids


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
    for model_id in _download_ids(text):
        if model_id not in found:
            found.append(model_id)
    if _LOADER.search(text):  # an id held in a variable or a constant that a loader is given
        for match in _QUOTED.finditer(text):
            model_id = match.group(1).rstrip(".")
            if model_id.split("/", 1)[0].lower() not in _NOT_MODELS and model_id not in found:
                found.append(model_id)
    order = {m: text.find(m) for m in found}
    return sorted(found, key=lambda m: order[m])
