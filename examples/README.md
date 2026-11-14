# Examples

Outputs on the committed graph, each with the command that produced it.

| Example | Command | Output |
|---|---|---|
| A fine-tune that declares an earlier Llama licence | `python -m pedigree check NousResearch/Hermes-3-Llama-3.1-8B` | [`check-nousresearch_hermes-3-llama-3.1-8b.txt`](check-nousresearch_hermes-3-llama-3.1-8b.txt) |
| A model below a research-only licence | `python -m pedigree check Comfy-Org/Qwen-Image-2.1` | [`check-comfy-org_qwen-image-2.1.txt`](check-comfy-org_qwen-image-2.1.txt) |
| Two licences in one family tree | `python -m pedigree check jinaai/jina-embeddings-v5-text-small-retrieval` | [`check-jinaai_jina-embeddings-v5-text-small-retrieval.txt`](check-jinaai_jina-embeddings-v5-text-small-retrieval.txt) |
| The coding-agent hook before `hf download` | `python -m pedigree hook` with the agent's tool call on stdin | [`hook-hf-download.txt`](hook-hf-download.txt) |
| A coding agent stopped before it writes code that loads a model | Claude Code, headless, in a clone of the repository | [`agent-session.md`](agent-session.md) |
