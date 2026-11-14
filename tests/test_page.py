"""The browser page, driven in a real Chromium: Relate's WebAssembly build loads the page's slice of the graph in the
tab, and every part of the page answers. Run with `python -m pytest -m e2e` after `playwright install chromium` and
`npm ci` in web/ (axe-core comes from web/node_modules)."""

from __future__ import annotations

import functools
import http.server
import socketserver
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from playwright.sync_api import Page, sync_playwright

pytestmark = pytest.mark.e2e
WEB = Path(__file__).resolve().parents[1] / "web"
AXE = WEB / "node_modules" / "axe-core" / "axe.min.js"


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:
        pass


@pytest.fixture(scope="module")
def base_url() -> Iterator[str]:
    httpd = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(WEB)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/index.html"
    httpd.shutdown()


@pytest.fixture(scope="module")
def browser() -> Iterator[Any]:
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


def open_page(browser: Any, base_url: str, model: str | None = None) -> Page:
    page: Page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(base_url + (f"?model={quote(model)}" if model else ""))
    page.wait_for_selector("body.ready", timeout=60_000)
    return page


@pytest.fixture
def page(browser: Any, base_url: str) -> Iterator[Page]:
    pg = open_page(browser, base_url)
    yield pg
    pg.close()


def test_relate_runs_in_the_tab_on_the_pinned_snapshot(page: Page) -> None:
    status = page.inner_text("#status")
    assert status.startswith("Relate 1.0.1 running in this tab (WebAssembly):")
    assert "from a snapshot of 914,842 Hub model cards (revision be6e076)" in status


def test_the_first_example_shows_which_upstream_terms_the_declared_licence_words_differently(page: Page) -> None:
    verdict = page.inner_text("#verdict")
    assert verdict.startswith("NousResearch/Hermes-3-Llama-3.1-8B")
    assert "Declares llama3. Inherits terms from llama3.1." in verdict
    assert "Upstream terms the declared licence does not carry: Attribution, Name." in verdict


def test_a_merge_family_shows_four_generations_and_a_failed_naming_clause(page: Page) -> None:
    page.click("#examples button >> text=zerofata/L3.3-GeneticLemonade-Final-v2-70B")
    assert "Inherits terms from llama3, llama3.1, llama3.3." in page.inner_text("#verdict")
    assert page.locator("#chart .stamp").count() >= 10
    assert page.locator("#chart .more").count() >= 1  # the line goes on past the chart's last generation
    assert "the name does not begin with “Llama 3”" in page.inner_text("#terms")


def test_a_licence_named_only_in_the_card_claims_no_difference_but_shows_the_research_terms(page: Page) -> None:
    page.click("#examples button >> text=Comfy-Org/Qwen-Image-2.1")
    verdict = page.inner_text("#verdict")
    assert "Declares a licence named in its card (Hub id other)." in verdict
    assert "does not carry" not in verdict
    assert "FOR NON-COMMERCIAL PURPOSES ONLY" in page.inner_text("#terms")


def test_a_model_outside_the_pages_slice_points_to_the_command_line(page: Page) -> None:
    page.fill("#model", "nobody/not-a-model")
    page.click("#form button[type=submit]")
    assert "is not in this page's slice of the graph" in page.inner_text("#verdict")


def test_a_link_opens_the_model_it_names_and_a_choice_updates_the_link(browser: Any, base_url: str) -> None:
    pg = open_page(browser, base_url, "jinaai/jina-embeddings-v5-text-small-retrieval")
    assert pg.inner_text("#verdict").startswith("jinaai/jina-embeddings-v5-text-small-retrieval")
    pg.click("#examples button >> text=Comfy-Org/Qwen-Image-2.1")
    assert "model=Comfy-Org%2FQwen-Image-2.1" in pg.url
    pg.close()


def test_the_register_shows_the_population_figures(page: Page) -> None:
    stats = page.inner_text("#stats")
    assert "llama3.1: 12,038 models inherit its terms" in stats
    assert "2,516 declare llama3.1, 4,697 declare another licence, 4,825 declare none." in stats


def test_the_page_has_no_serious_accessibility_violation(page: Page) -> None:
    page.click("#examples button >> text=zerofata/L3.3-GeneticLemonade-Final-v2-70B")
    page.add_script_tag(path=str(AXE))
    result = page.evaluate("axe.run(document, { resultTypes: ['violations'] })")
    serious = [(v["id"], len(v["nodes"])) for v in result["violations"] if v["impact"] in ("serious", "critical")]
    assert serious == []
