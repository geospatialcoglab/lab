"""Author-name highlighting in the rendered author list.

The PI's surname is bolded at RENDER time (not stored in the curated JSON,
whose ``authors`` field is HTML-escaped), so the emphasis survives publications
that a future Scholar sync adds automatically. These tests pin the two
properties that matter: the bolding is applied, and it is applied AFTER escaping
so it cannot be used to inject markup.
"""

from __future__ import annotations

import re

from hypothesis import given, settings

from scripts import generate_publications as gp
from tests import strategies as strat

_AUTHORS_RE = re.compile(r'<p class="pub-authors">(.*)</p>')


def _authors_html(pubs, *args) -> list[str]:
    """The inner HTML of every rendered `.pub-authors` paragraph."""
    return _AUTHORS_RE.findall(gp.render_list(pubs, *args))


def _pub(authors: str) -> gp.Publication:
    return gp.Publication(
        title="A Title.",
        authors=authors,
        venue="<em>Journal</em>, 1, 2.",
        year=2025,
        link="https://doi.org/10.1000/x",
        link_label="DOI \u2192",
    )


def test_pi_surname_is_bolded_in_rendered_authors():
    """The PI surname is wrapped in <strong> in the .pub-authors output."""
    authors = _authors_html([_pub("McWhorter, C., & Montello, D. R.")])
    assert authors == ["<strong>McWhorter</strong>, C., &amp; Montello, D. R."]


def test_pi_surname_is_bolded_in_any_author_position():
    """Bolding is positional-agnostic: it also fires for a non-first author."""
    authors = _authors_html([_pub("Acheson, G., & McWhorter, C.")])
    assert authors == ["Acheson, G., &amp; <strong>McWhorter</strong>, C."]


def test_non_matching_authors_are_left_unchanged():
    """An author string without the surname renders with no <strong> at all."""
    authors = _authors_html([_pub("Hegarty, M., & Baylis, K.")])
    assert authors == ["Hegarty, M., &amp; Baylis, K."]


def test_empty_highlight_author_disables_bolding():
    """Passing an empty highlight_author turns the feature off entirely."""
    authors = _authors_html([_pub("McWhorter, C., & Acheson, G.")], "")
    assert authors == ["McWhorter, C., &amp; Acheson, G."]
    assert "<strong>" not in gp.render_list([_pub("McWhorter, C.")], "")


def test_highlighting_happens_after_escaping_so_it_is_not_injectable():
    """Hostile author text stays escaped; the only raw tags are the added ones."""
    hostile = '<script>alert("x")</script> & McWhorter, C. <b>'
    rendered = gp.render_list([_pub(hostile)])
    assert "<script>" not in rendered
    # Text content escaping leaves quotes literal (quote=False) but neutralizes
    # every angle bracket and ampersand.
    assert '&lt;script&gt;alert("x")&lt;/script&gt;' in rendered
    assert "&amp; <strong>McWhorter</strong>" in rendered
    assert "&lt;b&gt;" in rendered
    # The surname is still bolded despite the surrounding hostile text.
    assert "<strong>McWhorter</strong>" in rendered
    # No raw tag other than the <strong> pair we injected.
    assert set(re.findall(r"<[^>]+>", _authors_html([_pub(hostile)])[0])) == {
        "<strong>",
        "</strong>",
    }


def test_highlight_does_not_match_a_surname_substring():
    """Word boundaries keep a longer name containing the surname unbolded."""
    assert gp._highlight_author("McWhorterson, A.", gp.HIGHLIGHT_AUTHOR) == (
        "McWhorterson, A."
    )
    # Case-sensitive: a differently-cased spelling is not the PI.
    assert gp._highlight_author("mcwhorter, c.", gp.HIGHLIGHT_AUTHOR) == (
        "mcwhorter, c."
    )


def test_highlight_author_ignores_empty_surname():
    """An empty/None surname is a no-op rather than an error."""
    assert gp._highlight_author("McWhorter, C.", "") == "McWhorter, C."
    assert gp._highlight_author("McWhorter, C.", None) == "McWhorter, C."


def test_curated_entries_render_with_bolded_pi():
    """The shipped curated records render the PI bold in every entry."""
    curated = gp.load_curated()
    authors = _authors_html(curated)
    assert authors, "curated file should contain at least one publication"
    for entry in authors:
        assert "<strong>McWhorter</strong>" in entry


@given(pubs=strat.publication_lists())
@settings(max_examples=100)
def test_render_list_stays_deterministic_with_highlighting(pubs):
    """Highlighting keeps render_list pure: same input -> identical bytes."""
    # Inject the surname into every author string so the code path is exercised.
    seeded = [
        gp.Publication(
            title=p.title,
            authors=f"McWhorter, C., & {p.authors}",
            venue=p.venue,
            year=p.year,
            link=p.link,
            link_label=p.link_label,
        )
        for p in pubs
    ]
    first = gp.render_list(seeded)
    second = gp.render_list(seeded)
    assert first == second
    assert first.encode("utf-8") == second.encode("utf-8")
