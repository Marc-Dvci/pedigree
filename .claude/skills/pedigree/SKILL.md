---
name: pedigree
description: Check which licence terms an open model inherits from the models it was built on. Use before downloading, recommending or shipping a Hugging Face model (from_pretrained, pipeline, hf download, vllm serve, ollama run hf.co/...), and when asked whether a fine-tune, adapter, merge or quantisation can be used commercially or what it must credit.
---

# Pedigree

Pedigree holds the family tree of open models on Hugging Face as a Relate graph in `pedigree.rl`: which model each one
was fine-tuned, adapted, merged or quantised from, the licence each declares, and the obligations each licence passes
to derivatives, with the clause and its source.

## Tools (MCP server `pedigree`)

| Question | Tool |
|---|---|
| What does this model inherit, and from whom? | `check_model(model_id)` |
| Which model ids match a name? | `find_models(text)` |
| Anything else about the graph | `get_schema()`, then `read_cypher(query)` (read-only) |

Without the MCP server: `python -m pedigree check <model id>`.

## Rules

1. Before writing code or running a command that downloads a model, call `check_model` for it.
2. Report each inherited licence with the ancestor that declares it, the path, and the clause the tool returns. Quote
   the clause; never paraphrase a licence from memory.
3. Where the declared licence differs from upstream terms, say "declared terms differ from upstream terms" and list
   the obligations. Do not say that anyone broke a licence.
4. A naming finding means the licence asks derivative models to begin with a prefix (Llama 3.1 and later: "Llama").
5. The graph is a snapshot of the Hub; `get_schema` gives its date and revision.
