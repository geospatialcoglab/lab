"""Total normalization and defined link output (Task 5.4, Property 5, Req 3.3).

normalize() must never raise on arbitrary/garbage records, must skip records
without a title, and must give every produced Publication a non-empty link
following the DOI -> pub_url -> Scholar-URL fallback (with the correct label).
"""

from __future__ import annotations

from hypothesis import given, settings

from scripts import generate_publications as gp
from tests import strategies as strat
from tests.conftest import make_record


# --- Property 5 ----------------------------------------------------------

@given(records=strat.raw_records())
@settings(max_examples=400)
def test_normalize_never_raises_and_links_nonempty(records):
    """normalize is total; every result has a title and a non-empty link."""
    pubs = gp.normalize(records)  # must not raise
    for pub in pubs:
        assert pub.title != ""          # titleless records are skipped
        assert pub.link != ""           # link is never empty (Req 3.3)
        assert pub.link_label in ("DOI \u2192", "Link \u2192")
        assert isinstance(pub.year, int)


@given(records=strat.raw_records())
@settings(max_examples=200)
def test_titleless_records_are_skipped(records):
    """Count of produced pubs never exceeds count of records with a real title."""
    def has_title(rec):
        if not isinstance(rec, dict):
            return False
        bib = rec.get("bib")
        if not isinstance(bib, dict):
            return False
        title = bib.get("title")
        return title is not None and str(title).strip() != ""

    expected = sum(1 for r in records if has_title(r))
    assert len(gp.normalize(records)) == expected


# --- Link fallback chain (DOI -> pub_url -> Scholar URL) ------------------

def test_real_doi_wins_with_doi_label():
    rec = make_record(title="T", doi="10.1016/j.ijdrr.2025.105446",
                      pub_url="https://example.org/paper")
    pub = gp.normalize([rec])[0]
    assert pub.link == "https://doi.org/10.1016/j.ijdrr.2025.105446"
    assert pub.link_label == "DOI \u2192"


def test_doi_style_pub_url_counts_as_doi():
    rec = make_record(title="T", pub_url="https://doi.org/10.1000/abc")
    pub = gp.normalize([rec])[0]
    assert pub.link == "https://doi.org/10.1000/abc"
    assert pub.link_label == "DOI \u2192"


def test_non_doi_pub_url_uses_link_label():
    rec = make_record(title="T", pub_url="https://example.org/paper")
    pub = gp.normalize([rec])[0]
    assert pub.link == "https://example.org/paper"
    assert pub.link_label == "Link \u2192"


def test_scholar_url_fallback_when_no_doi_or_pub_url():
    rec = make_record(title="T", author_pub_id="Xu5F1CAAAAAJ:u5HHmVD_uO8C")
    pub = gp.normalize([rec])[0]
    assert pub.link != ""
    assert pub.link.startswith(gp.SCHOLAR_CITATIONS_BASE)
    assert "u5HHmVD_uO8C" in pub.link
    assert pub.link_label == "Link \u2192"


def test_scholar_base_fallback_when_nothing_available():
    rec = make_record(title="T")
    pub = gp.normalize([rec])[0]
    assert pub.link == gp.SCHOLAR_CITATIONS_BASE
    assert pub.link_label == "Link \u2192"


# --- Author formatting ----------------------------------------------------

def test_author_single_unchanged():
    pub = gp.normalize([make_record(title="T", author="Solo Author")])[0]
    assert pub.authors == "Solo Author"


def test_author_two_joined_with_ampersand():
    pub = gp.normalize([make_record(title="T", author="A B and C D")])[0]
    assert pub.authors == "A B & C D"


def test_author_three_oxford_join():
    pub = gp.normalize([make_record(title="T", author="A and B and C")])[0]
    assert pub.authors == "A, B, & C"


# --- Year parsing ---------------------------------------------------------

def test_year_parsed_from_string():
    pub = gp.normalize([make_record(title="T", pub_year="2021")])[0]
    assert pub.year == 2021


def test_unparseable_year_becomes_zero():
    pub = gp.normalize([make_record(title="T", pub_year="n/a")])[0]
    assert pub.year == 0


def test_missing_year_becomes_zero():
    pub = gp.normalize([make_record(title="T")])[0]
    assert pub.year == 0


# --- Venue assembly -------------------------------------------------------

def test_venue_from_journal_volume_pages_wraps_em():
    rec = make_record(title="T", journal="Nature", volume="12", pages="3-9")
    pub = gp.normalize([rec])[0]
    assert pub.venue == "<em>Nature</em>, 12, 3-9."


def test_venue_falls_back_to_booktitle():
    rec = make_record(title="T", booktitle="Some Proceedings")
    pub = gp.normalize([rec])[0]
    assert pub.venue == "Some Proceedings"
