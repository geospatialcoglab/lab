"""Non-destructiveness under failure (Task 5.6, Property 3) and fetch retry /
empty-result handling (Task 5.7).

Property 3 (Req 3.9, 3.10, 5.1, 5.2, 5.5): on retrieval failure and on
below-threshold results, main() returns non-zero AND publications.html bytes
are unchanged.
Task 5.7 (Req 3.2, 3.10, 5.5, 5.6): the retry loop makes exactly max_retries
attempts then raises RetrievalError; a zero-record success raises
BelowThresholdError via the threshold guard / main.
"""

from __future__ import annotations

import shutil
import sys
import types
from pathlib import Path

import pytest

from scripts import generate_publications as gp
from tests.conftest import FakeScholarly, make_author, make_record

_SRC = Path(__file__).resolve().parent.parent / "publications.html"


def _install(monkeypatch, fake):
    fake_mod = types.ModuleType("scholarly")
    fake_mod.scholarly = fake
    monkeypatch.setitem(sys.modules, "scholarly", fake_mod)
    return fake


def _always_raise(author_id):
    raise RuntimeError("simulated Scholar block / CAPTCHA")


def _tmp_html(tmp_path):
    dst = tmp_path / "publications.html"
    shutil.copyfile(_SRC, dst)
    return dst


_FAST_ARGS = ["--max-retries", "3", "--attempt-timeout", "5",
              "--request-timeout", "1"]


# --- 5.6 Property 3: non-destructiveness under failure -------------------

def test_retrieval_failure_is_nonzero_and_nondestructive(tmp_path, monkeypatch):
    """scholarly always raising -> main() returns non-zero, file unchanged."""
    html_file = _tmp_html(tmp_path)
    before = html_file.read_bytes()

    _install(monkeypatch, FakeScholarly(on_search=_always_raise))

    rc = gp.main(_FAST_ARGS + ["--html-file", str(html_file)])

    assert rc != 0
    assert html_file.read_bytes() == before  # no write on failure


def test_below_threshold_is_nonzero_and_nondestructive(tmp_path, monkeypatch):
    """Zero Scholar records -> main() returns non-zero, file unchanged."""
    html_file = _tmp_html(tmp_path)
    before = html_file.read_bytes()

    _install(monkeypatch, FakeScholarly(author=make_author([])))

    rc = gp.main(_FAST_ARGS + ["--html-file", str(html_file)])

    assert rc != 0
    assert html_file.read_bytes() == before


def test_below_custom_threshold_is_nondestructive(tmp_path, monkeypatch):
    """One record but min-threshold 5 -> non-zero, file unchanged."""
    html_file = _tmp_html(tmp_path)
    before = html_file.read_bytes()

    records = [make_record(title="Only One", author="A", pub_year="2024",
                           pub_url="https://example.org/one")]
    _install(monkeypatch, FakeScholarly(author=make_author(records)))

    rc = gp.main(_FAST_ARGS + ["--html-file", str(html_file),
                               "--min-threshold", "5"])

    assert rc != 0
    assert html_file.read_bytes() == before


# --- 5.7 fetch retry + empty-result handling -----------------------------

def test_fetch_makes_exactly_max_retries_attempts(monkeypatch):
    """Every attempt raises -> exactly max_retries search calls, then RetrievalError."""
    fake = _install(monkeypatch, FakeScholarly(on_search=_always_raise))

    with pytest.raises(gp.RetrievalError):
        gp.fetch_publications("Xu5F1CAAAAAJ", max_retries=3,
                              request_timeout=1, attempt_timeout=5)

    assert fake.search_calls == 3


@pytest.mark.parametrize("retries", [1, 2, 5])
def test_fetch_attempt_count_matches_max_retries(monkeypatch, retries):
    fake = _install(monkeypatch, FakeScholarly(on_search=_always_raise))

    with pytest.raises(gp.RetrievalError):
        gp.fetch_publications("Xu5F1CAAAAAJ", max_retries=retries,
                              request_timeout=1, attempt_timeout=5)

    assert fake.search_calls == retries


def test_zero_record_success_raises_below_threshold(monkeypatch):
    """A successful fetch that returns zero records trips the threshold guard."""
    _install(monkeypatch, FakeScholarly(author=make_author([])))

    raw = gp.fetch_publications("Xu5F1CAAAAAJ", max_retries=1,
                                request_timeout=1, attempt_timeout=5)
    pubs = gp.normalize(raw)
    assert pubs == []
    with pytest.raises(gp.BelowThresholdError):
        gp.check_threshold(pubs, 1)


def test_successful_fetch_returns_records(monkeypatch):
    """A well-formed profile fetch yields normalize-shaped records."""
    records = [
        make_record(title="Paper One", author="A and B", pub_year="2022",
                    journal="J", volume="1", pages="1-2",
                    pub_url="https://example.org/1"),
        make_record(title="Paper Two", author="C", pub_year="2020",
                    doi="10.1000/two"),
    ]
    _install(monkeypatch, FakeScholarly(author=make_author(records)))

    raw = gp.fetch_publications("Xu5F1CAAAAAJ", max_retries=1,
                                request_timeout=1, attempt_timeout=5)
    pubs = gp.normalize(raw)
    assert len(pubs) == 2
    titles = {p.title for p in pubs}
    assert titles == {"Paper One", "Paper Two"}


def test_successful_run_writes_and_exits_zero(tmp_path, monkeypatch):
    """Above-threshold fetch injects and returns 0; file changes from original."""
    html_file = _tmp_html(tmp_path)
    before = html_file.read_bytes()

    records = [make_record(title="A New Paper", author="A and B",
                           pub_year="2099", pub_url="https://example.org/new")]
    _install(monkeypatch, FakeScholarly(author=make_author(records)))

    rc = gp.main(_FAST_ARGS + ["--html-file", str(html_file)])

    assert rc == 0
    after = html_file.read_bytes()
    assert after != before
    assert b"A New Paper" in after
