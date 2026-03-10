"""Pytest regression tests for the Search API endpoint.

Run from the project root:
    pytest scripts/test_search.py -v

The backend must be running and reachable at BASE_URL.
Set the EGDC_BASE_URL environment variable to override the default.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("EGDC_BASE_URL", "http://localhost:3000") + "/api/v1/search/"

# ---------------------------------------------------------------------------
# Parameterised test cases — each tuple is (params_dict, test_id)
# ---------------------------------------------------------------------------
SEARCH_CASES = [
    pytest.param(
        {},
        id="no-params-returns-all-published",
    ),
    pytest.param(
        {"q": "carbon", "match_type": "exact"},
        id="exact-match-q-only",
    ),
    pytest.param(
        {"q": "carbon", "match_type": "partial"},
        id="partial-match-q-only",
    ),
    pytest.param(
        {"q": "energy", "match_type": "exact", "sector": "manufacturing"},
        id="exact-q-plus-sector",
    ),
    pytest.param(
        {"q": "energy", "match_type": "exact", "country": "FRA"},
        id="exact-q-plus-country",
    ),
    pytest.param(
        {"q": "energy", "sector": "manufacturing", "country": "FRA"},
        id="q-plus-sector-and-country",
    ),
    # This exact combination was the original crash reproducer.
    pytest.param(
        {
            "q": "fasdfs",
            "sector": "manufacturing",
            "country": "FRA",
            "page": 1,
            "limit": 10,
            "sort_by": "created_date",
            "sort_order": "desc",
            "match_type": "exact",
        },
        id="crash-reproducer-full-param-combo",
    ),
    pytest.param(
        {"page": 1, "limit": 5, "sort_by": "created_date", "sort_order": "desc"},
        id="pagination-sort-by-date-desc",
    ),
    pytest.param(
        {"page": 1, "limit": 5, "sort_by": "title", "sort_order": "asc"},
        id="pagination-sort-by-title-asc",
    ),
    pytest.param(
        {"sector": "manufacturing", "country": "FRA"},
        id="sector-and-country-no-q",
    ),
    pytest.param(
        {
            "q": "renewable",
            "match_type": "exact",
            "sort_by": "created_date",
            "sort_order": "desc",
            "page": 1,
            "limit": 10,
        },
        id="exact-q-with-pagination-and-sort",
    ),
    pytest.param(
        {"q": "renewable", "match_type": "partial", "page": 2, "limit": 5},
        id="partial-q-page-2",
    ),
]


# ---------------------------------------------------------------------------
# Core regression: every valid parameter combination must return HTTP 200
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("params", SEARCH_CASES)
def test_search_returns_200(params):
    """Every valid parameter combination must return HTTP 200."""
    response = requests.get(BASE_URL, params=params, timeout=15)
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. "
        f"Params: {params}. Body: {response.text[:500]}"
    )


# ---------------------------------------------------------------------------
# Response shape: must always contain the pagination envelope
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("params", SEARCH_CASES)
def test_search_response_shape(params):
    """Response must contain the expected pagination envelope keys."""
    response = requests.get(BASE_URL, params=params, timeout=15)
    assert response.status_code == 200, f"Non-200 response: {response.text[:300]}"
    body = response.json()
    assert "total" in body,  "Missing 'total' key in response"
    assert "page" in body,   "Missing 'page' key in response"
    assert "limit" in body,  "Missing 'limit' key in response"
    assert "items" in body,  "Missing 'items' key in response"
    assert isinstance(body["items"], list), "'items' must be a list"


# ---------------------------------------------------------------------------
# Pagination correctness
# ---------------------------------------------------------------------------
def test_search_pagination_consistency():
    """Page 1 and page 2 must not return the same records."""
    r1 = requests.get(BASE_URL, params={"limit": 2, "page": 1}, timeout=15)
    r2 = requests.get(BASE_URL, params={"limit": 2, "page": 2}, timeout=15)
    assert r1.status_code == 200
    assert r2.status_code == 200
    b1, b2 = r1.json(), r2.json()
    ids_page1 = {item["id"] for item in b1["items"]}
    ids_page2 = {item["id"] for item in b2["items"]}
    if b1["total"] > 2 and ids_page2:
        assert ids_page1.isdisjoint(ids_page2), (
            f"Page 1 and page 2 share results: {ids_page1 & ids_page2}"
        )


def test_search_limit_respected():
    """The number of returned items must not exceed the requested limit."""
    for limit in (1, 5, 10):
        r = requests.get(BASE_URL, params={"limit": limit, "page": 1}, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert len(body["items"]) <= limit, (
            f"limit={limit} but got {len(body['items'])} items"
        )


def test_search_page_reflected_in_response():
    """The 'page' field in the response must match the requested page."""
    for page in (1, 2, 3):
        r = requests.get(BASE_URL, params={"page": page, "limit": 5}, timeout=15)
        assert r.status_code == 200
        assert r.json()["page"] == page


# ---------------------------------------------------------------------------
# Sector + country combination (verifies no duplicate-join crash)
# ---------------------------------------------------------------------------
def test_sector_country_q_combination_no_crash():
    """The exact combination that triggered the 500 crash must return 200."""
    params = {
        "q": "fasdfs",
        "sector": "manufacturing",
        "country": "FRA",
        "page": 1,
        "limit": 10,
        "sort_by": "created_date",
        "sort_order": "desc",
        "match_type": "exact",
    }
    response = requests.get(BASE_URL, params=params, timeout=15)
    assert response.status_code == 200, (
        f"Crash-reproducer returned {response.status_code}: {response.text[:500]}"
    )
    body = response.json()
    # A search for a nonsense string must return 0 results, not crash
    assert body["total"] == 0, (
        f"Expected 0 results for nonsense query, got {body['total']}"
    )
