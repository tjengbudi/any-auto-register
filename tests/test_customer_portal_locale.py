"""customer_portal_api locale resolution unit tests.

Covers `customer_portal_api.app.deps.parse_accept_language` (pure parser,
no app boot needed) and `get_portal_locale` (the `Depends()` wrapper) per
the story's I/O & Edge-Case Matrix.
"""
from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from customer_portal_api.app.deps import get_portal_locale, parse_accept_language


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("en-US,en;q=0.9,zh;q=0.8", "en"),
        ("*", "zh"),
        ("*;q=0.5,en;q=0.9", "en"),
        (None, "zh"),
        ("", "zh"),
        ("!!!, en;q=abc", "en"),
        ("fr-FR,de;q=0.9", "zh"),
        ("EN-us", "en"),
        # RFC 7231's `weight = OWS ";" OWS "q=" qvalue` permits whitespace
        # around ";" and "=" -- a literal ";q=" substring match would miss this.
        ("en; q=0.9, zh;q=0.5", "en"),
        # The "q" directive name is case-insensitive.
        ("en;Q=0.9, zh;q=0.5", "en"),
        # A wildcard that outranks every explicit candidate still resolves to
        # zh -- pins the intended precedence (AC: "* resolves to zh") against
        # the case where a real candidate is merely present, not winning.
        ("*;q=1.0,en;q=0.5", "zh"),
        # A duplicate q= param on one candidate: only the first is honored.
        ("en;q=0.9;q=0.1", "en"),
        # Out-of-range/negative q values are treated as if unset (weight 1.0),
        # not accepted at face value.
        ("zh;q=-1", "zh"),
        ("fr;q=5,en;q=0.5", "en"),
    ],
)
def test_parse_accept_language_matrix(header, expected):
    assert parse_accept_language(header) == expected


def test_parse_accept_language_never_raises_on_assorted_garbage():
    for header in (",", ";q=", "en;q=", "  ,  ", "en;q=nan", "en;q=inf"):
        # Only asserting it returns a string without raising -- exact value
        # for these off-matrix inputs is not part of the contract.
        assert isinstance(parse_accept_language(header), str)


def test_get_portal_locale_reads_header_through_a_real_request():
    """Proves get_portal_locale reads the header via FastAPI/Starlette's own
    header parsing, not just the pure function tested in isolation above."""

    async def endpoint(request):
        return JSONResponse({"locale": get_portal_locale(request)})

    app = Starlette(routes=[Route("/locale", endpoint)])
    client = TestClient(app)

    resp = client.get("/locale", headers={"Accept-Language": "en-US,en;q=0.9,zh;q=0.8"})
    assert resp.status_code == 200
    assert resp.json() == {"locale": "en"}

    resp_absent = client.get("/locale")
    assert resp_absent.status_code == 200
    assert resp_absent.json() == {"locale": "zh"}
