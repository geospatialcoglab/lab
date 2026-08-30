"""Curated-entry preservation and deduplication (Task 5.8, Property 7,
Req 3.3, 5.4).

Over generated Scholar Publication lists, merge(load_curated(), scholar):
  - contains each curated entry exactly once,
  - collapses any Scholar entry whose normalized title matches a curated title
    OR shares a curated DOI (curated wording wins, no duplicate work),
  - retains every non-duplicate Scholar entry.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from scripts import generate_publications as gp
from scripts.generate_publications import Publication
from tests import strategies as strat

# The curated list is a packaged repo asset; load it once for the whole module.
CURATED = gp.load_curated()
_CURATED_TITLE_KEYS = {gp._dedup_key(c) for c in CURATED}
_CURATED_DOI_KEYS = {gp._doi_key(c) for c in CURATED if gp._doi_key(c)}


def _is_curated_duplicate(pub: Publication) -> bool:
    """Whether ``pub`` collides with a curated entry by title key or DOI."""
    title_key = gp._dedup_key(pub)
    doi_key = gp._doi_key(pub)
    return title_key in _CURATED_TITLE_KEYS or (
        bool(doi_key) and doi_key in _CURATED_DOI_KEYS
    )


@st.composite
def scholar_pub(draw):
    """A Scholar-derived Publication: arbitrary, or a crafted curated collision."""
    kind = draw(st.integers(min_value=0, max_value=3))
    if kind == 0:
        # Arbitrary Scholar entry (usually a non-duplicate).
        return draw(strat.publications())

    curated = draw(st.sampled_from(CURATED))
    if kind == 1:
        # Title collision with case/punctuation/whitespace variation.
        t = curated.title
        variant = draw(st.sampled_from([
            t.upper(), t.lower(), "   " + t + "   ",
            t.replace(".", ""), t.replace(",", " "),
        ]))
        return Publication(
            title=variant, authors="Scholar Wording", venue="scholar venue",
            year=1999, link="https://example.org/collide", link_label="Link \u2192",
        )
    if kind == 2:
        # DOI collision, distinct title.
        return Publication(
            title="Distinct Scholar Title " + draw(strat.safe_text_nonempty),
            authors="Scholar Wording", venue="scholar venue", year=1990,
            link=curated.link, link_label="DOI \u2192",
        )
    # kind == 3: deliberately unique, non-colliding entry.
    return Publication(
        title="Totally Unique " + draw(strat.safe_text_nonempty),
        authors="S", venue="v", year=1985,
        link="https://example.org/uniq/" + draw(strat.safe_text_nonempty),
        link_label="Link \u2192",
    )


scholar_lists = st.lists(scholar_pub(), max_size=12)


@given(scholar=scholar_lists)
@settings(max_examples=300)
def test_property7_curated_preserved_and_deduped(scholar):
    merged = gp.merge(CURATED, scholar)

    # 1. Curated entries come first, in order, exactly once each.
    assert merged[: len(CURATED)] == CURATED
    for curated in CURATED:
        assert merged.count(curated) == 1

    survivors = merged[len(CURATED):]

    # 2. No Scholar duplicate of a curated work survives.
    for pub in survivors:
        assert not _is_curated_duplicate(pub)

    # 3. Every non-duplicate Scholar entry is retained, in input order.
    expected = [p for p in scholar if not _is_curated_duplicate(p)]
    assert survivors == expected


# --- Concrete dedupe unit tests ------------------------------------------

def test_scholar_title_duplicate_collapses_to_curated_wording():
    curated = CURATED[0]
    # Same work, Scholar's messier wording/case/punctuation.
    scholar_dupe = Publication(
        title=curated.title.upper().replace(".", ""),
        authors="Different Scholar Authors",
        venue="scholar-supplied venue",
        year=curated.year,
        link="https://example.org/scholar",
        link_label="Link \u2192",
    )
    merged = gp.merge(CURATED, [scholar_dupe])
    assert merged.count(curated) == 1
    assert scholar_dupe not in merged
    # Curated wording (venue) is what survives.
    kept = [m for m in merged if gp._dedup_key(m) == gp._dedup_key(curated)]
    assert len(kept) == 1
    assert kept[0].venue == curated.venue


def test_scholar_doi_duplicate_collapses():
    curated = CURATED[0]
    scholar_dupe = Publication(
        title="A Completely Different Title",
        authors="Scholar", venue="v", year=2025,
        link=curated.link,  # shared DOI
        link_label="DOI \u2192",
    )
    merged = gp.merge(CURATED, [scholar_dupe])
    assert scholar_dupe not in merged
    assert len(merged) == len(CURATED)


def test_non_duplicate_scholar_entries_retained():
    unique = Publication(
        title="An Unrelated New Paper", authors="Newton",
        venue="<em>New J</em>, 1, 1-2.", year=2030,
        link="https://example.org/new", link_label="Link \u2192",
    )
    merged = gp.merge(CURATED, [unique])
    assert unique in merged
    assert len(merged) == len(CURATED) + 1


def test_all_curated_present_with_no_scholar():
    merged = gp.merge(CURATED, [])
    assert merged == CURATED
