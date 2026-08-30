"""Rendering determinism/idempotency (Task 5.1) and ordering (Task 5.3).

Property 1 (Req 3.5, 3.6): render_list is a pure, byte-stable function and a
full regenerate over an unchanged fixture yields a byte-identical file.
Property 4 (Req 3.4): rendered output groups by year strictly descending with
the undated (year 0 -> "Undated") bucket last, and title-ascending within a year.
"""

from __future__ import annotations

import re
import shutil
import sys
import types
from pathlib import Path

from hypothesis import given, settings

from scripts import generate_publications as gp
from tests import strategies as strat
from tests.conftest import FakeScholarly, make_author, make_record


# --- 5.1 Property 1: rendering determinism -------------------------------

@given(pubs=strat.publication_lists())
@settings(max_examples=200)
def test_render_list_is_deterministic(pubs):
    """render_list(x) == render_list(x): identical input -> identical bytes."""
    first = gp.render_list(pubs)
    second = gp.render_list(pubs)
    assert first == second
    assert first.encode("utf-8") == second.encode("utf-8")


@given(pubs=strat.publication_lists(min_size=1))
@settings(max_examples=100)
def test_inject_twice_is_idempotent(pubs):
    """Injecting the same rendered block twice is a no-op the second time."""
    rendered = gp.render_list(pubs)
    base = (
        "<html><body>\n"
        "                <!-- PUBLICATIONS:START -->\n"
        "                <!-- PUBLICATIONS:END -->\n"
        "</body></html>\n"
    )
    once = gp.inject(base, rendered)
    twice = gp.inject(once, rendered)
    assert once == twice


def test_full_regenerate_is_byte_identical(tmp_path, monkeypatch):
    """main() over an unchanged fixture writes nothing on the second run.

    First run injects into a temp copy of publications.html; the second run,
    with the same mocked Scholar records, must find the file already up to date
    and leave the bytes untouched (zero diff -> zero commit, Req 3.6).
    """
    src = Path(__file__).resolve().parent.parent / "publications.html"
    html_file = tmp_path / "publications.html"
    shutil.copyfile(src, html_file)

    records = [
        make_record(title="A Study of Wayfinding", author="X and Y",
                    pub_year="2023", journal="J Nav", volume="7", pages="1-10",
                    pub_url="https://example.org/a"),
        make_record(title="Spatial Decisions Under Stress", author="Z",
                    pub_year="2021", doi="10.1000/xyz"),
    ]
    author = make_author(records)

    def install():
        fake = FakeScholarly(author=author)
        fake_mod = types.ModuleType("scholarly")
        fake_mod.scholarly = fake
        monkeypatch.setitem(sys.modules, "scholarly", fake_mod)

    argv = ["--html-file", str(html_file), "--max-retries", "1",
            "--attempt-timeout", "5", "--request-timeout", "1"]

    install()
    rc1 = gp.main(argv)
    assert rc1 == 0
    after_first = html_file.read_bytes()

    install()
    rc2 = gp.main(argv)
    assert rc2 == 0
    after_second = html_file.read_bytes()

    assert after_first == after_second


# --- 5.3 Property 4: deterministic ordering ------------------------------

_YEAR_HEADING_RE = re.compile(r'<div class="pub-year">\s*<h2>([^<]*)</h2>')
_TITLE_RE = re.compile(r'<p class="pub-title">([^<]*)</p>')


def _year_headings(rendered: str):
    return _YEAR_HEADING_RE.findall(rendered)


@given(pubs=strat.publication_lists(min_size=1))
@settings(max_examples=200)
def test_years_render_strictly_descending_with_undated_last(pubs):
    """Year headings appear in strictly descending order, 'Undated' bucket last."""
    rendered = gp.render_list(pubs)
    headings = _year_headings(rendered)

    # Map headings back to sortable numbers: "Undated" is the year-0 bucket.
    numeric = [0 if h == "Undated" else int(h) for h in headings]

    # No duplicate year groups.
    assert len(numeric) == len(set(numeric))

    # Real years strictly descending; undated (0) forced last if present.
    real = [y for y in numeric if y != 0]
    assert real == sorted(real, reverse=True)
    if 0 in numeric:
        assert numeric[-1] == 0
        assert 0 not in numeric[:-1]


@given(pubs=strat.publication_lists(min_size=1))
@settings(max_examples=200)
def test_titles_ascending_within_each_year(pubs):
    """Within a single .pub-year block, titles are sorted ascending."""
    rendered = gp.render_list(pubs)
    # Split into year blocks and check title order inside each.
    blocks = rendered.split('<div class="pub-year">')
    for block in blocks[1:]:
        titles = _TITLE_RE.findall(block)
        assert titles == sorted(titles)
