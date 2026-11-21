"""Finding the model ids a command or code would download."""

from __future__ import annotations

import pytest

from pedigree.detect import model_ids


@pytest.mark.parametrize(
    ("text", "ids"),
    [
        (
            'AutoModelForCausalLM.from_pretrained("NousResearch/Hermes-3-Llama-3.1-8B")',
            ["NousResearch/Hermes-3-Llama-3.1-8B"],
        ),
        ("pipeline('text-generation', model='Qwen/Qwen2.5-7B-Instruct')", ["Qwen/Qwen2.5-7B-Instruct"]),
        (
            'hf download bartowski/Meta-Llama-3.1-8B-Instruct-GGUF --include "*Q4_K_M*"',
            ["bartowski/Meta-Llama-3.1-8B-Instruct-GGUF"],
        ),
        ("huggingface-cli download mistralai/Mistral-7B-v0.1", ["mistralai/Mistral-7B-v0.1"]),
        ("ollama run hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF:Q4_K_M", ["bartowski/Llama-3.2-1B-Instruct-GGUF"]),
        (
            "vllm serve deepseek-ai/DeepSeek-R1-Distill-Llama-8B --port 8000",
            ["deepseek-ai/DeepSeek-R1-Distill-Llama-8B"],
        ),
        ("llama-server -hf ggml-org/gemma-3-1b-it-GGUF", ["ggml-org/gemma-3-1b-it-GGUF"]),
        ('snapshot_download(repo_id="google/gemma-2-9b-it")', ["google/gemma-2-9b-it"]),
        ("https://huggingface.co/meta-llama/Llama-3.1-8B", ["meta-llama/Llama-3.1-8B"]),
    ],
)
def test_each_download_form_is_found(text: str, ids: list[str]) -> None:
    assert model_ids(text) == ids


def test_options_before_the_repository_id_are_skipped() -> None:
    hermes = ["NousResearch/Hermes-3-Llama-3.1-8B"]
    assert model_ids("hf download --local-dir models/hermes NousResearch/Hermes-3-Llama-3.1-8B") == hermes
    assert model_ids("huggingface-cli download --repo-type model --quiet NousResearch/Hermes-3-Llama-3.1-8B") == hermes
    assert model_ids('hf download --revision main "NousResearch/Hermes-3-Llama-3.1-8B" config.json') == hermes
    assert model_ids("hf download --repo-type=dataset librarian-bots/model_cards_with_metadata") == []


def test_dataset_and_space_links_are_not_models() -> None:
    assert model_ids("https://huggingface.co/datasets/foo/bar https://huggingface.co/spaces/a/b") == []


def test_a_command_without_a_download_finds_nothing() -> None:
    assert model_ids("git status && pytest -q") == []


def test_ids_come_back_once_in_order_of_mention() -> None:
    text = 'from_pretrained("b/two")\nfrom_pretrained("a/one")\nfrom_pretrained("b/two")'
    assert model_ids(text) == ["b/two", "a/one"]


def test_an_id_held_in_a_constant_that_a_loader_is_given_is_found() -> None:
    code = 'MODEL_ID = "NousResearch/Hermes-3-Llama-3.1-8B"\nmodel = AutoModelForCausalLM.from_pretrained(MODEL_ID)\n'
    assert model_ids(code) == ["NousResearch/Hermes-3-Llama-3.1-8B"]


def test_a_quoted_id_without_a_loader_call_is_not_a_download() -> None:
    assert model_ids('README = "see NousResearch/Hermes-3-Llama-3.1-8B for details"') == []
