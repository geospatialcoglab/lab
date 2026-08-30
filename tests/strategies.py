"""Shared Hypothesis strategies for the Generator_Script property tests.

Strategies build both ``Publication`` values (for the pure render/order tests)
and raw ``scholarly``-shaped records (for the normalization property test).
Titles/authors/venues are drawn from an HTML-safe alphabet (no ``&``, ``<``,
``>``) so that ``html.escape`` is a no-op and ordering assertions can compare
the rendered text directly against the source strings.
"""

from __future__ import annotations

import string

from hypothesis import strategies as st

from scripts.generate_publications import Publication

# Alphabet with no HTML-sensitive characters so escape() leaves text unchanged.
_SAFE_CHARS = string.ascii_letters + string.digits + " .,:-_()"

safe_text = st.text(alphabet=_SAFE_CHARS, min_size=0, max_size=40)
safe_text_nonempty = st.text(alphabet=_SAFE_CHARS, min_size=1, max_size=40).map(
    lambda s: s.strip() or "x"
)

# Years: a spread of real years plus 0 (the "Undated" sentinel bucket).
years = st.one_of(
    st.integers(min_value=1900, max_value=2100),
    st.just(0),
)


@st.composite
def publications(draw):
    """A single render-ready ``Publication`` with HTML-safe fields."""
    return Publication(
        title=draw(safe_text_nonempty),
        authors=draw(safe_text),
        venue=draw(safe_text),
        year=draw(years),
        link=draw(safe_text_nonempty),
        link_label=draw(st.sampled_from(["DOI \u2192", "Link \u2192"])),
    )


def publication_lists(min_size=0, max_size=12):
    """Lists of ``Publication`` values."""
    return st.lists(publications(), min_size=min_size, max_size=max_size)


# --- Raw scholarly-record strategies (for normalize) ----------------------
#
# scholarly's field layout is inconsistent, so these strategies deliberately
# emit missing keys, wrong types, and junk values to prove normalize() is total.

_junk_values = st.one_of(
    st.none(),
    st.text(max_size=30),
    st.integers(),
    st.booleans(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.lists(st.text(max_size=5), max_size=3),
    st.dictionaries(st.text(max_size=5), st.text(max_size=5), max_size=3),
)

_bib_keys = st.sampled_from(
    ["title", "author", "pub_year", "journal", "volume", "pages",
     "venue", "booktitle", "doi", "junk_key"]
)


@st.composite
def raw_bib(draw):
    """An arbitrary, possibly-garbage bib dict."""
    return draw(st.dictionaries(_bib_keys, _junk_values, max_size=8))


@st.composite
def raw_record(draw):
    """An arbitrary scholarly-shaped record, or occasionally pure junk.

    Emits dicts with an arbitrary ``bib`` (which may itself be junk, not a
    dict), optional ``pub_url``/``author_pub_id``, and sometimes a non-dict
    record entirely so normalize()'s skip path is exercised.
    """
    kind = draw(st.integers(min_value=0, max_value=9))
    if kind == 0:
        # Non-dict record: normalize must skip it.
        return draw(_junk_values)
    record = {"bib": draw(st.one_of(raw_bib(), _junk_values))}
    if draw(st.booleans()):
        record["pub_url"] = draw(_junk_values)
    if draw(st.booleans()):
        record["author_pub_id"] = draw(_junk_values)
    return record


def raw_records(max_size=10):
    return st.lists(raw_record(), max_size=max_size)
