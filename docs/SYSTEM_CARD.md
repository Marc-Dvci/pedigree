# Pedigree: system card

## Who it is for, and what it is for

Pedigree is for the engineer, the coding agent and the reviewer who decide whether an open model from Hugging Face can
go into a product. It reports which licence terms a model inherits from the models it was built on, from which
ancestor, by which path and under which clause. It reads the family trees that model cards declare for the releases of
Meta Llama, Google, Qwen, Mistral AI and DeepSeek (213,928 models, Hub snapshot of 14 November 2026), and the terms of
14 licences.

## Uses it is built for

- Checking a model before it is downloaded, in a coding agent's loop or in CI.
- Reviewing the models a product already uses.
- Measuring, across the Hub, how inherited terms are declared.

Its findings are terms to review: they point a person to the clause and the licence text. Reading the licence and
deciding remain with that person; the wording on every surface is "declared terms differ from upstream terms". Where the
graph cannot tell, every surface says so. A declared licence it holds no terms for reads "declared terms unknown". Each
ancestor whose card is not in the snapshot, or that sits outside the traced family trees, is named.

## Models and data

| Component | Model or source | Role |
|---|---|---|
| Lineage and licences | `librarian-bots/model_cards_with_metadata`, commit `be6e076`; the Hub API for 775 gated family models | Every model, its parents and its declared licence |
| Obligations | The licence texts, quoted with their source ([`sources/obligations.csv`](../sources/obligations.csv)) | What each licence passes to derivatives |
| Checks | Cypher on Relate by Neo4j 1.2.0 | Decide every finding |
| Agents | Any MCP client; the pre-download hook | Ask and act on the findings |
| Agent evaluation | Qwen 3.8 Flash, Alibaba Cloud Model Studio | Measure answers from the card against answers with the tools |

## Evaluation

- **The checks.** 58 tests build small family trees with the real builder and check every rule: a fine-tune inherits
  every obligation of its ancestors' licences, the nearest ancestor is named with its path, a merge inherits from both
  parents, a quantisation inherits but is not a newly trained model, a licence named only in the card or one the terms
  table does not hold leaves the declared terms unknown, and a base model outside the snapshot or the traced trees is
  named. They cover 99% of the decision core's lines and 96% of its branches.
- **The browser.** The page's code gives the Python answers on 13 of 13 models ([`web/test/parity.mjs`](../web/test/parity.mjs)).
- **The sources.** All 41 quoted obligations are found word for word in the licence texts at their source URLs, and all
  34 lineage edges on the paths of the 21 evaluated models match the models' live Hub cards
  ([`evidence/sources-check.json`](../evidence/sources-check.json)).
- **The agent.** On 21 real models, three times each, Qwen 3.8 Flash named the licences a model inherits as the graph
  does 27 times in 63 from the model's card, and 63 times in 63 with the Pedigree tools. On the 5 models whose family tree
  carries more than one licence: 0 of 15 from the card, 15 of 15 with the tools. The answers come from the graph and
  were committed before the model ran ([`evidence/agent-eval/`](../evidence/agent-eval/)).

## Human oversight

- The obligations table is written by a person from the licence texts and committed before the engine runs.
- The hook reports to the agent and the person, and the download decision stays with them.
- A finding names the clause and links to the licence text.

## How a correction is made

Open an issue with the correction form: the model id, what the graph says, and what the model's card or licence says.
A correction to the obligations table is a pull request to [`sources/obligations.csv`](../sources/obligations.csv); a
lineage correction comes from the model's own card on the Hub at the next snapshot.
