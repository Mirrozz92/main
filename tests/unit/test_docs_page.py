"""Smoke test for the custom /docs HTML page."""

from __future__ import annotations

from src.api.v1.routes.docs_page import _BASE_URL, _HTML

_ENDPOINT_SECTIONS = [
    "me",
    "request-op",
    "check",
    "check-task",
    "history",
    "stats",
    "webhook-configure",
    "webhooks",
]


def test_docs_render_is_complete() -> None:
    html = _HTML.replace("__BASE__", _BASE_URL)
    # placeholder fully substituted
    assert "__BASE__" not in html
    # every documented endpoint has both a section and a matching nav link
    for sid in _ENDPOINT_SECTIONS:
        assert f'id="{sid}"' in html, f"missing section #{sid}"
        assert f'href="#{sid}"' in html, f"missing nav link #{sid}"
    # tags are balanced
    assert html.count("<section") == html.count("</section>")
