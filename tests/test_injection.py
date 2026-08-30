"""Structure preservation under injection (Task 5.2, Property 2, Req 3.7).

inject() must replace ONLY the region strictly between the sentinels, leave
every byte outside that region unchanged, keep the sentinel strings intact, be
idempotent, and raise SentinelError on missing/out-of-order sentinels.
"""

from __future__ import annotations

import string

from hypothesis import given, settings
from hypothesis import strategies as st

from scripts import generate_publications as gp
from tests import strategies as strat

START = gp.PUBLICATIONS_START
END = gp.PUBLICATIONS_END

# Surrounding text must not itself contain the sentinel strings, so restrict to
# a plain alphabet (no '<'/'!' sequences that could form a sentinel).
_outside = st.text(alphabet=string.ascii_letters + string.digits + " \n\t",
                   min_size=0, max_size=60)


@st.composite
def html_with_sentinels(draw):
    """HTML with both sentinels present and in order, plus arbitrary edges."""
    prefix = draw(_outside)
    end_indent = draw(st.sampled_from(["", "    ", "                "]))
    inner = draw(_outside)  # pre-existing content between sentinels
    suffix = draw(_outside)
    text = (
        prefix
        + START
        + inner
        + "\n" + end_indent + END
        + suffix
    )
    return text, prefix, suffix


@given(data=html_with_sentinels(), pubs=strat.publication_lists())
@settings(max_examples=200)
def test_inject_preserves_bytes_outside_region(data, pubs):
    """Everything before/including START and from END onward is unchanged."""
    html_text, prefix, suffix = data
    rendered = gp.render_list(pubs)

    out = gp.inject(html_text, rendered)

    # Prefix up to and including START is preserved verbatim.
    kept_prefix = html_text[: html_text.find(START) + len(START)]
    assert out.startswith(kept_prefix)

    # Everything from END onward is preserved verbatim.
    kept_suffix = html_text[html_text.find(END):]
    assert out.endswith(kept_suffix)

    # Both sentinels survive exactly once.
    assert out.count(START) == 1
    assert out.count(END) == 1

    # The rendered block sits inside the region.
    if rendered:
        assert rendered in out


@given(data=html_with_sentinels(), pubs=strat.publication_lists())
@settings(max_examples=200)
def test_inject_is_idempotent(data, pubs):
    """Re-injecting the same rendered block yields byte-identical output."""
    html_text, _prefix, _suffix = data
    rendered = gp.render_list(pubs)
    once = gp.inject(html_text, rendered)
    twice = gp.inject(once, rendered)
    assert once == twice


def test_missing_start_sentinel_raises():
    with_only_end = "<html>\n" + END + "\n</html>"
    try:
        gp.inject(with_only_end, "")
        assert False, "expected SentinelError"
    except gp.SentinelError:
        pass


def test_missing_end_sentinel_raises():
    with_only_start = "<html>\n" + START + "\n</html>"
    try:
        gp.inject(with_only_start, "")
        assert False, "expected SentinelError"
    except gp.SentinelError:
        pass


def test_out_of_order_sentinels_raise():
    reversed_order = "<html>\n" + END + "\nmiddle\n" + START + "\n</html>"
    try:
        gp.inject(reversed_order, "")
        assert False, "expected SentinelError"
    except gp.SentinelError:
        pass
