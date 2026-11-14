# A coding agent and the pre-download hook

A real session, 14 November 2026: Claude Code, run headless in a clone of this repository with its
[`.claude/settings.json`](../.claude/settings.json) hook, was asked:

> Our product's chat feature will run NousResearch/Hermes-3-Llama-3.1-8B. Write serve.py that loads it with transformers
> (AutoModelForCausalLM.from_pretrained and AutoTokenizer.from_pretrained) and exposes a generate(prompt) function.

The agent's write to `serve.py` (excerpt):

```python
MODEL_ID = "NousResearch/Hermes-3-Llama-3.1-8B"


@lru_cache(maxsize=1)
def _load() -> tuple[PreTrainedTokenizerBase, PreTrainedModel]:
    """Load the tokenizer and model once, on first use."""
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        torch_dtype=torch.bfloat16,
        device_map="auto",
    )
    model.eval()
    return tokenizer, model
```

The hook ran before the file was written and returned:

```text
Pedigree: check these inherited licence terms before using the model.

NousResearch/Hermes-3-Llama-3.1-8B: declares llama3
  Inherits llama3.1 from meta-llama/Llama-3.1-8B
    path: NousResearch/Hermes-3-Llama-3.1-8B -> meta-llama/Llama-3.1-8B
    attribution: clause 1.b.i(B): prominently display "Built with Llama" on a related website, user interface, blogpost, about page, or product documentation
    naming: clause 1.b.i: include "Llama" at the beginning of any such AI model name
    notice: clause 1.b.i(A), 1.b.iii: provide a copy of this Agreement with any such Llama Materials
    use_policy: clause 1.b.iv: adhere to the Acceptable Use Policy for the Llama Materials
    user_threshold: clause 2: greater than 700 million monthly active users ... you must request a license from Meta
  Declared terms differ from upstream terms: attribution, naming
  Name: llama3.1 clause 1.b.i asks derivative models to begin with 'Llama'
```

The agent answered (excerpt):

> I haven't written `serve.py` yet. The repo's Pedigree hook blocked the write because the file names this model, and the hook wants the inherited licence terms reviewed first.
>
> Reply "go ahead" once you've accepted these terms and I'll write it, or tell me if you'd rather pick a different model. You'll probably have to approve the write in the hook's prompt too.
