# Pedigree: system card

## Who it is for, and what it is for

Pedigree is for the engineer, the coding agent and the reviewer who decide whether an open model from Hugging Face can
go into a product. It reports which licence terms a model inherits from the models it was built on, from which
ancestor, by which path and under which clause.

## Uses it is built for

- Checking a model before it is downloaded, in a coding agent's loop or in CI.
- Reviewing the models a product already uses.
- Measuring, across the Hub, how inherited terms are declared.

Its findings point a person to the clause and the licence text. Reading the licence and deciding remain with that
person; the wording on every surface is "declared terms differ from upstream terms".

## Models and data

| Component | Model or source | Role |
|---|---|---|
| Lineage and licences | `librarian-bots/model_cards_with_metadata`, commit `be6e076`; the Hub API for 775 gated family models | Every model, its parents and its declared licence |
| Obligations | The licence texts, quoted with their source ([`sources/obligations.csv`](../sources/obligations.csv)) | What each licence passes to derivatives |
| Checks | Cypher on Relate by Neo4j 1.0.1 | Decide every finding |
| Agents | Any MCP client; the pre-download hook | Ask and act on the findings |
| Agent evaluation | Qwen 3.8 Flash, Alibaba Cloud Model Studio | Measure answers from the card against answers with the tools |

## Evaluation

{{SYSTEM_CARD_EVAL}}

## Human oversight

- The obligations table is written by a person from the licence texts and committed before the engine runs.
- The hook reports to the agent and the person; it does not remove or change any model.
- A finding names the clause and links to the licence text.

## How a correction is made

Open an issue with the correction form: the model id, what the graph says, and what the model's card or licence says.
A correction to the obligations table is a pull request to [`sources/obligations.csv`](../sources/obligations.csv); a
lineage correction comes from the model's own card on the Hub at the next snapshot.
