"""HTML primitives shared by the publications and news generators.

This module holds the small, pure building blocks that both static-site
generators in ``scripts/`` need: HTML escaping, the accessible-name convention
for links that open in a new tab, and the marker-based injection that splices a
generated block into a hand-written HTML page between two sentinel comments.

These primitives originated inside ``scripts/generate_publications.py`` (as
``SentinelError``, ``_escape_text``, ``_escape_attr``, ``_new_tab_aria_label``,
and ``inject``). They are needed verbatim by the news generator, and duplicating
them would mean two copies of the subtlest code in the repository: the
whitespace contract of the injector is exact, and a drifting copy would be the
one nobody is watching. So they live here once, generalized only where the news
pipeline needs it, namely ``inject_between()``, which takes the sentinel pair,
the fallback indent, and the target file name as parameters because the news
pipeline injects two different marker pairs into two different files.

Standard library only, no imports from either generator, so this module stays
trivially importable and unit-testable.
"""

from __future__ import annotations

import html

# Decorative arrow that can appear at the tail of a visible link label
# ("DOI \u2192"). It is stripped out of the accessible name so a screen reader
# announces "DOI, opens in a new tab" instead of reading the glyph.
LINK_ARROW = "\u2192"

# Phrase appended to an accessible name for a link that opens in a new tab.
NEW_TAB_SUFFIX = "opens in a new tab"


class SentinelError(ValueError):
    """A target file's sentinel pair is missing or out of order.

    Marker-based injection refuses to guess where a generated block belongs: if
    either sentinel is absent, or the end sentinel precedes (or overlaps) the
    start sentinel, the run must fail rather than rewrite a hand-edited file
    whose markers were removed or reordered.
    """


def escape_text(value: str, quote: bool = False) -> str:
    """Escape ``value`` for use as HTML element text content.

    Thin wrapper over ``html.escape(value, quote=quote)``: ``&``, ``<``, and
    ``>`` always become entities, and ``"`` plus ``'`` become entities only when
    ``quote`` is true.

    The two generators call this differently on purpose. The publications
    generator escapes text with ``quote=False``, matching its original
    ``_escape_text`` helper, which left quote characters alone in text content.
    The news generator passes ``quote=True``, because news Requirement 2.7 names
    the double-quote character explicitly among the characters that must be
    escaped in every text value taken from a post file.
    """
    return html.escape(value, quote=quote)


def escape_text_content(value: str) -> str:
    """Escape exactly the four characters named by news Requirement 2.7.

    Escapes ``&``, ``<``, ``>``, and ``"``, and deliberately does NOT escape the
    apostrophe. ``html.escape(value, quote=True)`` would emit ``&#x27;`` for
    every apostrophe in ordinary prose ("master's degree" becoming
    "master&#x27;s degree"), while an apostrophe is harmless in element text and
    inside a double-quoted attribute, so escaping it is noise that makes the
    generated HTML worse than the hand-written pages it replaces.

    ``html.escape(value, quote=False)`` handles ``&`` first, which is what keeps
    the subsequent ``"`` -> ``&quot;`` replacement from double encoding the
    ampersand it introduces.
    """
    return html.escape(value, quote=False).replace('"', "&quot;")


def escape_attr(value: str) -> str:
    """Escape ``value`` for use inside a double-quoted HTML attribute.

    Always escapes quotes (``html.escape(value, quote=True)``), so the result is
    safe between the double quotes of an attribute such as ``href``. Hrefs
    routinely contain ``&`` (for example a Scholar URL like
    ``?user=...&citation_for_view=...``), which must be emitted as ``&amp;``.
    """
    return html.escape(value, quote=True)


def new_tab_aria_label(label: str) -> str:
    """Derive the accessible name for a link that opens in a new tab.

    Pure and total. A visible label may carry a decorative trailing arrow
    (U+2192, for example ``"DOI \u2192"``) that a screen reader would read out,
    so the arrow is stripped along with surrounding whitespace before the
    announcement is appended:

        "DOI \u2192"  -> "DOI, opens in a new tab"
        "Link \u2192" -> "Link, opens in a new tab"
        "DOI"         -> "DOI, opens in a new tab"   (no arrow, handled fine)

    A label that is empty, whitespace-only, arrow-only, or ``None`` yields just
    ``"opens in a new tab"``. The result is plain text; callers must pass it
    through :func:`escape_attr` before emitting it into an attribute.
    """
    text = (label or "").strip()
    if text.endswith(LINK_ARROW):
        text = text[: -len(LINK_ARROW)].strip()
    return f"{text}, {NEW_TAB_SUFFIX}" if text else NEW_TAB_SUFFIX


def inject_between(
    html_text: str,
    rendered: str,
    start_marker: str,
    end_marker: str,
    default_indent: str,
    file_label: str = "the target file",
) -> str:
    """Splice ``rendered`` between ``start_marker`` and ``end_marker``.

    Pure function. This is the publications generator's ``inject()`` with the
    marker pair, the fallback indent, and the file name in the error messages
    lifted into parameters. The contract below is unchanged, and is spelled out
    in full because both pipelines depend on every clause of it.

    Location and preservation:
        - ``start_marker`` is located with ``str.find``, then ``end_marker``.
        - ``prefix`` is everything up to AND INCLUDING ``start_marker``;
          ``suffix`` is everything from ``end_marker`` onward. Both are preserved
          byte for byte, the marker strings themselves included, along with the
          indentation of the start marker's line (which sits in the prefix).
        - Only the text strictly between the two markers is replaced.

    Whitespace contract:
        - ``end_indent`` is the horizontal whitespace on the end marker's own
          line, that is, the text from the newline preceding the marker up to
          the marker. It is used verbatim when it is all whitespace, and
          ``default_indent`` is used instead when the end marker shares its line
          with other content.
        - The middle region becomes ``"\\n" + rendered + end_indent``, or just
          ``"\\n" + end_indent`` when ``rendered`` is falsy.

    Idempotence:
        No blank padding is emitted before the end marker. Any pre-existing
        blank padding therefore collapses on the first run and never grows
        again, which is exactly what makes repeated injection byte-identical:
        running this on already-injected HTML with the same ``rendered`` returns
        the same bytes. Reading ``end_indent`` from the live end-marker line
        rather than hard-coding it means the splice tracks the file's real
        indentation while still landing on a fixed point.

    Args:
        html_text: the full current text of the target file.
        rendered: the generated block to place between the markers. It is
            expected to end with a single newline when non-empty.
        start_marker: the opening sentinel string, for example
            ``"<!-- NEWS:START -->"``.
        end_marker: the closing sentinel string.
        default_indent: fallback indentation for the end marker's line.
        file_label: name of the target file, used in error messages.

    Returns:
        The full new file text.

    Raises:
        SentinelError: if ``start_marker`` or ``end_marker`` is absent, or if
            ``end_marker`` appears before (or overlapping) the position just
            after ``start_marker``. This must abort the run rather than guess.
    """
    start_pos = html_text.find(start_marker)
    if start_pos == -1:
        raise SentinelError(
            f"Missing start sentinel {start_marker!r} in {file_label}"
        )

    end_pos = html_text.find(end_marker)
    if end_pos == -1:
        raise SentinelError(
            f"Missing end sentinel {end_marker!r} in {file_label}"
        )

    after_start = start_pos + len(start_marker)
    if end_pos < after_start:
        raise SentinelError(
            "End sentinel appears before (or overlaps) the start sentinel in "
            f"{file_label}"
        )

    prefix = html_text[:after_start]
    suffix = html_text[end_pos:]

    # Indentation on the end marker's own line: the horizontal whitespace from
    # the newline preceding the marker up to the marker. Reused so the end line
    # keeps its indentation; falls back to default_indent if the end marker
    # unexpectedly shares its line with non-whitespace content.
    line_start = html_text.rfind("\n", 0, end_pos) + 1
    end_line_prefix = html_text[line_start:end_pos]
    end_indent = end_line_prefix if end_line_prefix.strip() == "" else default_indent

    if rendered:
        middle = "\n" + rendered + end_indent
    else:
        middle = "\n" + end_indent

    return prefix + middle + suffix
