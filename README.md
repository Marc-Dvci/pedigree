# Pedigree

**Pedigree tells you which licence terms an open model inherits from the models it was built on, before you or your coding agent download it.**

[![Tests](https://github.com/Marc-Dvci/pedigree/actions/workflows/tests.yml/badge.svg)](https://github.com/Marc-Dvci/pedigree/actions/workflows/tests.yml)
[![Decision core coverage](https://img.shields.io/badge/decision%20core%20coverage-{{COVERAGE}}%25-brightgreen)](#run-it)
[![CodeQL](https://github.com/Marc-Dvci/pedigree/actions/workflows/codeql.yml/badge.svg)](https://github.com/Marc-Dvci/pedigree/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Live page](https://img.shields.io/badge/live-page-1d4ed8)]({{LIVE_URL}})

[![Watch the film: Pedigree](docs/film_thumbnail.jpg)](https://www.youtube.com/watch?v={{VIDEO_ID}})

**[Watch the film](https://www.youtube.com/watch?v={{VIDEO_ID}})** · **[Open the live page]({{LIVE_URL}})**

I led AI use cases for an internal-audit function, and the first question about any open model was what we were allowed to do with it.

| Live page | Built with | Store | Headline result |
|---|---|---|---|
| [Open it]({{LIVE_URL}}) (Relate runs in the tab) | Relate by Neo4j 1.0.1: Python, CLI, MCP, WebAssembly | Single file, [`pedigree.rl`](pedigree.rl) | {{HEADLINE}} |

[For judges](#for-judges) · [See it work](#see-it-work) · [Use case](#use-case) · [How it uses Relate](#how-it-uses-relate) · [Agents](#agents) · [Results](#results) · [Run it](#run-it) · [Where the data lives](#where-the-data-lives)

## For judges

| Criterion | Where it is answered |
|---|---|
| Relate and connected context | [How it uses Relate](#how-it-uses-relate): inherited terms are a variable-length walk up the family tree in Cypher ([`pedigree/checks.py`](pedigree/checks.py)), over {{MODELS}} models in one `.rl` file |
| Functionality and completeness | [See it work](#see-it-work), [Run it](#run-it): command line, MCP server, a pre-download hook for coding agents, browser page, Docker images; {{TEST_COUNT}} tests |
| Usefulness | [Use case](#use-case), [Results](#results): figures on the whole Hugging Face snapshot |
| Documentation and reproducibility | [Run it](#run-it) needs no keys; `python -m pedigree build --revision <commit>` rebuilds the graph from the pinned snapshot |
| Creativity | Licence clauses as graph nodes that flow down `DERIVED_FROM` edges, checked at the moment an agent is about to download |
| AI and agentic capabilities | [Agents](#agents): a hook that stops a coding agent before a download, MCP tools, a skill, and a measured comparison of an agent with and without the graph |

## See it work

{{SEE_IT_WORK}}

## Use case

{{USE_CASE}}

## How it uses Relate

- **Mode:** single file, [`pedigree.rl`](pedigree.rl).
- **Why this mode:** the lineage graph is rebuilt from a daily public snapshot of the Hub, so it ships as one versioned file that a coding-agent hook, CI or a notebook opens read-only, with nothing to install or run.
- **What the graph models:**

```text
(:Model {id, licence, downloads})-[:DERIVED_FROM {relation}]->(:Model)     finetune | adapter | merge | quantized
(:Model)-[:DECLARES]->(:Licence {id, name})
(:Licence)-[:REQUIRES]->(:Obligation {kind, clause, text, source})         attribution, naming, notice, use policy,
                                                                           non-commercial, user threshold
(:Snapshot {dataset, revision, rows})
```

## Agents

{{AGENTS}}

## Results

{{RESULTS}}

## Run it

{{RUN_IT}}

## Where the data lives

| Path | What it holds |
|---|---|
| [`pedigree.rl`](pedigree.rl) | **The persistent Relate store**: one file with every model, its lineage, licences and obligations |
| [`sources/`](sources/) | The obligations table with clause references and sources, and the licence names behind `license:other` |
| [`evidence/`](evidence/) | Population figures and the agent evaluation |
| [`web/data/`](web/data/) | The slice of the graph the browser page loads |

## License

[MIT](LICENSE). The obligations table quotes short passages of each licence it lists, with a link to the full text.
