"""Shared pytest fixtures/helpers for the Generator_Script test suite.

Puts the repo root on ``sys.path`` so ``scripts.generate_publications`` imports
cleanly regardless of the working directory, and provides helpers for building
fake ``scholarly`` modules and record fixtures. ``scholarly`` is ALWAYS mocked;
no test performs a live Google Scholar call.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

# --- Import path setup ----------------------------------------------------
# Repo root = parent of this tests/ directory. Adding it lets tests do
# ``import scripts.generate_publications as gp``.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.generate_publications as gp  # noqa: E402


@pytest.fixture
def module():
    """The module under test."""
    return gp


# --- scholarly mocking helpers -------------------------------------------
#
# The real module does ``from scholarly import scholarly`` lazily inside
# ``_fetch_once``. To intercept that import we install a fake package module at
# ``sys.modules['scholarly']`` whose ``scholarly`` attribute is our fake
# navigator object exposing ``search_author_id`` and ``fill``.


class FakeScholarly:
    """Stand-in for the ``scholarly.scholarly`` navigator object.

    - ``search_author_id(author_id)`` returns the author dict (or invokes a
      supplied callable, e.g. to raise, to simulate a blocked profile).
    - ``fill(obj, sections=...)`` returns the author (with publications) on the
      first call and echoes each publication on subsequent per-pub calls.

    Call counts are recorded so retry-loop tests can assert attempt counts.
    """

    def __init__(self, author=None, on_search=None, on_fill=None):
        self._author = author
        self._on_search = on_search
        self._on_fill = on_fill
        self.search_calls = 0
        self.fill_calls = 0

    def search_author_id(self, author_id):
        self.search_calls += 1
        if self._on_search is not None:
            return self._on_search(author_id)
        return self._author

    def fill(self, obj, sections=None):
        self.fill_calls += 1
        if self._on_fill is not None:
            return self._on_fill(obj, sections)
        # Default: author fill returns the author unchanged; per-pub fill
        # echoes the publication dict back (it already carries its bib).
        return obj


def install_fake_scholarly(monkeypatch, fake):
    """Register ``fake`` as ``sys.modules['scholarly'].scholarly``.

    Mirrors the real package layout so ``from scholarly import scholarly``
    inside the fetch layer resolves to ``fake``.
    """
    fake_module = types.ModuleType("scholarly")
    fake_module.scholarly = fake
    monkeypatch.setitem(sys.modules, "scholarly", fake_module)
    return fake


@pytest.fixture
def install_scholarly(monkeypatch):
    """Return a helper that installs a FakeScholarly (or raw fake) module."""

    def _install(fake):
        return install_fake_scholarly(monkeypatch, fake)

    return _install


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch):
    """Neutralize retry backoff so fetch-failure tests stay fast."""
    monkeypatch.setattr(gp.time, "sleep", lambda *_a, **_k: None)


def make_author(publications):
    """Build a scholarly-shaped author dict wrapping ``publications``."""
    return {"publications": list(publications)}


def make_record(title=None, author=None, pub_year=None, journal=None,
                volume=None, pages=None, venue=None, booktitle=None,
                doi=None, pub_url=None, author_pub_id=None):
    """Build a scholarly-shaped record ({'bib': {...}, 'pub_url', ...}).

    Only non-None fields are included, matching scholarly's inconsistent shape.
    """
    bib = {}
    if title is not None:
        bib["title"] = title
    if author is not None:
        bib["author"] = author
    if pub_year is not None:
        bib["pub_year"] = pub_year
    if journal is not None:
        bib["journal"] = journal
    if volume is not None:
        bib["volume"] = volume
    if pages is not None:
        bib["pages"] = pages
    if venue is not None:
        bib["venue"] = venue
    if booktitle is not None:
        bib["booktitle"] = booktitle
    if doi is not None:
        bib["doi"] = doi
    record = {"bib": bib}
    if pub_url is not None:
        record["pub_url"] = pub_url
    if author_pub_id is not None:
        record["author_pub_id"] = author_pub_id
    return record
