"""Guard: internal endpoints must not leak into the public OpenAPI schema.

/swagger renders whatever is in the schema, so anything a publisher shouldn't
see (the CryptoBot payment callback, the HTML registration/onboarding forms)
must be marked include_in_schema=False.
"""

from __future__ import annotations

from src.api.app import create_app

_INTERNAL_PATHS = [
    "/cryptobot/webhook",
    "/register",
    "/onboard/{token}",
]

_PUBLIC_PATHS = [
    "/api/v1/me",
    "/api/v1/request-op",
    "/api/v1/check-resource",
    "/api/v1/check-task",
    "/api/v1/stats",
    "/api/v1/webhook/configure",
]


def test_internal_endpoints_absent_from_schema() -> None:
    paths = set(create_app().openapi()["paths"])
    leaked = [p for p in _INTERNAL_PATHS if p in paths]
    assert leaked == [], f"internal endpoints leaked into /swagger: {leaked}"


def test_publisher_endpoints_present_in_schema() -> None:
    paths = set(create_app().openapi()["paths"])
    missing = [p for p in _PUBLIC_PATHS if p not in paths]
    assert missing == [], f"publisher endpoints missing from schema: {missing}"
