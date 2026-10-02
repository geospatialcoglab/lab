"""Generate the news article list and the home page news preview from Markdown.

This is the news pipeline's Generator_Script (design Components 2 to 8). One
post is one file in ``content/news/`` named ``<slug>.md``, and that file is the
only place the post's content exists. A single run renders BOTH targets from the
same parsed post set, so the full article list in ``news.html`` and the
condensed mirror in ``index.html`` cannot fall out of sync:

    discover -> split front matter -> validate -> parse body -> Post
        -> order -> render_news / render_preview -> inject -> write-if-different

Everything before the write is a pure function over in-memory values. Reading,
rendering, and injecting both pages all complete before the first byte is
written, which is what makes the all-or-nothing guarantee cheap: any failure
leaves both pages byte identical to how they started.

Two properties carried over from the publications pipeline are what make this
safe, and neither may be reordered:

1. Escape first, then add markup. Every text value taken from a post file is
   HTML escaped before any inline conversion runs, so the only raw tags in the
   output are the ones this module writes. ``html.escape`` leaves ``[``, ``]``,
   ``(``, ``)``, and ``*`` untouched, so every delimiter the inline grammar
   needs survives the escape.
2. Marker-based injection is byte preserving and idempotent, so a clean
   regeneration is a disk no-op.

Standard library only: no network call, no credential, no third-party
dependency, so CI needs no ``pip install``. One consequence is that there is no
Markdown library here, so the accepted body syntax is an explicitly defined
subset (paragraphs, ``## `` subheadings, ``- `` list items, ``[label](target)``,
``**strong**``, ``*em*``) and anything outside it is a hard error naming the
post and the line number rather than a silent misrendering.

House dash rule: an em dash (U+2014) or an en dash (U+2013) anywhere in a post
file is rejected, because word processors insert them silently and the site's
style does not use them.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

# Repo root = parent of this scripts/ directory. Every default path is resolved
# from __file__ so the generator is working-directory independent.
_REPO_ROOT = Path(__file__).resolve().parent.parent

# Import the shared HTML primitives under their canonical package name so the
# module identity (and therefore `SentinelError`) is the same object whether
# this file is imported as ``scripts.generate_news`` (tests, with the repo root
# on sys.path) or run as ``python scripts/generate_news.py`` (sys.path[0] is
# scripts/, so the ``scripts`` package is not visible until the repo root is
# added below).
try:
    from scripts.site_html import (
        SentinelError,
        escape_attr,
        escape_text_content,
        inject_between,
        new_tab_aria_label,
    )
except ModuleNotFoundError:  # run directly as a script
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from scripts.site_html import (  # noqa: E402  (path setup must precede it)
        SentinelError,
        escape_attr,
        escape_text_content,
        inject_between,
        new_tab_aria_label,
    )


# --- Constants (each defined in exactly one place) -------------------------

# News_Data_Directory: source content, not a served page.
NEWS_DIR = _REPO_ROOT / "content" / "news"
NEWS_PAGE = _REPO_ROOT / "news.html"
HOME_PAGE = _REPO_ROOT / "index.html"

# Number of most recent posts mirrored on the home page. Read by
# render_preview() and by nothing else, so changing it here changes the home
# page on the next run with no edit to index.html.
PREVIEW_COUNT = 2

NEWS_START = "<!-- NEWS:START -->"
NEWS_END = "<!-- NEWS:END -->"
NEWS_PREVIEW_START = "<!-- NEWS_PREVIEW:START -->"
NEWS_PREVIEW_END = "<!-- NEWS_PREVIEW:END -->"

# Both sentinel pairs sit four levels deep in their pages, so an <article> lands
# at 16 spaces, its direct children at 20, and an <li> at 24.
BASE_INDENT = " " * 16

# Host treated as internal for link classification (this site).
INTERNAL_HOST = "geospatialcognitionlab.com"

REQUIRED_KEYS = ("title", "date", "teaser")
OPTIONAL_KEYS = ("short_title", "image", "image_alt")

# Hard-coded rather than calendar.month_name or strftime("%B"), both of which
# read the LC_TIME locale. Output must not depend on the machine it ran on.
MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

# The two characters the house style rejects, with the name used in the error.
EM_DASH = "\u2014"
EN_DASH = "\u2013"
_DASH_NAMES = ((EM_DASH, "em dash (U+2014)"), (EN_DASH, "en dash (U+2013)"))

# Appended to every unsupported-construct error so the fix is in the message.
ACCEPTED_SYNTAX = (
    "Accepted body syntax: paragraphs, '## ' subheadings, '- ' list items, "
    "[label](target), **strong**, *em*."
)

_SLUG_RE = re.compile(r"^[a-z0-9-]+$")
_DATE_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

# Inline grammar. Applied to ALREADY-ESCAPED text (see render_inline).
# A link target may not contain a parenthesis and a label may not contain a
# bracket; both cases are reported as unmatched markers rather than guessed at.
_LINK_RE = re.compile(r"\[([^\[\]]*)\]\(([^()]*)\)")
_STRONG_RE = re.compile(r"\*\*([^*]+)\*\*")
_EM_RE = re.compile(r"\*([^*]+)\*")

# Source-level rejections.
_HEADING_RE = re.compile(r"^(#+)(?: |$)")
_ORDERED_LIST_RE = re.compile(r"^\d+\. ")
_RAW_TAG_RE = re.compile(r"<[A-Za-z/]")

_FRONT_MATTER_DELIMITER = "---"


# --- Data model -----------------------------------------------------------

# A parsed body block, carrying its one-based source line number so error
# reporting does not have to rediscover it:
#   ("paragraph",  line_number, str)               lines joined by one space
#   ("subheading", line_number, str)               text after "## "
#   ("list",       line_number, tuple[str, ...])   one item per "- " line
Block = tuple[str, int, object]


@dataclass(frozen=True)
class Post:
    """One news post, holding RAW UNESCAPED source text in every text field.

    Escaping and inline conversion happen once, at render time, in
    :func:`render_inline`. Storing escaped text would invite double escaping,
    and storing HTML would let the model carry markup no renderer emitted,
    which is precisely what the escape-first ordering exists to prevent.

    Frozen with a tuple of tuples for ``blocks``, so a Post is hashable, two
    Posts compare by value, and no renderer can mutate a post another renderer
    will read. ``short_title`` and ``image`` use ``""`` for absence rather than
    ``None``, so ``short_title or title`` is the whole fallback.
    """

    slug: str
    title: str
    short_title: str
    year: int
    month: int
    teaser: str
    image: str
    image_alt: str
    blocks: tuple[Block, ...]

    @property
    def display_month(self) -> str:
        """Human label for the post month, e.g. ``"August 2026"`` (locale free)."""
        return f"{MONTH_NAMES[self.month - 1]} {self.year}"

    @property
    def order_key(self) -> tuple[int, int, str]:
        """Sort key for :func:`order_posts`: ``(year, month, slug)``."""
        return (self.year, self.month, self.slug)

    @property
    def headline(self) -> str:
        """Preview headline: ``short_title`` when supplied, otherwise ``title``."""
        return self.short_title or self.title


class PostError(ValueError):
    """A post file is invalid.

    The message always names the post first, either by slug or, when the slug
    itself is the fault, by file name, so a reviewer scanning a failed check
    sees which file to open before reading anything else. Where a line number is
    known it follows the slug as ``"<slug> line 7: ..."``.
    """


# --- Discovery ------------------------------------------------------------


def discover_post_files(directory: Path) -> list[tuple[str, Path]]:
    """Find the post files in ``directory`` as ``(slug, path)`` pairs.

    Globs ``*.md`` and skips any file whose name begins with an underscore, which
    is what keeps ``content/news/_template.md`` out of the generated pages. The
    result is sorted by slug so parsing, and therefore error reporting, has a
    deterministic order. Output ORDER for the pages does not come from here; it
    comes from :func:`order_posts`.

    Raises:
        PostError: when a slug contains anything outside ``[a-z0-9-]`` (naming
            the file), or when the directory holds no post file at all.
    """
    candidates = [
        path
        for path in directory.glob("*.md")
        if not path.name.startswith("_")
    ]
    candidates.sort(key=lambda path: path.stem)

    if not candidates:
        raise PostError(f"no post files found in {directory}")

    pairs: list[tuple[str, Path]] = []
    for path in candidates:
        slug = path.stem
        if not _SLUG_RE.match(slug):
            raise PostError(
                f"{path.name}: slug must contain only lowercase letters, "
                "digits, and hyphens"
            )
        pairs.append((slug, path))
    return pairs


# --- House dash rule ------------------------------------------------------


def check_dashes(slug: str, lines, first_line: int = 1) -> None:
    """Reject an em dash or an en dash anywhere in ``lines``.

    Scanning the whole post file (front matter values included) is the simplest
    way to cover every presented text value while still holding the one-based
    source line number and the source line itself, both of which the error
    message needs. The message is deliberately prescriptive: a contributor
    pasting from a word processor will hit this, cannot see the character, and
    needs the fix in the message rather than in a document they have not opened.

    Raises:
        PostError: naming the slug, the line number, which of the two
            characters was found, the quoted source line, and the fix.
    """
    for offset, line in enumerate(lines):
        for char, name in _DASH_NAMES:
            if char in line:
                quoted = line.rstrip("\n")
                raise PostError(
                    f"{slug} line {first_line + offset}: found an {name} in "
                    f'"{quoted}". Replace it with a comma, a colon, or the '
                    'word "to" for a numeric range.'
                )


# --- Front matter ---------------------------------------------------------


def split_front_matter(text: str, slug: str) -> tuple[dict[str, str], list[str], int]:
    """Split ``text`` into its raw front matter map, body lines, and body offset.

    The first line must be exactly ``---`` once trailing whitespace is stripped,
    and a later line must be exactly ``---``. Each line between them is
    ``key: value`` split on the FIRST colon only, which matters because a post
    title may contain a colon.

    Returns:
        ``(raw_key_map, body_lines, body_first_line_number)`` where the raw map
        preserves the source values unstripped and unvalidated, and the line
        number is one-based so body error messages point at the real line.

    Raises:
        PostError: when either delimiter is missing, when a front matter line
            carries no colon, or when a key is duplicated.
    """
    lines = text.split("\n")
    if not lines or lines[0].rstrip() != _FRONT_MATTER_DELIMITER:
        raise PostError(
            f"{slug}: front matter must open and close with a line containing "
            "only ---"
        )

    closing = None
    for index in range(1, len(lines)):
        if lines[index].rstrip() == _FRONT_MATTER_DELIMITER:
            closing = index
            break
    if closing is None:
        raise PostError(
            f"{slug}: front matter must open and close with a line containing "
            "only ---"
        )

    raw: dict[str, str] = {}
    for index in range(1, closing):
        line = lines[index]
        if not line.strip():
            continue
        if ":" not in line:
            raise PostError(
                f"{slug} line {index + 1}: front matter line must be "
                f'"key: value", got "{line.rstrip()}"'
            )
        key, value = line.split(":", 1)
        key = key.strip()
        if key in raw:
            raise PostError(f"{slug}: duplicate front matter key '{key}'")
        raw[key] = value

    return raw, lines[closing + 1 :], closing + 2


def parse_front_matter(raw: dict[str, str], slug: str) -> dict[str, str]:
    """Validate a raw front matter map and return the stripped, checked values.

    Keys are matched case sensitively against ``REQUIRED_KEYS + OPTIONAL_KEYS``;
    anything else is an error rather than an ignored line, because a silently
    dropped key hides a typo. Values are whitespace stripped. Absent optional
    keys come back as ``""``.

    Raises:
        PostError: for an unrecognized key, a missing required key, a required
            value that is empty after stripping, a ``date`` that is not
            ``YYYY-MM`` with a month from 01 to 12, or an ``image`` supplied
            without a non-empty ``image_alt``. Every message names the slug and
            the offending key or value.
    """
    accepted = REQUIRED_KEYS + OPTIONAL_KEYS

    for key in raw:
        if key not in accepted:
            raise PostError(
                f"{slug}: unrecognized front matter key '{key}'; accepted keys "
                f"are {', '.join(accepted)}"
            )

    values = {key: raw.get(key, "").strip() for key in accepted}

    for key in REQUIRED_KEYS:
        if key not in raw:
            raise PostError(f"{slug}: missing required front matter key '{key}'")
        if not values[key]:
            raise PostError(
                f"{slug}: front matter key '{key}' must not be empty"
            )

    date = values["date"]
    if not _DATE_RE.match(date):
        raise PostError(
            f"{slug}: date '{date}' must match YYYY-MM with a month from 01 to 12"
        )

    if values["image"] and not values["image_alt"]:
        raise PostError(
            f"{slug}: 'image' requires a non-empty 'image_alt' for the alt "
            "attribute"
        )

    return values


# --- Body parsing and source-level rejections -----------------------------


def _reject(slug: str, line_no: int, construct: str) -> None:
    """Raise a PostError for an unsupported construct, with the accepted syntax."""
    raise PostError(
        f"{slug} line {line_no}: unsupported Markdown construct "
        f"'{construct}'. {ACCEPTED_SYNTAX}"
    )


def check_line(slug: str, line_no: int, line: str) -> None:
    """Reject any construct on ``line`` that falls outside the accepted subset.

    Checked, each reported with the slug and the one-based line number: ``# ``
    and ``### `` or deeper headings (only ``## `` is accepted, because ``h1``
    belongs to the page and ``h3`` is the deepest level styles.css styles inside
    ``.news-article``), ordered list markers such as ``1. ``, backticks, body
    image syntax ``![alt](src)`` (images come from the ``image`` front matter key
    so ``image_alt`` can be enforced), block quote markers ``> ``, a leading
    table pipe, a raw HTML tag detected as ``<`` followed by a letter or ``/``,
    an unmatched ``**`` or ``*``, and an unmatched ``[``.

    Stray ``(`` and ``)`` are allowed: ordinary prose uses them, and the
    recruitment article does exactly that around two links.

    The unmatched-marker check runs the real inline substitution and looks for a
    leftover delimiter, so it cannot drift from what :func:`render_inline` will
    actually accept.
    """
    heading = _HEADING_RE.match(line)
    if heading:
        level = len(heading.group(1))
        if level == 1:
            _reject(slug, line_no, "level-1 heading")
        if level >= 3:
            _reject(slug, line_no, "heading deeper than a '## ' subheading")

    if line.lstrip().startswith("|"):
        _reject(slug, line_no, "table pipe")

    # Strip an accepted block marker so its own characters are not mistaken for
    # an inline construct.
    content = line
    if content.startswith("## "):
        content = content[3:]
    elif content.startswith("- "):
        content = content[2:]

    if _ORDERED_LIST_RE.match(content):
        _reject(slug, line_no, "ordered list marker")
    if "`" in content:
        _reject(slug, line_no, "backtick")
    if "![" in content:
        _reject(slug, line_no, "inline image")
    if content.startswith("> "):
        _reject(slug, line_no, "block quote")
    if _RAW_TAG_RE.search(content):
        _reject(slug, line_no, "raw HTML tag")

    leftover = render_inline(content)
    if "*" in leftover:
        _reject(slug, line_no, "unmatched emphasis marker")
    if "[" in leftover:
        _reject(slug, line_no, "unmatched link bracket")


def parse_body(lines: list[str], slug: str, first_line: int) -> tuple[Block, ...]:
    """Parse body ``lines`` into blocks, rejecting anything outside the subset.

    Blocks are separated by blank lines. Within a block: every line starting
    with ``- `` makes one list block whose items preserve source order, a single
    line starting with ``## `` makes a subheading, and anything else makes a
    paragraph whose lines are joined by a single space. Consecutive ``- `` lines
    with no blank line between them form exactly one list.

    ``first_line`` is the one-based source line number of ``lines[0]``, so every
    block, and every error, carries a line number that matches the file.

    Raises:
        PostError: for a multi-line ``## `` block, a block mixing ``- `` lines
            with non-``- `` lines, or any construct rejected by
            :func:`check_line`.
    """
    blocks: list[Block] = []
    current: list[tuple[int, str]] = []

    def flush() -> None:
        if not current:
            return
        line_no = current[0][0]
        texts = [text for _, text in current]

        if all(text.startswith("- ") for text in texts):
            items = tuple(text[2:].strip() for text in texts)
            blocks.append(("list", line_no, items))
        elif any(text.startswith("- ") for text in texts):
            raise PostError(
                f"{slug} line {line_no}: a list block must not mix '- ' items "
                "with other lines"
            )
        elif texts[0].startswith("## "):
            if len(texts) > 1:
                raise PostError(
                    f"{slug} line {line_no}: a '## ' subheading must be a "
                    "single line"
                )
            blocks.append(("subheading", line_no, texts[0][3:].strip()))
        else:
            blocks.append(("paragraph", line_no, " ".join(texts)))
        current.clear()

    for offset, raw_line in enumerate(lines):
        line_no = first_line + offset
        line = raw_line.rstrip()
        if not line.strip():
            flush()
            continue
        check_line(slug, line_no, line)
        current.append((line_no, line.strip()))
    flush()

    return tuple(blocks)


# --- Loading --------------------------------------------------------------


def build_post(slug: str, text: str) -> Post:
    """Build a validated :class:`Post` from ``slug`` and raw file ``text``.

    Order of checks: the house dash rule over the whole file first (so a
    contributor sees the invisible-character problem before anything else),
    then the front matter, then the body.
    """
    lines = text.split("\n")
    check_dashes(slug, lines, first_line=1)

    raw, body_lines, body_first_line = split_front_matter(text, slug)
    values = parse_front_matter(raw, slug)
    blocks = parse_body(body_lines, slug, body_first_line)

    year, month = values["date"].split("-")
    return Post(
        slug=slug,
        title=values["title"],
        short_title=values["short_title"],
        year=int(year),
        month=int(month),
        teaser=values["teaser"],
        image=values["image"],
        image_alt=values["image_alt"],
        blocks=blocks,
    )


def load_posts(directory: Path) -> tuple[Post, ...]:
    """Read and validate every post file in ``directory``, in slug order.

    The only impure function in the parsing half of the module. Files are read
    as UTF-8 and validated in slug order, so the first failure reported for a
    given directory is always the same one.

    Raises:
        PostError: for any invalid post, or when the directory holds no post.
        OSError, UnicodeDecodeError: propagated for main() to report.
    """
    posts: list[Post] = []
    for slug, path in discover_post_files(directory):
        posts.append(build_post(slug, path.read_text(encoding="utf-8")))
    return tuple(posts)


# --- Ordering -------------------------------------------------------------


def order_posts(posts) -> tuple[Post, ...]:
    """Order ``posts`` newest first, most recent month first, slug descending.

    A single reverse sort on ``(year, month, slug)`` gives month descending with
    slug descending as the tiebreak. Both renderers consume the output of this
    one function, so the article order and the preview selection cannot
    disagree, and nothing is derived from file system enumeration order.

    Accepts any iterable of :class:`Post` and returns a tuple.
    """
    return tuple(sorted(posts, key=lambda post: post.order_key, reverse=True))


# --- Inline rendering and link classification -----------------------------


def _is_external(target: str) -> bool:
    """Report whether ``target`` is an outbound link needing new-tab attributes.

    External means an absolute ``http`` or ``https`` URL whose host is neither
    ``geospatialcognitionlab.com`` nor one of its subdomains. Everything else is
    internal: a ``mailto:`` address, a relative path such as ``news.html``, a
    bare fragment, and the lab's own host.
    """
    parts = urlsplit(target)
    if parts.scheme not in ("http", "https"):
        return False
    host = (parts.hostname or "").lower()
    return host != INTERNAL_HOST and not host.endswith("." + INTERNAL_HOST)


def _link_replacement(match: "re.Match[str]") -> str:
    """Assemble one anchor from an ALREADY-ESCAPED ``[label](target)`` match.

    Because :func:`render_inline` escaped the whole string first, the target is
    already attribute safe (an ``&`` in a query string is already ``&amp;``), so
    it is emitted as-is rather than escaped a second time.

    Attribute order is fixed at ``href``, ``target``, ``rel``, ``aria-label`` so
    the output is byte stable. An external link gets ``target="_blank"`` plus
    ``rel="noopener noreferrer"``: ``noopener`` denies the opened page a handle
    on this one, ``noreferrer`` keeps the referrer from leaking. Since the
    visible label alone would not tell a screen-reader user about the new tab, an
    ``aria-label`` announces it. Every other anchor carries neither ``target``
    nor ``rel``.
    """
    label, target = match.group(1), match.group(2)
    if not _is_external(target):
        return f'<a href="{target}">{label}</a>'
    # NOT escaped again, deliberately. `label` arrives here already escaped by
    # render_inline (escape_text_content), so &, <, >, and " are
    # already entities and it is attribute safe as-is; new_tab_aria_label only
    # appends plain ASCII. Wrapping this in escape_attr would double encode, so
    # a label containing "&" would render as "&amp;amp;".
    aria_label = new_tab_aria_label(label)
    return (
        f'<a href="{target}" target="_blank" rel="noopener noreferrer" '
        f'aria-label="{aria_label}">{label}</a>'
    )


def render_inline(raw: str) -> str:
    """Escape ``raw``, then convert the three accepted inline forms.

    THE ORDERING IS THE SECURITY PROPERTY AND MUST NOT BE REARRANGED. Escaping
    runs first, so ``&``, ``<``, ``>``, and ``"`` taken from a post are entities
    before any markup is added and the only raw ``<`` in the result is one this
    function wrote: a ``<script>`` typed into a post body comes out as
    ``&lt;script&gt;``, visible text and not markup.

    The escaping is :func:`escape_text_content`, which covers exactly the four
    characters named by Requirement 2.7 and leaves the apostrophe as a literal.
    Only the character set narrowed; the escape-first ordering is unchanged and
    is still what makes the output safe. ``[``, ``]``, ``(``, ``)``, and ``*``
    are untouched by escaping either way, so every delimiter the inline grammar
    needs survives and the conversions below still work.

    Substitution order is links, then ``**strong**``, then ``*em*``, so a
    double asterisk is consumed before the single-asterisk form can split it.
    """
    out = escape_text_content(raw)
    out = _LINK_RE.sub(_link_replacement, out)
    out = _STRONG_RE.sub(lambda m: f"<strong>{m.group(1)}</strong>", out)
    out = _EM_RE.sub(lambda m: f"<em>{m.group(1)}</em>", out)
    return out


# --- Renderers ------------------------------------------------------------


def render_news(posts) -> str:
    """Render ``posts`` as the ``.news-list`` block for news.html.

    Pure function. Per post, an ``article.news-article`` at 16 spaces with its
    direct children at 20 and ``li`` elements at 24, matching both the existing
    page and the publications renderer's indentation contract. Element order is
    ``span.news-date``, ``h2``, an optional ``img.news-image`` with the fixed
    attribute order ``src``, ``alt``, ``class``, then the body blocks in source
    order as ``p``, ``h3``, and ``ul``/``li``. Articles are separated by one
    blank line, as they are on the page today.

    The title goes through :func:`render_inline` like any other post text, so a
    literal ``&`` in a title is emitted as ``&amp;``.

    Returns ``""`` for an empty input.
    """
    i1 = BASE_INDENT
    i2 = BASE_INDENT + " " * 4
    i3 = BASE_INDENT + " " * 8

    articles: list[str] = []
    for post in posts:
        lines = [
            f'{i1}<article class="news-article" id="{escape_attr(post.slug)}">',
            f'{i2}<span class="news-date">'
            f"{escape_text_content(post.display_month)}</span>",
            f"{i2}<h2>{render_inline(post.title)}</h2>",
        ]
        if post.image:
            lines.append(
                f'{i2}<img src="{escape_attr(post.image)}" '
                f'alt="{escape_attr(post.image_alt)}" class="news-image">'
            )
        for kind, _line_no, payload in post.blocks:
            if kind == "paragraph":
                lines.append(f"{i2}<p>{render_inline(payload)}</p>")
            elif kind == "subheading":
                lines.append(f"{i2}<h3>{render_inline(payload)}</h3>")
            elif kind == "list":
                lines.append(f"{i2}<ul>")
                for item in payload:
                    lines.append(f"{i3}<li>{render_inline(item)}</li>")
                lines.append(f"{i2}</ul>")
        lines.append(f"{i1}</article>")
        articles.append("\n".join(lines) + "\n")

    # One blank line between articles, single trailing newline overall.
    return "\n".join(articles)


def render_preview(posts, preview_count: int = PREVIEW_COUNT) -> str:
    """Render the first ``preview_count`` of ``posts`` as the home page mirror.

    Pure function. Slicing an already-ordered sequence handles a post count
    below ``preview_count`` with no special branch. Per previewed post, an
    ``article.news-item`` at 16 spaces holding ``span.news-date``, an ``h3``
    with ``short_title`` when supplied and ``title`` otherwise, and exactly one
    ``p`` holding the rendered teaser. The post body is never emitted here.
    Preview articles are not blank-line separated, matching index.html today.

    Returns ``""`` for an empty input or a non-positive ``preview_count``.
    """
    if preview_count <= 0:
        return ""

    i1 = BASE_INDENT
    i2 = BASE_INDENT + " " * 4

    articles: list[str] = []
    for post in tuple(posts)[:preview_count]:
        lines = [
            f'{i1}<article class="news-item">',
            f'{i2}<span class="news-date">'
            f"{escape_text_content(post.display_month)}</span>",
            f'{i2}<h3><a href="news.html#{escape_attr(post.slug)}">'
            f'{render_inline(post.headline)}</a></h3>',
            f"{i2}<p>{render_inline(post.teaser)}</p>",
            f"{i1}</article>",
        ]
        articles.append("\n".join(lines) + "\n")

    return "".join(articles)


# --- CLI, atomic write, and orchestration ---------------------------------


def _atomic_write(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` via a temp file in the same directory.

    The temp file lives beside the target so ``os.replace`` is a rename within
    one filesystem, which makes the swap atomic: a reader sees either the old
    file or the new one, never a half-written page. The temp file is removed if
    the write or the rename fails.
    """
    temp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        temp_path.write_bytes(data)
        os.replace(temp_path, path)
    except OSError:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise


def _build_arg_parser() -> argparse.ArgumentParser:
    """Construct the CLI parser (defaults mirror the publications generator)."""
    parser = argparse.ArgumentParser(
        prog="generate_news.py",
        description=(
            "Regenerate the news list in news.html and the news preview in "
            "index.html from the Markdown posts in content/news "
            "(discover -> validate -> render -> inject -> write-if-different)."
        ),
    )
    parser.add_argument(
        "--news-dir",
        default=str(NEWS_DIR),
        help="Directory holding the post files (default: content/news).",
    )
    parser.add_argument(
        "--news-file",
        default=str(NEWS_PAGE),
        help="Target page containing the NEWS sentinels (default: news.html).",
    )
    parser.add_argument(
        "--home-file",
        default=str(HOME_PAGE),
        help="Target page containing the NEWS_PREVIEW sentinels "
        "(default: index.html).",
    )
    parser.add_argument(
        "--preview-count",
        type=int,
        default=PREVIEW_COUNT,
        help="Number of most recent posts mirrored on the home page "
        "(default: %(default)s).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Render and compare without writing; exit non-zero when either "
        "page is out of date.",
    )
    return parser


def main(argv=None) -> int:
    """Run the whole pipeline. Returns a process exit code.

    Step order is what guarantees the all-or-nothing write: load and validate
    every post, order them, render both blocks, read BOTH pages, inject BOTH in
    memory, compute which targets actually differ, and only then write, each
    through a temp file moved into place. Nothing is written until every check
    has passed, so a missing sentinel in index.html cannot leave news.html
    already rewritten.

    A target whose bytes are unchanged is not written at all, so a clean
    regeneration touches no file and produces a zero-byte repository diff.

    Returns 0 on success whether or not anything was written, and 1 on any
    validation, sentinel, read, or write failure, with one reason line on
    stderr. If the second write fails, the error names both the file that was
    already updated and the one that was not, so the partial state is visible
    rather than silent.
    """
    args = _build_arg_parser().parse_args(argv)

    news_dir = Path(args.news_dir)
    news_path = Path(args.news_file)
    home_path = Path(args.home_file)

    # 1 and 2. Load, validate, order. Any problem here writes nothing.
    try:
        posts = load_posts(news_dir)
    except PostError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except UnicodeDecodeError as exc:
        print(f"ERROR: cannot decode a post file in {news_dir}: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"ERROR: cannot read a post file in {news_dir}: {exc}", file=sys.stderr)
        return 1

    ordered = order_posts(posts)

    # 3 and 4. Render both blocks from the one ordered sequence.
    news_block = render_news(ordered)
    preview_block = render_preview(ordered, args.preview_count)

    # 5. Read BOTH pages before any write.
    current: dict[Path, bytes] = {}
    for path in (news_path, home_path):
        try:
            current[path] = path.read_bytes()
        except OSError as exc:
            print(f"ERROR: cannot read {path}: {exc}", file=sys.stderr)
            return 1

    # 6 and 7. Inject BOTH in memory.
    plan = (
        (news_path, news_block, NEWS_START, NEWS_END),
        (home_path, preview_block, NEWS_PREVIEW_START, NEWS_PREVIEW_END),
    )
    updated: dict[Path, bytes] = {}
    for path, block, start_marker, end_marker in plan:
        try:
            text = current[path].decode("utf-8")
        except UnicodeDecodeError as exc:
            print(f"ERROR: cannot decode {path}: {exc}", file=sys.stderr)
            return 1
        try:
            new_text = inject_between(
                text, block, start_marker, end_marker, BASE_INDENT, path.name
            )
        except SentinelError as exc:
            print(f"ERROR: sentinel/injection failure: {exc}", file=sys.stderr)
            return 1
        updated[path] = new_text.encode("utf-8")

    # 8. Which targets actually differ.
    targets = [
        (path, data) for path, data in updated.items() if data != current[path]
    ]

    if args.check:
        if targets:
            stale = ", ".join(str(path) for path, _ in targets)
            print(
                f"ERROR: out of date: {stale}. Run "
                "'python scripts/generate_news.py' and commit the result.",
                file=sys.stderr,
            )
            return 1
        print("[news] Up to date: no change to news.html or index.html.")
        return 0

    if not targets:
        print("[news] No change: news.html and index.html already up to date.")
        return 0

    # 9. Write only the differing targets.
    written: list[Path] = []
    for path, data in targets:
        try:
            _atomic_write(path, data)
        except OSError as exc:
            message = f"ERROR: cannot write {path}: {exc}."
            if written:
                already = ", ".join(str(done) for done in written)
                message += (
                    f" {already} was already updated but {path} was not; "
                    "rerun after fixing."
                )
            print(message, file=sys.stderr)
            return 1
        written.append(path)

    print(f"[news] Updated {', '.join(str(path) for path in written)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
