"""Generate the publications list for publications.html from Google Scholar data.

This is the Generator_Script for the automated publication sync pipeline
(design Component 4). It runs in CI (GitHub Actions), never in the browser, and
transforms records fetched from a Google Scholar profile into the deterministic
`.publications-list` markup used by publications.html.

The pipeline is:

    fetch (scholarly) -> normalize -> threshold-guard -> load curated + merge
    -> render -> inject -> write-only-if-different

Only the standard library is used by the pure transformation core so the module
imports cleanly and stays unit-testable without a network or the ``scholarly``
dependency. The ``scholarly`` import is deferred to the fetch layer (task 4.5).

This file is built incrementally across tasks 4.1-4.6. Task 4.1 establishes the
``Publication`` model and ``normalize()`` plus the small helpers it needs.

Undated-year convention: a publication whose ``pub_year`` is missing or does not
parse to an integer is stored with ``year = 0``. Zero is a sentinel meaning
"undated"; rendering (task 4.2) sorts years descending, so 0 naturally sorts
last, and the renderer is responsible for showing a human label (e.g. "Undated")
for the 0 bucket. Normalization never crashes on a bad year.

Author-formatting convention: Scholar joins authors with " and "
(``"A and B and C"``). Display uses an Oxford-style join:
    - one author  -> unchanged ("A")
    - two authors -> "A & B"
    - 3+ authors  -> "A, B, & C"
An unparseable/empty author field falls back to the raw string.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Base used only as the final, never-empty fallback for a publication link when
# no DOI, no pub_url, and no per-citation Scholar id are available.
SCHOLAR_CITATIONS_BASE = "https://scholar.google.com/citations"


@dataclass(frozen=True)
class Publication:
    """A normalized, render-ready publication record.

    Fields map directly onto the rendered markup:
        title      -> .pub-title
        authors    -> .pub-authors (already joined into a display string)
        venue      -> .pub-venue inner HTML (may contain <em> around the journal)
        year       -> .pub-year grouping key; 0 means undated (see module docs)
        link       -> .pub-link href (never empty; DOI preferred)
        link_label -> visible .pub-link text, e.g. "DOI →" or "Link →"
    """

    title: str
    authors: str
    venue: str
    year: int
    link: str
    link_label: str


def _format_authors(raw: object) -> str:
    """Reformat a scholarly ``author`` string into an Oxford-style display join.

    scholarly typically returns ``"A and B and C"``. Returns:
        - the single author unchanged for one author,
        - ``"A & B"`` for two authors,
        - ``"A, B, & C"`` for three or more.
    If ``raw`` is empty or not a string, returns the coerced raw value (possibly
    an empty string) so normalization never crashes.
    """
    if not isinstance(raw, str):
        return "" if raw is None else str(raw)

    text = raw.strip()
    if not text:
        return ""

    # Split on the literal " and " separator scholarly uses between authors.
    names = [name.strip() for name in re.split(r"\s+and\s+", text) if name.strip()]

    if len(names) <= 1:
        # Single author (or unparseable) -> keep as-is.
        return names[0] if names else text
    if len(names) == 2:
        return f"{names[0]} & {names[1]}"
    return ", ".join(names[:-1]) + f", & {names[-1]}"


def _parse_year(raw: object) -> int:
    """Parse a scholarly ``pub_year`` into an int, or 0 (undated) if unparseable.

    Accepts ints or strings that contain a 4-ish digit year; returns 0 for
    ``None``, empty, or anything without digits. Never raises.
    """
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        match = re.search(r"\d{3,4}", raw)
        if match:
            try:
                return int(match.group())
            except ValueError:
                return 0
    return 0


def _clean(value: object) -> str:
    """Coerce a possibly-missing bib value to a stripped string ("" if absent)."""
    if value is None:
        return ""
    return str(value).strip()


def _build_venue(bib: dict) -> str:
    """Assemble the .pub-venue inner HTML from bib fields, journal wrapped in <em>.

    Priority:
        1. journal (+ ", {volume}" if present, + ", {pages}" if present),
           with the journal name wrapped in <em>...</em> and a trailing period,
           matching the existing hand-entered style, e.g.
           "<em>International Journal of Disaster Risk Reduction</em>, 123, 105446."
        2. venue, else booktitle (returned as-is).
        3. empty string when nothing is available.
    """
    journal = _clean(bib.get("journal"))
    if journal:
        parts = [f"<em>{journal}</em>"]
        volume = _clean(bib.get("volume"))
        if volume:
            parts.append(volume)
        pages = _clean(bib.get("pages"))
        if pages:
            parts.append(pages)
        return ", ".join(parts) + "."

    fallback = _clean(bib.get("venue")) or _clean(bib.get("booktitle"))
    return fallback


def _normalize_doi(raw: str) -> str:
    """Turn a raw DOI value into a full doi.org URL, or "" if it isn't a DOI."""
    doi = raw.strip()
    if not doi:
        return ""
    if doi.startswith("http://") or doi.startswith("https://"):
        return doi if "doi.org/" in doi else ""
    # Bare DOI like "10.1016/j.ijdrr.2025.105446" -> full URL.
    if doi.lower().startswith("doi:"):
        doi = doi[4:].strip()
    if doi.startswith("10."):
        return f"https://doi.org/{doi}"
    return ""


def _scholar_entry_url(record: dict) -> str:
    """Build a Scholar citation URL from ``author_pub_id`` (final link fallback).

    ``author_pub_id`` looks like ``"Xu5F1CAAAAAJ:u5HHmVD_uO8C"`` (user id, then a
    per-citation id). When present we build the per-citation view URL; otherwise
    we fall back to the generic Scholar citations base so the link is never empty.
    """
    author_pub_id = _clean(record.get("author_pub_id"))
    if author_pub_id and ":" in author_pub_id:
        user, citation = author_pub_id.split(":", 1)
        return (
            f"{SCHOLAR_CITATIONS_BASE}?view_op=view_citation&hl=en"
            f"&user={user}&citation_for_view={author_pub_id}"
        )
    if author_pub_id:
        return f"{SCHOLAR_CITATIONS_BASE}?view_op=view_citation&hl=en&citation_for_view={author_pub_id}"
    return SCHOLAR_CITATIONS_BASE


def _build_link(record: dict, bib: dict) -> tuple[str, str]:
    """Resolve the (link, link_label) pair using the DOI -> pub_url -> Scholar chain.

    - A genuine DOI (bib['doi'] or a doi.org pub_url) -> (doi_url, "DOI →").
    - Else a pub_url                                  -> (pub_url, "Link →").
    - Else the Scholar entry URL                      -> (scholar_url, "Link →").
    The returned link is never empty (Req 3.3).
    """
    # 1. Explicit DOI field.
    doi_url = _normalize_doi(_clean(bib.get("doi")))
    if doi_url:
        return doi_url, "DOI →"

    pub_url = _clean(record.get("pub_url"))

    # 2. A pub_url that is itself a DOI link counts as a DOI.
    if pub_url and "doi.org/" in pub_url:
        return pub_url, "DOI →"

    # 3. A non-DOI outbound pub_url.
    if pub_url:
        return pub_url, "Link →"

    # 4. Never-empty fallback: the Scholar entry / profile URL.
    return _scholar_entry_url(record), "Link →"


def normalize(records) -> list[Publication]:
    """Map raw scholarly-style records into a list of ``Publication`` values.

    Each raw record is expected to look like::

        {"bib": {"title": ..., "author": "A and B and C", "pub_year": "2021",
                 "journal": ..., "volume": ..., "pages": ..., "venue": ...},
         "pub_url": ..., "author_pub_id": ..., ...}

    Mapping is defensive because scholarly fields are inconsistent:
        - title:   bib['title']; a record with no title is SKIPPED (not emitted).
        - authors: bib['author'] reformatted Oxford-style; raw string if odd.
        - year:    bib['pub_year'] parsed to int, 0 (undated) if unparseable.
        - venue:   journal (+ volume/pages, journal in <em>), else venue/booktitle.
        - link:    DOI -> pub_url -> Scholar entry URL (never empty), with the
                   matching link_label ("DOI →" vs "Link →").

    Never raises on malformed input.
    """
    pubs: list[Publication] = []
    for record in records or []:
        if not isinstance(record, dict):
            continue
        bib = record.get("bib")
        if not isinstance(bib, dict):
            bib = {}

        title = _clean(bib.get("title"))
        if not title:
            # No title -> skip the record entirely.
            continue

        authors = _format_authors(bib.get("author"))
        year = _parse_year(bib.get("pub_year"))
        venue = _build_venue(bib)
        link, link_label = _build_link(record, bib)

        pubs.append(
            Publication(
                title=title,
                authors=authors,
                venue=venue,
                year=year,
                link=link,
                link_label=link_label,
            )
        )
    return pubs

# --- Rendering (task 4.2) -------------------------------------------------
#
# The rendered block is injected between the PUBLICATIONS:START / :END
# sentinels inside the `.publications-list` container in publications.html.
# In that file the sentinels and the `.pub-year` blocks are indented 16 spaces
# (they sit four levels deep: section > container > publications-list > block).
# render_list() reproduces that exact indentation so injected output looks
# hand-written and, more importantly, is byte-stable across runs.
#
# Indentation contract (spaces):
#     16  <div class="pub-year"> ... </div>
#     20      <h2>...</h2>  and  <div class="publication"> ... </div>
#     24          <p class="pub-*">...</p>  and  <a ... class="pub-link">...</a>
#
# The undated bucket (year == 0) always sorts last and renders its <h2> as
# "Undated" rather than "0".

import html

# Base indent of a `.pub-year` block inside `.publications-list`.
_BASE_INDENT = " " * 16
_UNDATED_HEADING = "Undated"

# Surname of the lab PI, emphasized with <strong> in every rendered author list.
#
# Bolding is applied at RENDER time (not stored in curated_publications.json)
# because the `authors` field is HTML-escaped by `_escape_text()` before it is
# emitted, so a literal `<strong>` in the JSON would display as visible text.
# Doing it here also means publications that a future Scholar sync adds
# automatically get the same treatment with no manual editing.
HIGHLIGHT_AUTHOR = "McWhorter"

# Decorative arrow at the tail of a visible link label ("DOI →"). It is stripped
# out of the accessible name so a screen reader announces "DOI, opens in a new
# tab" instead of reading the glyph.
_LINK_ARROW = "\u2192"
_NEW_TAB_SUFFIX = "opens in a new tab"


def _escape_text(value: str) -> str:
    """Escape &, <, > for use as element text content (quotes left as-is)."""
    return html.escape(value, quote=False)


def _escape_attr(value: str) -> str:
    """Escape a value for use inside a double-quoted HTML attribute (href).

    Scholar URLs routinely contain ``&`` (e.g. ``?user=...&citation_for_view=``)
    so this must at least turn ``&`` into ``&amp;`` and ``"`` into ``&quot;``.
    """
    return html.escape(value, quote=True)


def _highlight_author(escaped_authors: str, surname: str) -> str:
    """Wrap whole-word occurrences of ``surname`` in ``<strong>`` (pure).

    MUST be called on ALREADY-ESCAPED author text: escaping first and injecting
    the markup afterwards is what keeps the output injection-safe, since any
    ``&``/``<``/``>`` in the source string has already become an entity and the
    only raw tags in the result are the ones added here.

    Matching is case-sensitive and word-bounded (``\\bSurname\\b`` with
    ``re.escape``), so "McWhorter, C." matches while a longer name containing
    the surname as a substring does not. An empty or ``None`` surname disables
    highlighting and returns the input unchanged.
    """
    if not surname:
        return escaped_authors
    pattern = r"\b" + re.escape(surname) + r"\b"
    return re.sub(pattern, lambda m: f"<strong>{m.group(0)}</strong>", escaped_authors)


def _new_tab_aria_label(link_label: str) -> str:
    """Derive the `.pub-link` aria-label announcing that the link opens a new tab.

    Pure and total. The visible label carries a decorative trailing arrow
    (U+2192, e.g. ``"DOI →"``) that would be read out by a screen reader, so it
    is stripped along with the surrounding whitespace before the announcement is
    appended:

        "DOI →"  -> "DOI, opens in a new tab"
        "Link →" -> "Link, opens in a new tab"
        "DOI"    -> "DOI, opens in a new tab"   (no arrow: handled gracefully)

    A label that is empty (or arrow-only) yields just ``"opens in a new tab"``.
    The result is plain text; callers must ``_escape_attr()`` it before emitting.
    """
    text = (link_label or "").strip()
    if text.endswith(_LINK_ARROW):
        text = text[: -len(_LINK_ARROW)].strip()
    return f"{text}, {_NEW_TAB_SUFFIX}" if text else _NEW_TAB_SUFFIX


def _render_publication(pub: Publication, highlight_author: str = HIGHLIGHT_AUTHOR) -> str:
    """Render a single `.publication` block (20-space indented, trailing newline).

    Text fields (authors, title, link_label) are HTML-escaped; the href and the
    aria-label are attribute-escaped; ``venue`` is emitted verbatim because it is
    trusted internal HTML that may contain intentional <em> markup.

    The link is an outbound citation, so it opens in a new tab with
    ``target="_blank"`` plus ``rel="noopener noreferrer"``: ``noopener`` denies
    the opened page any handle on this one (tab-nabbing), ``noreferrer`` keeps
    the referrer from leaking. Because the visible label alone would not tell a
    screen-reader user about the new tab, an ``aria-label`` derived from
    ``link_label`` (arrow stripped) announces it.

    Attribute order is fixed -- href, class, target, rel, aria-label -- to keep
    the output byte-stable.

    ``highlight_author`` (default ``HIGHLIGHT_AUTHOR``) is applied to the
    authors field only, AFTER escaping; pass ``""`` to disable bolding.
    """
    i2 = _BASE_INDENT + " " * 4   # 20 spaces: .publication
    i3 = _BASE_INDENT + " " * 8   # 24 spaces: inner <p>/<a>
    authors = _highlight_author(_escape_text(pub.authors), highlight_author)
    aria_label = _escape_attr(_new_tab_aria_label(pub.link_label))
    lines = [
        f'{i2}<div class="publication">',
        f'{i3}<p class="pub-authors">{authors}</p>',
        f'{i3}<p class="pub-title">{_escape_text(pub.title)}</p>',
        f'{i3}<p class="pub-venue">{pub.venue}</p>',
        f'{i3}<a href="{_escape_attr(pub.link)}" class="pub-link"'
        f' target="_blank" rel="noopener noreferrer"'
        f' aria-label="{aria_label}">{_escape_text(pub.link_label)}</a>',
        f"{i2}</div>",
    ]
    return "\n".join(lines) + "\n"


def render_list(
    pubs: list[Publication], highlight_author: str = HIGHLIGHT_AUTHOR
) -> str:
    """Render publications into deterministic `.pub-year` -> `.publication` markup.

    Pure function: no I/O, no globals mutated, output depends only on ``pubs``.

    Ordering (Req 3.4):
        - Years are grouped and rendered in strictly DESCENDING order, with the
          undated bucket (year == 0) always placed LAST regardless of value.
        - Within a year, publications are sorted by title ASCENDING as a stable,
          deterministic tiebreak.

    Output shape matches the existing publications.html pattern (Req 3.3):
    each year is a `.pub-year` block at 16-space indent whose <h2> is the year
    (or "Undated" for the 0 bucket), containing one `.publication` per entry.

    Determinism (Req 3.5, 3.6): fixed indentation, fixed field order, stable
    sorts, and a single blank line separating year blocks make the output
    byte-stable for identical input. An empty list returns "".

    ``highlight_author`` (default ``HIGHLIGHT_AUTHOR``) is the surname bolded in
    every entry's author list, applied after escaping; ``""`` disables it. It is
    part of the pure input, so determinism still holds for a fixed value.
    """
    if not pubs:
        return ""

    # Group by year.
    groups: dict[int, list[Publication]] = {}
    for pub in pubs:
        groups.setdefault(pub.year, []).append(pub)

    # Years descending; undated (0) forced last regardless of other values.
    ordered_years = sorted(groups, key=lambda y: (y != 0, y), reverse=True)

    year_blocks: list[str] = []
    for year in ordered_years:
        heading = _UNDATED_HEADING if year == 0 else str(year)
        # Title-ascending, stable tiebreak within the year.
        entries = sorted(groups[year], key=lambda p: p.title)

        block_lines = [
            f'{_BASE_INDENT}<div class="pub-year">',
            f'{_BASE_INDENT}    <h2>{_escape_text(heading)}</h2>',
        ]
        block = "\n".join(block_lines) + "\n"
        block += "".join(
            _render_publication(entry, highlight_author) for entry in entries
        )
        block += f"{_BASE_INDENT}</div>\n"
        year_blocks.append(block)

    # One blank line between year blocks; single trailing newline overall.
    return "\n".join(year_blocks)

# --- Injection (task 4.3) -------------------------------------------------
#
# The rendered block is spliced into publications.html between two HTML-comment
# sentinels that live inside `.publications-list` (design "Sentinel scheme"):
#
#     <div class="publications-list">
#         <!-- PUBLICATIONS:START -->
#         ... generated .pub-year blocks ...
#         <!-- PUBLICATIONS:END -->
#     </div>
#
# inject() replaces ONLY the text strictly between the two sentinel markers.
# Everything before and including START, and everything from END onward, is
# preserved byte-for-byte -- including the sentinel comment strings themselves
# and the leading indentation of the START line (which sits in the prefix).
#
# Whitespace/newline contract around the sentinels (must stay in lock-step with
# the injection property tests, task 5.2):
#
#     <prefix ...>PUBLICATIONS:START -->        <- kept verbatim (incl. indent)
#     \n                                        <- exactly one newline after START
#     <rendered>                                <- render_list() output; it starts
#                                                  at 16-space indent and already
#                                                  ends with a single "\n"
#     <end_indent><!-- PUBLICATIONS:END -->     <- END kept verbatim; end_indent is
#                                                  the horizontal whitespace on the
#                                                  END marker's own line (16 spaces)
#
# Concretely the middle region is:  "\n" + rendered + end_indent
# (and just "\n" + end_indent when `rendered` is empty). No blank lines are
# emitted before END, so any pre-existing blank padding collapses on the first
# run and never grows again -- that is what makes inject() IDEMPOTENT: running
# it on already-injected HTML with the same rendered block yields byte-identical
# output. `end_indent` is read from the current END line rather than hard-coded
# so the splice tracks the file's real indentation, but falls back to the known
# 16-space base indent if the END marker shares its line with other content.

PUBLICATIONS_START = "<!-- PUBLICATIONS:START -->"
PUBLICATIONS_END = "<!-- PUBLICATIONS:END -->"


class SentinelError(ValueError):
    """Raised when the publications.html sentinels are missing or out of order.

    The marker-based injection refuses to guess where the generated block
    belongs: if either sentinel is absent (or END precedes START) the run must
    fail (Req 3.7 / design "Missing sentinels"), protecting a hand-edited file
    whose markers were removed.
    """


def inject(html_text: str, rendered: str) -> str:
    """Splice ``rendered`` between the PUBLICATIONS sentinels in ``html_text``.

    Pure function. Locates ``<!-- PUBLICATIONS:START -->`` and
    ``<!-- PUBLICATIONS:END -->`` and replaces ONLY the text strictly between
    them, preserving every byte before/including START and from END onward,
    the sentinel comment strings byte-for-byte included (Req 3.7).

    The replacement is deterministic and idempotent: the region becomes
    ``"\\n" + rendered + end_indent`` (or ``"\\n" + end_indent`` when
    ``rendered`` is empty), where ``end_indent`` is the whitespace preceding the
    END marker on its own line. Re-running inject on already-injected HTML with
    the same ``rendered`` returns byte-identical output.

    Raises:
        SentinelError: if START or END is missing, or END appears before (or
            overlapping) START. This must abort the run rather than guessing.
    """
    start_pos = html_text.find(PUBLICATIONS_START)
    if start_pos == -1:
        raise SentinelError(
            f"Missing start sentinel {PUBLICATIONS_START!r} in publications.html"
        )

    end_pos = html_text.find(PUBLICATIONS_END)
    if end_pos == -1:
        raise SentinelError(
            f"Missing end sentinel {PUBLICATIONS_END!r} in publications.html"
        )

    after_start = start_pos + len(PUBLICATIONS_START)
    if end_pos < after_start:
        raise SentinelError(
            "End sentinel appears before (or overlaps) the start sentinel in "
            "publications.html"
        )

    prefix = html_text[:after_start]
    suffix = html_text[end_pos:]

    # Indentation on the END marker's own line: the horizontal whitespace from
    # the newline preceding END up to the marker. Reused so the END line keeps
    # its indentation; falls back to the base 16-space indent if the END marker
    # unexpectedly shares its line with non-whitespace content.
    line_start = html_text.rfind("\n", 0, end_pos) + 1
    end_line_prefix = html_text[line_start:end_pos]
    end_indent = end_line_prefix if end_line_prefix.strip() == "" else _BASE_INDENT

    if rendered:
        middle = "\n" + rendered + end_indent
    else:
        middle = "\n" + end_indent

    return prefix + middle + suffix

# --- Threshold guard (task 4.4) -------------------------------------------
#
# The guard is the pipeline's non-destructive safety valve (design Component 4
# stage "Guard"). It runs on the SCHOLAR-fetched, normalized count -- BEFORE the
# curated merge -- so a blocked or empty fetch can never silently fall back to
# only the curated entries and overwrite the last good page. If the fetch
# returned fewer records than expected the run aborts and commits nothing,
# leaving the Last_Good_Version intact (Req 3.9, 3.10, 5.5).
#
# The zero-record case (Req 3.10) is a special case of the general
# below-threshold check: with the default threshold of 1, an empty Scholar
# result raises. The threshold is configurable via ``min_threshold`` so a
# profile known to have many publications can demand a higher floor.


class BelowThresholdError(ValueError):
    """Raised when the Scholar-fetched count is under the required minimum.

    Signals a non-destructive abort: the fetch succeeded but returned fewer
    publications than ``min_threshold`` (which defaults to 1, so this also
    covers the zero-record case, Req 3.10). ``main()`` (task 4.5) treats this as
    a non-zero exit that makes no commit, preserving the live page (Req 5.5).
    """


def check_threshold(pubs, min_threshold: int = 1) -> int:
    """Guard the Scholar-fetched publication count against ``min_threshold``.

    Operates on the normalized, Scholar-fetched list BEFORE the curated merge
    (design Component 4 stage "Guard"). Raises when the count is under the floor
    so a blocked/empty fetch aborts the run instead of degrading the page.

    Args:
        pubs: the normalized Scholar-fetched publications (any sized sequence).
        min_threshold: the minimum acceptable count; defaults to 1 so an empty
            result (zero records, Req 3.10) fails. Configurable for profiles
            that should demand a higher floor.

    Returns:
        The fetched count when it meets or exceeds ``min_threshold``.

    Raises:
        BelowThresholdError: when ``len(pubs) < min_threshold``. The message
            states the fetched count and the required minimum.
    """
    count = len(pubs)
    if count < min_threshold:
        raise BelowThresholdError(
            f"Scholar returned {count} publication(s), below the required "
            f"minimum of {min_threshold}; aborting without changes."
        )
    return count

# --- Curated source + merge/dedupe (task 4.6) -----------------------------
#
# The two publications currently hand-written in publications.html (the 2025
# IJDRR firefighter navigation paper and the 2020 encyclopedia chapter) must be
# preserved with their exact hand-authored wording (design "Existing
# hand-entered publications (curated-merge strategy)", Req 3.3 / 5.4). Rather
# than let Scholar's version overwrite them, they live in a small JSON file next
# to this script and are merged into the Scholar-derived list AFTER the
# threshold guard (which still runs on the Scholar-fetched count, per design
# Component 4 stage "Guard"). On any collision the curated entry wins.
#
# Dedup key (must stay in lock-step with the Property 7 test, task 5.8): two
# publications are "the same work" when EITHER
#   (a) their normalized titles match -- normalization is: casefold, strip
#       surrounding whitespace, remove punctuation (every non-word,
#       non-whitespace char), then collapse internal whitespace runs to a single
#       space; OR
#   (b) they share a DOI -- the case-folded path after "doi.org/" (trailing
#       slash stripped) is equal and non-empty on both.
# merge() keeps all curated entries (each exactly once), then appends every
# Scholar entry that is NOT a duplicate of a curated one, preserving the
# Scholar input order -- a fixed, deterministic rule.

import json
from pathlib import Path

# Curated file resolved relative to THIS script (via __file__) so the generator
# finds it regardless of the current working directory (e.g. CI checkouts).
_CURATED_PATH = Path(__file__).with_name("curated_publications.json")

# Keys every curated JSON record must provide (Publication-shaped).
_CURATED_FIELDS = ("authors", "title", "venue", "year", "link", "link_label")


def _dedup_key(pub: Publication) -> str:
    """Return the normalized-title dedup key for ``pub`` (pure).

    Normalization (case-insensitive, punctuation-and-whitespace-insensitive):
        1. casefold,
        2. strip surrounding whitespace,
        3. remove every character that is neither a word char nor whitespace
           (drops punctuation such as ':', '.', ',', '-'),
        4. collapse internal whitespace runs to a single space.

    Two titles that differ only in case, punctuation, or spacing map to the same
    key, so a Scholar entry restating a curated title collapses onto it.
    """
    text = (pub.title or "").casefold().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _doi_key(pub: Publication) -> str:
    """Return the normalized DOI of ``pub`` for cross-source matching, else "".

    Only ``doi.org`` links yield a key: the case-folded path after ``doi.org/``
    with any trailing slash removed. Non-DOI links (Scholar/pub_url) return "",
    so they never match on DOI (they can still match on title).
    """
    link = (pub.link or "").strip()
    if "doi.org/" not in link:
        return ""
    doi = link.split("doi.org/", 1)[1].strip().rstrip("/")
    return doi.casefold() if doi else ""


def load_curated(path: "str | Path | None" = None) -> list[Publication]:
    """Load the curated hand-entered publications into ``Publication`` records.

    Reads the JSON array at ``path`` (default: ``curated_publications.json``
    next to this script, resolved via ``__file__`` so CWD is irrelevant) and
    builds one ``Publication`` per record, coercing ``year`` to ``int``.

    This file is a packaged repository asset, so its absence or corruption is a
    real failure, not a soft fallback: the function raises rather than returning
    an empty list.

    Raises:
        FileNotFoundError: the curated file does not exist / cannot be read.
        ValueError: the file is not valid JSON, is not a JSON array, has a
            non-object entry, is missing a required field, or has a non-integer
            ``year``.
    """
    curated_path = Path(path) if path is not None else _CURATED_PATH

    try:
        raw = curated_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Curated publications file not found: {curated_path}"
        ) from exc
    except OSError as exc:
        raise ValueError(
            f"Could not read curated publications file {curated_path}: {exc}"
        ) from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Curated publications file {curated_path} is not valid JSON: {exc}"
        ) from exc

    if not isinstance(data, list):
        raise ValueError(
            f"Curated publications file {curated_path} must contain a JSON array, "
            f"got {type(data).__name__}."
        )

    pubs: list[Publication] = []
    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ValueError(
                f"Curated entry #{index} in {curated_path} must be a JSON object, "
                f"got {type(entry).__name__}."
            )
        missing = [field for field in _CURATED_FIELDS if field not in entry]
        if missing:
            raise ValueError(
                f"Curated entry #{index} in {curated_path} is missing required "
                f"field(s): {', '.join(missing)}."
            )
        try:
            year = int(entry["year"])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Curated entry #{index} in {curated_path} has a non-integer "
                f"year: {entry['year']!r}."
            ) from exc

        pubs.append(
            Publication(
                title=str(entry["title"]).strip(),
                authors=str(entry["authors"]),
                venue=str(entry["venue"]),
                year=year,
                link=str(entry["link"]).strip(),
                link_label=str(entry["link_label"]),
            )
        )
    return pubs


def merge(
    curated: list[Publication], scholarly_pubs: list[Publication]
) -> list[Publication]:
    """Return the deduplicated union of curated and Scholar-derived publications.

    Every curated entry is kept (each appears exactly once) and always wins on a
    collision: a Scholar entry is dropped when it duplicates a curated entry by
    EITHER normalized title (``_dedup_key``) OR shared DOI (``_doi_key``). All
    non-duplicate Scholar entries are retained.

    The output order is deterministic and fixed: curated entries first (in their
    input order) followed by the surviving Scholar entries in their input order.
    Final display order is decided later by ``render_list`` (year desc, title
    asc), so this order only needs to be stable, not display-ready.

    Runs AFTER ``check_threshold`` (design Component 4): the threshold guard is
    evaluated on the Scholar-fetched count so a blocked/empty fetch never
    degrades to rendering only the curated entries.
    """
    curated_title_keys: set[str] = set()
    curated_doi_keys: set[str] = set()

    merged: list[Publication] = []
    for pub in curated or []:
        merged.append(pub)
        curated_title_keys.add(_dedup_key(pub))
        doi = _doi_key(pub)
        if doi:
            curated_doi_keys.add(doi)

    for pub in scholarly_pubs or []:
        title_key = _dedup_key(pub)
        doi = _doi_key(pub)
        is_duplicate = title_key in curated_title_keys or (
            bool(doi) and doi in curated_doi_keys
        )
        if is_duplicate:
            continue
        merged.append(pub)

    return merged

# --- Fetch layer + CLI/main wiring (task 4.5) -----------------------------
#
# This is the only stage that touches the network and the fragile `scholarly`
# library, so it is kept deliberately thin and defensive (design Component 4,
# stages 1 and 7, and the "Retrieval failure" Error Handling section).
#
# `scholarly` is imported LAZILY inside `fetch_publications` (never at module
# import time) for two reasons: (1) the pure transformation core above must stay
# importable and unit-testable without the dependency installed, and (2) tests
# mock the fetch by injecting a fake `scholarly` module into `sys.modules`. The
# rest of the module has no runtime dependency on it.
#
# Timeout/retry model (Req 3.2, 5.6, 5.7):
#   * The fetch is retried up to `max_retries` attempts (default 3). Any
#     exception raised during an attempt is caught, logged to stderr, and — if
#     attempts remain — retried after a short backoff sleep. When the final
#     attempt fails, a `RetrievalError` is raised, chaining the last exception.
#   * Each attempt as a whole is bounded to `attempt_timeout` seconds
#     (default 120). This is enforced two ways for robustness: a SIGALRM
#     wall-clock alarm on Unix main-thread runs (the CI environment), AND an
#     internal monotonic-clock deadline that is re-checked before the author
#     lookup, after the profile fill, and before/after each per-publication
#     fill. Either mechanism turns an over-long attempt into a `TimeoutError`,
#     which the retry loop treats like any other attempt failure.
#   * `request_timeout` (default 30s) bounds an individual network request.
#     `scholarly` does not expose a per-request timeout hook cleanly, so this is
#     applied best-effort against its underlying requests session when reachable
#     and otherwise documented as a soft bound; the hard guarantee that a stuck
#     attempt cannot hang the job comes from the `attempt_timeout` guard above.
#
# Exit-code contract of main() (design "Exit codes"):
#   0        success — the file was rewritten with new content
#   0        identical — regeneration matched the current file, nothing written
#   non-zero (1) RetrievalError        (retrieval failure after retries)
#   non-zero (1) BelowThresholdError   (below-threshold / zero records)
#   non-zero (1) SentinelError         (sentinels missing / out of order)
#   non-zero (1) html file unreadable / unwritable
#   non-zero (1) load_curated failure  (missing / corrupt curated JSON)
# On every non-zero path the html file is left byte-for-byte unchanged
# (non-destructive default, Req 3.9, 3.10, 5.1, 5.2, 5.5); the write only ever
# happens on the success path and only when the new bytes differ.

import argparse
import signal
import sys
import threading
import time

# Default target file, resolved relative to THIS script's parent (repo root) so
# the generator is CWD-independent (e.g. under a CI checkout).
_DEFAULT_HTML_FILE = Path(__file__).resolve().parent.parent / "publications.html"

# Default Scholar user id for the lab profile (Req 3.2).
_DEFAULT_AUTHOR_ID = "Xu5F1CAAAAAJ"

# Backoff (seconds) slept between failed fetch attempts.
_RETRY_BACKOFF_SECONDS = 2.0


class RetrievalError(Exception):
    """Raised when the Google Scholar fetch fails after all retries.

    Google Scholar has no API and actively blocks scrapers, so an exhausted
    fetch is an *expected*, non-fatal outcome (design "Retrieval failure").
    ``main()`` maps this to a non-zero exit that commits nothing and leaves
    ``publications.html`` untouched (Req 3.9, 5.1, 5.2, 5.3).
    """


class _AttemptTimeout(TimeoutError):
    """Internal: a single fetch attempt exceeded its wall-clock budget."""


def _configure_request_timeout(scholarly_module, request_timeout: float) -> None:
    """Best-effort: apply a per-request timeout to scholarly's HTTP session.

    ``scholarly`` does not expose a clean per-request timeout, so this reaches
    for the underlying navigator/session only when present and silently does
    nothing otherwise. The hard attempt bound (``attempt_timeout``) is what
    actually guarantees an attempt cannot hang; this is a softer refinement
    (Req 5.7).
    """
    if request_timeout is None or request_timeout <= 0:
        return
    # scholarly's internals are private and version-dependent; probing them is
    # entirely optional and must never raise into the fetch path.
    try:  # pragma: no cover - depends on scholarly internals at runtime
        navigator = getattr(scholarly_module, "_Scholarly__nav", None)
        session = getattr(navigator, "_session", None) if navigator else None
        if session is not None:
            session.request = _wrap_session_request(session.request, request_timeout)
    except Exception:
        # A failed probe is non-fatal: fall back to the attempt-level guard.
        pass


def _wrap_session_request(original, request_timeout: float):
    """Wrap a requests-style ``session.request`` to inject a default timeout."""

    def _request(*args, **kwargs):  # pragma: no cover - runtime-only path
        kwargs.setdefault("timeout", request_timeout)
        return original(*args, **kwargs)

    return _request


def _fetch_once(author_id: str, request_timeout: float, attempt_timeout: float) -> list:
    """Perform a single Scholar fetch attempt; return raw normalize-shaped dicts.

    Imports ``scholarly`` lazily, looks up the author by id, fills the profile's
    publications section, then fills each publication to populate its ``bib``
    fields. Returns a list of records shaped like ``normalize()`` expects: each
    a dict with a ``bib`` dict plus ``pub_url``/``author_pub_id`` when available.

    An internal monotonic deadline (``attempt_timeout``) is checked at each
    coarse step so a slow attempt aborts with ``_AttemptTimeout`` even where the
    SIGALRM guard is unavailable (e.g. non-main-thread test runners).
    """
    from scholarly import scholarly  # lazy: keeps the module import dependency-free

    _configure_request_timeout(scholarly, request_timeout)

    deadline = time.monotonic() + attempt_timeout if attempt_timeout and attempt_timeout > 0 else None

    def _check_deadline() -> None:
        if deadline is not None and time.monotonic() > deadline:
            raise _AttemptTimeout(
                f"fetch attempt exceeded {attempt_timeout:g}s budget"
            )

    _check_deadline()
    author = scholarly.search_author_id(author_id)
    if author is None:
        raise ValueError(f"Scholar returned no author for id {author_id!r}")

    _check_deadline()
    filled_author = scholarly.fill(author, sections=["publications"])
    if filled_author is not None:
        author = filled_author

    publications = author.get("publications", []) if isinstance(author, dict) else []

    records: list[dict] = []
    for pub in publications or []:
        _check_deadline()
        try:
            filled_pub = scholarly.fill(pub)
        except Exception:
            # A single publication that won't fill still contributes whatever
            # bib it already carries rather than aborting the whole attempt.
            filled_pub = pub
        _check_deadline()

        if not isinstance(filled_pub, dict):
            continue

        bib = filled_pub.get("bib")
        record: dict = {"bib": dict(bib) if isinstance(bib, dict) else {}}

        pub_url = filled_pub.get("pub_url")
        if pub_url:
            record["pub_url"] = pub_url
        author_pub_id = filled_pub.get("author_pub_id")
        if author_pub_id:
            record["author_pub_id"] = author_pub_id

        records.append(record)

    return records


def _run_with_alarm(seconds: float, func):
    """Run ``func`` under a SIGALRM wall-clock alarm when possible.

    On Unix and only from the main thread, a ``SIGALRM`` fires after ``seconds``
    and raises ``_AttemptTimeout`` to interrupt a stuck call. Where SIGALRM is
    unavailable (Windows, or a non-main thread such as a test runner) this is a
    no-op wrapper and the internal deadline check in ``_fetch_once`` is the only
    guard. Either way the attempt is bounded.
    """
    use_alarm = (
        seconds
        and seconds > 0
        and hasattr(signal, "SIGALRM")
        and threading.current_thread() is threading.main_thread()
    )
    if not use_alarm:
        return func()

    def _handler(signum, frame):
        raise _AttemptTimeout(f"fetch attempt exceeded {seconds:g}s budget")

    previous = signal.signal(signal.SIGALRM, _handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        return func()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def fetch_publications(
    author_id: str,
    max_retries: int = 3,
    request_timeout: float = 30,
    attempt_timeout: float = 120,
) -> list[dict]:
    """Fetch raw Scholar publication records for ``author_id`` with retries.

    Uses ``scholarly`` (imported lazily) to look up the author, fill the profile,
    and retrieve each publication's bib. Returns a list of raw record dicts in
    the shape ``normalize()`` consumes.

    Retry/timeout behavior (Req 3.2, 5.6, 5.7):
        - Up to ``max_retries`` attempts. Each attempt is bounded to
          ``attempt_timeout`` seconds (SIGALRM guard + internal deadline) and
          individual requests are bounded best-effort to ``request_timeout``.
        - Any exception during an attempt is logged to stderr and retried after
          a short backoff, unless it was the final attempt.

    Raises:
        RetrievalError: when every attempt failed. The last underlying
            exception is chained for diagnostics.
    """
    attempts = max(1, int(max_retries))
    last_exc: BaseException | None = None

    for attempt in range(1, attempts + 1):
        try:
            return _run_with_alarm(
                attempt_timeout,
                lambda: _fetch_once(author_id, request_timeout, attempt_timeout),
            )
        except Exception as exc:  # noqa: BLE001 - any failure is a retryable attempt
            last_exc = exc
            print(
                f"[fetch] attempt {attempt}/{attempts} failed: "
                f"{type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            if attempt < attempts:
                time.sleep(_RETRY_BACKOFF_SECONDS)

    raise RetrievalError(
        f"Failed to retrieve publications for author id {author_id!r} after "
        f"{attempts} attempt(s)."
    ) from last_exc


def _build_arg_parser() -> argparse.ArgumentParser:
    """Construct the CLI parser (defaults match the design's configuration surface)."""
    parser = argparse.ArgumentParser(
        prog="generate_publications.py",
        description=(
            "Regenerate the publications list in publications.html from a Google "
            "Scholar profile (fetch -> normalize -> threshold guard -> curated "
            "merge -> render -> inject -> write-if-different)."
        ),
    )
    parser.add_argument(
        "--author-id",
        default=_DEFAULT_AUTHOR_ID,
        help="Google Scholar user id to fetch (default: %(default)s).",
    )
    parser.add_argument(
        "--html-file",
        default=str(_DEFAULT_HTML_FILE),
        help="Target HTML file containing the PUBLICATIONS sentinels "
        "(default: publications.html at the repo root).",
    )
    parser.add_argument(
        "--min-threshold",
        type=int,
        default=1,
        help="Minimum Scholar-fetched publication count; below this the run "
        "aborts without changes (default: %(default)s).",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum Scholar fetch attempts before failing (default: %(default)s).",
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=30,
        help="Per-request timeout in seconds, best-effort (default: %(default)s).",
    )
    parser.add_argument(
        "--attempt-timeout",
        type=float,
        default=120,
        help="Per-attempt overall timeout in seconds (default: %(default)s).",
    )
    parser.add_argument(
        "--highlight-author",
        default=HIGHLIGHT_AUTHOR,
        help="Surname to wrap in <strong> in every rendered author list; pass an "
        "empty string to disable bolding (default: %(default)s).",
    )
    parser.add_argument(
        "--curated-file",
        default=None,
        help="Path to the curated publications JSON (default: the packaged "
        "curated_publications.json next to this script).",
    )
    return parser


def main(argv=None) -> int:
    """Orchestrate the full publication-sync pipeline. Returns a process exit code.

    Stage order (design Component 4): fetch -> normalize -> check_threshold (on
    the Scholar-fetched, normalized count, BEFORE the curated merge) ->
    load_curated + merge -> render_list -> read html -> inject ->
    write-only-if-different.

    Returns 0 on success (whether or not a write happened; identical output
    writes nothing). Returns 1 on any failure — retrieval, below-threshold,
    sentinel, curated-load, or html read/write error — printing a reason to
    stderr and leaving the html file byte-for-byte unchanged (Req 3.9, 3.10,
    5.1, 5.2, 5.5).
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    # 1. Fetch (network + scholarly).
    try:
        raw_records = fetch_publications(
            args.author_id,
            max_retries=args.max_retries,
            request_timeout=args.request_timeout,
            attempt_timeout=args.attempt_timeout,
        )
    except RetrievalError as exc:
        print(f"ERROR: retrieval failure — {exc}", file=sys.stderr)
        return 1

    # 2. Normalize into the internal model.
    scholar_pubs = normalize(raw_records)

    # 3. Threshold guard on the Scholar-fetched count (before curated merge).
    try:
        count = check_threshold(scholar_pubs, args.min_threshold)
    except BelowThresholdError as exc:
        print(f"ERROR: below-threshold — {exc}", file=sys.stderr)
        return 1
    print(f"[sync] Scholar returned {count} publication(s) (>= {args.min_threshold}).")

    # 4. Load curated hand-entered records + merge/dedupe (curated wins).
    try:
        curated = load_curated(args.curated_file)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: curated load failure — {exc}", file=sys.stderr)
        return 1
    merged = merge(curated, scholar_pubs)

    # 5. Render the deterministic markup block.
    rendered = render_list(merged, args.highlight_author)

    # 6. Read the current html file.
    html_path = Path(args.html_file)
    try:
        current_bytes = html_path.read_bytes()
    except OSError as exc:
        print(f"ERROR: cannot read html file {html_path} — {exc}", file=sys.stderr)
        return 1

    # 7. Inject between the sentinels.
    try:
        new_text = inject(current_bytes.decode("utf-8"), rendered)
    except SentinelError as exc:
        print(f"ERROR: sentinel/injection failure — {exc}", file=sys.stderr)
        return 1
    except UnicodeDecodeError as exc:
        print(f"ERROR: cannot decode html file {html_path} — {exc}", file=sys.stderr)
        return 1

    new_bytes = new_text.encode("utf-8")

    # 8. Write only if the bytes actually differ (a clean regen is a disk no-op).
    if new_bytes == current_bytes:
        print(f"[sync] No change: {html_path} already up to date.")
        return 0

    try:
        html_path.write_bytes(new_bytes)
    except OSError as exc:
        print(f"ERROR: cannot write html file {html_path} — {exc}", file=sys.stderr)
        return 1

    print(f"[sync] Updated {html_path}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
