"""New-tab behaviour and accessible naming of the rendered `.pub-link` anchor.

Publication links point off-site, so the generator emits them with
``target="_blank"`` plus ``rel="noopener noreferrer"`` (``noopener`` blocks
tab-nabbing, ``noreferrer`` stops referrer leakage) and an ``aria-label`` that
announces the new tab while dropping the decorative arrow from the visible
label. These tests pin the emitted attribute set, the label derivation, href
escaping, and that none of it costs determinism.
"""

from __future__ import annotations

import re

from hypothesis import given, settings

from scripts import generate_publications as gp
from tests import strategies as strat

_ANCHOR_RE = re.compile(r"<a [^>]*class=\"pub-link\"[^>]*>")
_ARIA_RE = re.compile(r'<a [^>]*class="pub-link"[^>]*aria-label="([^"]*)"')


def _pub(link_label: str = "DOI \u2192", link: str = "https://doi.org/10.1000/x"):
    return gp.Publication(
        title="A Title.",
        authors="McWhorter, C.",
        venue="<em>Journal</em>, 1, 2.",
        year=2025,
        link=link,
        link_label=link_label,
    )


def _anchor(pub: gp.Publication) -> str:
    """The opening `.pub-link` tag rendered for a single publication."""
    tags = _ANCHOR_RE.findall(gp.render_list([pub]))
    assert len(tags) == 1, tags
    return tags[0]


# --- Emitted attributes ---------------------------------------------------

def test_pub_link_opens_in_new_tab_securely():
    """The anchor carries target="_blank" and rel="noopener noreferrer"."""
    tag = _anchor(_pub())
    assert 'target="_blank"' in tag
    assert 'rel="noopener noreferrer"' in tag


def test_pub_link_attribute_order_is_stable():
    """Attributes are emitted href, class, target, rel, aria-label."""
    tag = _anchor(_pub())
    positions = [
        tag.index("href="),
        tag.index("class="),
        tag.index("target="),
        tag.index("rel="),
        tag.index("aria-label="),
    ]
    assert positions == sorted(positions)


def test_visible_label_is_unchanged():
    """The visible link text still shows the arrow; only the aria-label drops it."""
    rendered = gp.render_list([_pub("DOI \u2192")])
    assert ">DOI \u2192</a>" in rendered


# --- Accessible name -----------------------------------------------------

def test_aria_label_announces_new_tab_for_doi_label():
    """A "DOI →" label yields aria-label="DOI, opens in a new tab"."""
    assert _ARIA_RE.findall(gp.render_list([_pub("DOI \u2192")])) == [
        "DOI, opens in a new tab"
    ]


def test_aria_label_announces_new_tab_for_link_label():
    """A "Link →" label yields aria-label="Link, opens in a new tab"."""
    assert _ARIA_RE.findall(gp.render_list([_pub("Link \u2192")])) == [
        "Link, opens in a new tab"
    ]


def test_aria_label_helper_handles_label_without_arrow():
    """A label with no trailing arrow is passed through, not truncated."""
    assert gp._new_tab_aria_label("DOI") == "DOI, opens in a new tab"
    assert gp._new_tab_aria_label("Full text") == "Full text, opens in a new tab"


def test_aria_label_helper_handles_degenerate_labels():
    """Empty, whitespace, arrow-only, and None labels degrade gracefully."""
    assert gp._new_tab_aria_label("") == "opens in a new tab"
    assert gp._new_tab_aria_label("   ") == "opens in a new tab"
    assert gp._new_tab_aria_label("\u2192") == "opens in a new tab"
    assert gp._new_tab_aria_label(None) == "opens in a new tab"
    # Whitespace around the arrow is not required.
    assert gp._new_tab_aria_label("DOI\u2192") == "DOI, opens in a new tab"


def test_aria_label_is_attribute_escaped():
    """A hostile label cannot break out of the aria-label attribute."""
    rendered = gp.render_list([_pub('Say "hi" & <go> \u2192')])
    assert 'aria-label="Say &quot;hi&quot; &amp; &lt;go&gt;, opens in a new tab"' in (
        rendered
    )


# --- href escaping is preserved ------------------------------------------

def test_href_is_still_attribute_escaped():
    """A Scholar URL's raw & renders as &amp; inside the href."""
    scholar = (
        "https://scholar.google.com/citations?view_op=view_citation&hl=en"
        "&user=Xu5F1CAAAAAJ"
    )
    tag = _anchor(_pub("Link \u2192", scholar))
    assert (
        'href="https://scholar.google.com/citations?view_op=view_citation&amp;hl=en'
        '&amp;user=Xu5F1CAAAAAJ"' in tag
    )
    # No bare ampersand survives in the emitted tag.
    assert not re.search(r"&(?!(?:[a-zA-Z][a-zA-Z0-9]*|#[0-9]+|#x[0-9a-fA-F]+);)", tag)


def test_curated_entries_all_render_new_tab_attributes():
    """Every shipped curated entry gets the full attribute set."""
    rendered = gp.render_list(gp.load_curated())
    tags = _ANCHOR_RE.findall(rendered)
    assert tags, "curated file should contain at least one publication"
    for tag in tags:
        assert 'target="_blank"' in tag
        assert 'rel="noopener noreferrer"' in tag
        assert "aria-label=" in tag


# --- Determinism ---------------------------------------------------------

@given(pubs=strat.publication_lists())
@settings(max_examples=100)
def test_render_list_stays_deterministic_with_link_attributes(pubs):
    """The new attributes keep render_list byte-stable for identical input."""
    first = gp.render_list(pubs)
    second = gp.render_list(pubs)
    assert first == second
    assert first.encode("utf-8") == second.encode("utf-8")
    # Every rendered anchor is fully attributed.
    for tag in _ANCHOR_RE.findall(first):
        assert 'target="_blank" rel="noopener noreferrer" aria-label="' in tag
