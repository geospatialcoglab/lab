# Implementation Plan: News Authoring Workflow

## Overview

This plan builds the news pipeline in the order the design requires: shared HTML primitives first, then the generator core from the inside out (model, front matter, body parser, inline rendering, ordering, renderers, `main()`), then the migration of the three existing posts, then the documentation, then the review workflow, and finally the optional refactor of the already deployed publications generator.

Implementation language is Python 3.12, standard library only, matching `scripts/generate_publications.py`. Tests use `pytest` with `hypothesis`, already configured in `pytest.ini`, `requirements.txt`, and `tests/`. The existing suite stands at 67 passing tests and every task below is additive to it.

Sequencing rules that the task order encodes:

- `scripts/site_html.py` must exist before `scripts/generate_news.py` can import it (task 1 precedes task 2).
- Parsing and validation precede the renderers, the renderers precede `main()`, and `main()` precedes the workflow (tasks 2 and 3, then 5 through 7, then 9, then 13).
- The pre-migration news regions of `news.html` and `index.html` are captured as fixtures before anything edits those files, because the migration fidelity test compares against them and they cannot be recovered afterward (task 10.1 precedes task 10.4).
- The one time manual sentinel edit happens only after the three migrated post files exist and the generator can render them, so the pages are never empty in between (task 10.4 follows tasks 9.1 and 10.2).
- The refactor of `scripts/generate_publications.py` onto `site_html` is deliberately last (task 15). It touches deployed code, it is guarded by the existing 67 tests, and it can be deferred or skipped entirely without blocking the news pipeline.

## Tasks

- [ ] 1. Extract the shared HTML primitives into `scripts/site_html.py`
  - [ ] 1.1 Create `scripts/site_html.py`
    - Define `SentinelError(ValueError)`, `escape_text(value, quote=False)`, `escape_attr(value)`, and `new_tab_aria_label(label)`, carrying over the behavior of the publications generator's private helpers including the stripping of a trailing U+2192 arrow from an accessible name.
    - Implement `inject_between(html_text, rendered, start_marker, end_marker, default_indent, file_label="the target file")` as the existing `inject()` with the marker pair, the fallback indent, and the file name lifted into parameters.
    - Preserve the whitespace contract exactly: the middle region becomes `"\n" + rendered + end_indent`, or `"\n" + end_indent` when `rendered` is empty, where `end_indent` is the horizontal whitespace on the end marker's own line and `default_indent` is the fallback when the end marker shares its line with other content. Emit no blank padding before the end marker so repeated injection is byte identical.
    - Raise `SentinelError` naming the missing marker and the file when either marker is absent, and when the end marker precedes or overlaps the start marker.
    - Import nothing outside the standard library.
    - _Requirements: 5.1, 5.2, 5.3, 5.5, 5.6, 2.7, 2.9_

  - [ ]* 1.2 Create `tests/news_strategies.py`
    - Add Hypothesis strategies for inline text, hostile text whose alphabet includes `&`, `<`, `>`, `"`, `'` and whole injected strings such as `<script>`, `</p>`, `&amp;`, and `&lt;`, body blocks, serialized post files, post sets, link targets spanning `http`, `https`, `mailto:`, relative, fragment, self host, and subdomain forms, and host documents containing a sentinel pair with generated prefix, suffix, and end marker indentation.
    - Draw years and months from small pools so Post_Month ties actually occur and the slug tiebreak is exercised.
    - Keep this module separate from the existing `tests/strategies.py`, whose HTML safe alphabet is needed by the publications tests for the opposite reason.
    - _Requirements: 2.7, 2.9, 6.2_

  - [ ]* 1.3 Property test for injection in `tests/test_news_inject.py`
    - **Property 10: Injection preserves structure and is idempotent**
    - *For any* host document containing a well ordered sentinel pair and *for any* rendered block, injection leaves every byte up to and including the start marker and every byte from the end marker onward unchanged, the marker strings themselves included, and injecting the same rendered block into the result again yields byte identical output.
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**

- [ ] 2. Build the post model, discovery, and front matter validation in `scripts/generate_news.py`
  - [ ] 2.1 Define module constants, the data model, and discovery
    - Create `scripts/generate_news.py` importing only `argparse`, `dataclasses`, `html`, `os`, `pathlib`, `re`, `sys`, and `urllib.parse`, plus `scripts/site_html.py`.
    - Define `NEWS_DIR`, `NEWS_PAGE`, `HOME_PAGE`, `PREVIEW_COUNT = 2` in exactly one place, the four sentinel constants, `BASE_INDENT` of 16 spaces, `INTERNAL_HOST`, `REQUIRED_KEYS`, `OPTIONAL_KEYS`, and `MONTH_NAMES` as a hard coded 12 tuple rather than `calendar.month_name` or `strftime("%B")`.
    - Define the `Block` alias as `tuple[str, int, object]` covering paragraph, subheading, and list payloads, and the frozen `Post` dataclass with `slug`, `title`, `short_title`, `year`, `month`, `teaser`, `image`, `image_alt`, and `blocks`, plus the `display_month`, `order_key`, and `headline` properties. Store raw unescaped source text in every field.
    - Define `PostError(ValueError)` whose message always names the post first.
    - Implement `discover_post_files(directory)` to glob `*.md`, skip names beginning with `_`, sort by slug, validate each slug against `^[a-z0-9-]+$` raising on the first violation with the file name, and raise when no post file is found.
    - _Requirements: 1.1, 1.2, 1.7, 4.5, 4.7, 5.7, 7.6, 7.9, 10.4_

  - [ ] 2.2 Implement front matter splitting, validation, and loading
    - Implement `split_front_matter(text, slug)` requiring a first line of exactly `---` after trailing whitespace is stripped and a later line of exactly `---`, returning the raw key map, the body lines, and the body's first line number.
    - Implement `parse_front_matter(raw, slug)` splitting each line on the first colon only so a colon inside a title survives, matching keys case sensitively against `REQUIRED_KEYS + OPTIONAL_KEYS`, rejecting an unrecognized key and a duplicate key, stripping values, rejecting an empty required value, validating `date` against `^\d{4}-(0[1-9]|1[0-2])$`, and rejecting `image` supplied without a non-empty `image_alt`.
    - Implement `build_post(slug, text)` and `load_posts(directory)`, reading files as UTF-8 and validating in slug order so the first failure reported is deterministic.
    - Match the message shapes in the design's failure catalog, naming the slug and the specific offending key, value, or field.
    - _Requirements: 1.4, 1.5, 2.6, 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ]* 2.3 Property test for post loading in `tests/test_news_frontmatter.py`
    - **Property 1: Post file round trip**
    - *For any* set of valid posts serialized into a data directory, loading that directory returns exactly one `Post` per file, with each `Post` field equal to the value written for it and the slug equal to the file stem, and with no file becoming two posts and no post being dropped.
    - **Validates: Requirements 1.2, 1.4, 1.5**

  - [ ]* 2.4 Property test for validation rejection in `tests/test_news_frontmatter.py`
    - **Property 14: Validation rejection identifies the post and the fault**
    - *For any* valid post mutated by exactly one of the defined faults, namely removing a required front matter key, adding an unrecognized key, duplicating a key, emptying a required value to whitespace, corrupting the `date` value, removing a front matter delimiter, supplying an `image` without a non-empty `image_alt`, or using a file name outside `[a-z0-9-]`, the run raises an error whose message names the post's slug, or the file name in the slug case, together with the specific offending key, value, or field.
    - **Validates: Requirements 1.7, 2.6, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6**

- [ ] 3. Implement the body parser and the source level rejections
  - [ ] 3.1 Implement `parse_body` block splitting
    - Split the body on blank lines. Convert a block whose lines all begin with `- ` into one list block whose items preserve source order, a single line block beginning with `## ` into a subheading block, and anything else into a paragraph block whose lines are joined by a single space.
    - Reject a multi line `## ` block and a block that mixes `- ` lines with non `- ` lines.
    - Carry the one based source line number on every block, since error reporting needs it and rendering does not.
    - _Requirements: 2.1, 2.2, 2.3, 3.7_

  - [ ] 3.2 Implement the dash rule and the unsupported construct checks
    - Reject an em dash (U+2014) or an en dash (U+2013) anywhere in presented text, front matter values included, with a message that names the slug, names which character was found, quotes the offending source line, and states that the contributor replaces it with a comma, a colon, or the word `to` for a numeric range.
    - Reject, with the slug and the one based line number, `# ` and `### ` or deeper headings, ordered list markers such as `1. `, backticks, body image syntax `![alt](src)`, block quote markers `> `, a leading table pipe, a raw HTML tag detected as `<` followed by a letter or `/`, an unmatched `**` or `*`, and an unmatched `[`. Allow stray `(` and `)`, which ordinary prose uses.
    - Include the accepted syntax summary in the unsupported construct message.
    - _Requirements: 7.7, 7.8_

  - [ ]* 3.3 Property test for construct line numbers in `tests/test_news_body.py`
    - **Property 16: Unsupported construct line number**
    - *For any* valid body and *for any* line index at which an unsupported Markdown construct is inserted, the run fails with an error naming the slug and the one based line number of the inserted line.
    - **Validates: Requirements 7.8**

  - [ ]* 3.4 Property test for the dash rule message in `tests/test_news_body.py`
    - **Property 15: Dash rule error content**
    - *For any* post and *for any* position in any of its presented text values at which an em dash or an en dash is inserted, the run fails with an error that names the slug, names which of the two characters was found, quotes the source line containing it, and states that the contributor replaces it with a comma, a colon, or the word `to` for a numeric range.
    - **Validates: Requirements 7.7**

- [ ] 4. Checkpoint - parser and validation
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Implement inline rendering and link classification
  - [ ] 5.1 Implement `render_inline` and `_is_external`
    - Escape first with `escape_text(raw, quote=True)`, then substitute `[label](target)`, then `**text**`, then `*text*`, so the only raw tags in the output are the ones the renderer writes and an `&` in a link target is already `&amp;` when the anchor is assembled.
    - Implement `_is_external` using `urllib.parse.urlsplit`: an external link is an absolute `http` or `https` URL whose host is neither `geospatialcognitionlab.com` nor one of its subdomains. Everything else, including `mailto:`, relative, and fragment targets, is internal.
    - Emit external anchors with `target="_blank"`, `rel="noopener noreferrer"`, and an `aria-label` from `new_tab_aria_label`, in the fixed attribute order `href`, `target`, `rel`, `aria-label`. Emit every other anchor with neither `target` nor `rel`.
    - _Requirements: 2.4, 2.7, 2.8, 2.9, 2.10, 2.11_

  - [ ]* 5.2 Property test for escaping in `tests/test_news_escaping.py`
    - **Property 3: Escape then markup safety**
    - *For any* post text, including text containing `&`, `<`, `>`, `"`, raw HTML tags, and preexisting entity strings, the set of HTML tag names appearing in either rendered block is a subset of the renderer's own tag vocabulary, and every one of those characters taken from the post appears in the output only in escaped form and never as active markup.
    - **Validates: Requirements 2.7, 2.8, 2.11**

  - [ ]* 5.3 Property test for link attributes in `tests/test_news_links.py`
    - **Property 4: Link attribute classification**
    - *For any* link target, the rendered anchor carries `target="_blank"`, `rel="noopener noreferrer"`, and an `aria-label` equal to the link label followed by `, opens in a new tab` if and only if the target is an absolute `http` or `https` URL whose host is neither `geospatialcognitionlab.com` nor one of its subdomains; every other target, including `mailto:`, relative, and self host targets, yields an anchor carrying neither a `target` nor a `rel` attribute.
    - **Validates: Requirements 2.9, 2.10**

- [ ] 6. Implement deterministic ordering
  - [ ] 6.1 Implement `order_posts`
    - Sort with a single reverse sort on `(year, month, slug)` so Post_Month runs descending with slug descending as the tiebreak, and expose the result as the one sequence both renderers consume.
    - Derive nothing from file system enumeration order.
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ]* 6.2 Property test for ordering in `tests/test_news_order.py`
    - **Property 13: Ordering**
    - *For any* set of posts, the ordered sequence is non increasing on the key `(year, month, slug)`, so posts run from most recent Post_Month to least recent with ties broken by descending slug, and the previewed posts are a prefix of that same sequence.
    - **Validates: Requirements 6.1, 6.2, 6.3**

- [ ] 7. Implement the two renderers
  - [ ] 7.1 Implement `render_news`
    - Emit per post an `article.news-article` at 16 spaces with its direct children at 20 spaces and `li` elements at 24 spaces, separating articles by one blank line.
    - Emit `span.news-date` holding the Display_Month as the first child, then `h2` holding the title, then, only when `image` is set, one `img.news-image` with the fixed attribute order `src`, `alt`, `class` before every body element, then the body blocks in source order as `p`, `h3`, and `ul` with `li`.
    - Return `""` for an empty input.
    - _Requirements: 2.5, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [ ]* 7.2 Property test for news page structure in `tests/test_news_render.py`
    - **Property 5: News page structure**
    - *For any* set of posts, the rendered news block contains exactly one `article` with class `news-article` per post, and in each one the first child is a `span` with class `news-date` whose text is the post's Display_Month, followed by an `h2` holding the post title, followed, only when the post supplies an image, by exactly one `img` with class `news-image` positioned before every body element.
    - **Validates: Requirements 2.5, 3.1, 3.2, 3.3, 3.4**

  - [ ]* 7.3 Property test for indentation in `tests/test_news_render.py`
    - **Property 6: Indentation contract**
    - *For any* set of posts, every line of the rendered news block is indented to exactly one of the expected depths, with each `article` element at 16 spaces, each of its direct children at 20 spaces, and each `li` element at 24 spaces.
    - **Validates: Requirements 3.5**

  - [ ]* 7.4 Property test for the class vocabulary in `tests/test_news_render.py`
    - **Property 7: Class vocabulary is already styled**
    - *For any* set of posts, every value the renderers emit in a `class` attribute is drawn from the fixed set of class names already present in `styles.css`, so no rendered output can require a stylesheet change.
    - **Validates: Requirements 3.6**

  - [ ]* 7.5 Property test for parse and render order in `tests/test_news_body.py`
    - **Property 2: Body parse and render order fidelity**
    - *For any* sequence of body blocks serialized into a Post_Body, parsing that body returns the same sequence of block kinds and payloads in the same order, and rendering that post emits the corresponding elements in that same order, with each subheading yielding exactly one `h3`, each paragraph exactly one `p`, and each list exactly one `ul` whose `li` elements preserve item order.
    - **Validates: Requirements 2.1, 2.2, 2.3, 3.7**

  - [ ] 7.6 Implement `render_preview`
    - Slice the first `preview_count` posts from the ordered sequence, defaulting to `PREVIEW_COUNT`, so a directory holding fewer posts than the count needs no special branch.
    - Emit per previewed post an `article.news-item` holding `span.news-date` with the Display_Month, then `h3` with `short_title` when non-empty and `title` otherwise, then exactly one `p` holding the rendered teaser. Never emit the Post_Body here. Do not separate preview articles by a blank line.
    - _Requirements: 1.6, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [ ]* 7.7 Property test for preview structure in `tests/test_news_preview.py`
    - **Property 8: Preview structure and headline fallback**
    - *For any* set of posts, the rendered preview block contains one `article` with class `news-item` per previewed post, and in each one the first child is a `span` with class `news-date` holding the Display_Month, followed by an `h3` whose text is the post's `short_title` when that value is non-empty and the post's `title` otherwise, followed by exactly one `p` holding the rendered teaser and containing no text drawn from the Post_Body.
    - **Validates: Requirements 1.6, 4.1, 4.2, 4.3, 4.4**

  - [ ]* 7.8 Property test for preview selection in `tests/test_news_preview.py`
    - **Property 9: Preview selection**
    - *For any* set of posts and *for any* preview count, the previewed posts are exactly the first `min(preview_count, number of posts)` posts of the ordered sequence, in that order.
    - **Validates: Requirements 4.5, 4.6, 4.7**

  - [ ]* 7.9 Property test for determinism in `tests/test_news_order.py`
    - **Property 12: Determinism under enumeration order**
    - *For any* set of posts and *for any* permutation of that set, the rendered news block and the rendered preview block are byte identical to those produced from any other permutation, and no output depends on the wall clock or the process locale.
    - **Validates: Requirements 5.7, 6.4**

- [ ] 8. Checkpoint - renderers
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Implement `main()`, the CLI, and the all or nothing write
  - [ ] 9.1 Implement `main(argv=None)` with atomic writes
    - Order the steps so nothing is written before every check has passed: load posts, order them, render both blocks, read both HTML files, inject both in memory, compute which targets differ, then write only the differing targets, each through a temp file in the same directory moved into place with `os.replace`.
    - Catch `PostError`, `SentinelError`, `OSError`, and `UnicodeDecodeError`, print one line to stderr, and return `1`. Return `0` on success whether or not anything was written.
    - When the second write fails, print an error naming both the file that was already updated and the file that was not, so the partial state is visible rather than silent.
    - Add the CLI surface `--news-dir`, `--news-file`, `--home-file`, `--preview-count`, and `--check`, where `--check` renders and compares without writing and exits non-zero when the pages are out of date.
    - _Requirements: 1.3, 1.8, 5.4, 7.10, 7.11, 7.12_

  - [ ]* 9.2 Property test for fail closed behavior in `tests/test_news_pipeline.py`
    - **Property 17: Fail closed and all or nothing write**
    - *For any* set of post files, if the run exits non zero then both the News_Page and the Home_Page are byte identical to their contents before the run, and if the run exits zero then both files reflect the same set of posts, so a run never updates one target without the other.
    - **Validates: Requirements 7.10, 7.11, 7.12**

  - [ ]* 9.3 Property test for sentinel failure detection in `tests/test_news_inject.py`
    - **Property 11: Sentinel failure detection**
    - *For any* host document from which a required marker has been removed, or in which the end marker precedes the start marker, injection raises an error naming the offending marker and the file, and a full run in that state exits non zero having left both target files byte identical.
    - **Validates: Requirements 5.5, 5.6**

  - [ ]* 9.4 Unit and example tests in `tests/test_news_pipeline.py`
    - A run against an empty data directory exits non-zero with both pages unchanged.
    - A run against the three migrated posts updates both pages, and an immediate second run writes nothing, producing a zero byte repository difference.
    - A simulated `OSError` on the second target write produces a non-zero exit and an error naming both the file that was written and the one that was not.
    - An import allowlist check asserts `generate_news.py` pulls in nothing outside the standard library, which is what keeps the no network and no credential claim true over time.
    - All 12 month numbers map to the expected Display_Month strings with no locale dependency.
    - Use `tmp_path` copies of the two HTML pages so no test can modify the real `news.html` or `index.html`.
    - _Requirements: 1.8, 5.4, 5.7, 7.9, 7.11_

- [ ] 10. Migrate the three existing posts and insert the sentinels
  - [ ] 10.1 Capture the pre-migration news regions as test fixtures
    - Copy the current `.news-list` contents of `news.html` and the current `.news-preview` contents of `index.html` into fixture files under `tests/fixtures/`, byte for byte.
    - This must happen before task 10.4 edits either page, because the migration fidelity test compares against these snapshots and they cannot be recovered once the hand written markup is deleted.
    - _Requirements: 8.2, 8.3, 8.4_

  - [ ] 10.2 Create the three migrated post files
    - `content/news/2026-08-phd-student-opportunity.md`, carrying the recruitment article's wording verbatim, with `short_title: Recruiting a PhD Student`, a `title` holding the literal `&`, 4 `## ` subheadings, 7 paragraph blocks, one 5 item `- ` list, the internal lab link, the external FEMP link, the `mailto:` link, and a closing paragraph that is entirely `**...**`.
    - `content/news/2026-02-a-lab-is-born.md` with `short_title: A Lab is Born` and its single paragraph.
    - `content/news/2025-07-mcwhorter-joins-osu.md` with no `short_title`, exercising the `title` fallback, and a `teaser` that is required but unused at the current preview count.
    - Verify by running the generator that the ordered result is 2026-08, then 2026-02, then 2025-07.
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 1.4, 1.5, 1.6_

  - [ ] 10.3 Create `content/news/_template.md`
    - Provide a copyable post file carrying every accepted front matter key with the optional ones commented out in prose form, plus one example of each accepted body construct.
    - The leading underscore is what keeps it out of discovery, matching the `discover_post_files` skip rule, so the template is never rendered as a post.
    - _Requirements: 10.4_

  - [ ] 10.4 Perform the one time manual sentinel edit
    - In `news.html`, replace the hand written article markup inside `.news-list` with `<!-- NEWS:START -->` and `<!-- NEWS:END -->` at 16 space indent.
    - In `index.html`, replace the hand written preview markup inside `.news-preview` with `<!-- NEWS_PREVIEW:START -->` and `<!-- NEWS_PREVIEW:END -->` at 16 space indent.
    - Leave the surrounding hand maintained structure untouched: the `.news-list` and `.news-preview` wrappers, the `Recent News` heading, and the `View All News` button.
    - Run `python scripts/generate_news.py` immediately so both pages carry generated content in the same commit and neither page is ever published empty.
    - _Requirements: 5.1, 5.2, 8.5_

  - [ ]* 10.5 Migration fidelity test in `tests/test_news_migration.py`
    - Render the three migrated posts and compare against the task 10.1 fixtures per article: whitespace normalized text content, heading levels and their order, the list items in original order, and the single `strong` wrapping the whole closing paragraph.
    - Assert the recruitment article's element census exactly: 1 `h2`, 7 `p`, 4 `h3`, 1 `ul`, 5 `li`, 3 `a`, 1 `strong`.
    - Assert every link target and each anchor's attribute set: no `target` and no `rel` on the internal lab link and on the `mailto:` link, and `target="_blank" rel="noopener noreferrer"` on the FEMP link.
    - Assert the one intentional difference positively rather than tolerating it: the FEMP anchor carries `aria-label="femp.okstate.edu, opens in a new tab"`, so a later change to the escaping or classification logic fails this test.
    - Compare the two rendered `.news-item` blocks against the captured `index.html` block for headline text, Display_Month, and teaser text, including the `news.html` link inside the August 2026 teaser.
    - Assert that `news.html` contains no `news-article` string outside its sentinel region and `index.html` contains no `news-item` string outside its sentinel region.
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ]* 10.6 Template validity test in `tests/test_news_docs.py`
    - Assert `content/news/_template.md` parses cleanly as a post and that `discover_post_files` excludes it.
    - _Requirements: 10.4_

- [ ] 11. Checkpoint - migration
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Rewrite the contributor documentation
  - [ ] 12.1 Rewrite the news section of `HOW-TO-UPDATE.txt`
    - Document every accepted front matter key, which are required and which optional, and the `YYYY-MM` date format.
    - Document the body syntax table for paragraphs, `## ` subheadings, `- ` list items, `[label](target)`, `**strong**`, and `*em*`, plus the explicit list of unsupported constructs and the fact that each one is a hard error with a line number rather than a silent misrendering.
    - Document the contributor procedure end to end: create a branch, copy `content/news/_template.md` to `content/news/<slug>.md`, edit, commit, open a pull request against `main`, wait for the check to commit the regenerated pages, request review, and let the reviewer merge.
    - Document the local command `python scripts/generate_news.py` and the `--check` variant.
    - Delete the current instruction to mirror the two most recent posts into `index.html` by hand, replacing it with a note that the home page preview is generated.
    - Add the dash warning: Microsoft Word and Google Docs silently convert a typed hyphen into an em dash, which the generator rejects. Include how to disable it (Word: File, Options, Proofing, AutoCorrect Options, AutoFormat As You Type, clear "Hyphens with dash"; Google Docs: Tools, Preferences, clear "Automatic substitution"), how to fix a draft that already contains one by replacing it with a comma, a colon, or the word `to` for a numeric range, and the advice to paste as plain text.
    - State that a contributor needs repository collaborator access and no credential belonging to the principal investigator.
    - _Requirements: 10.1, 10.2, 10.3, 10.5, 10.6, 10.7_

  - [ ]* 12.2 Documentation drift test in `tests/test_news_docs.py`
    - Assert the documented front matter key list matches `REQUIRED_KEYS + OPTIONAL_KEYS`, that the documented local command string appears in the file, and that the removed manual mirror instruction is absent.
    - _Requirements: 10.1, 10.3, 10.6_

- [ ] 13. Wire the review gated workflow
  - [ ] 13.1 Create `.github/workflows/news.yml`
    - Trigger on `pull_request` with `branches: [main]` and a `paths` filter of `content/news/**`, plus `workflow_dispatch`.
    - Use `pull_request` rather than `pull_request_target`: `pull_request_target` would hand a write token to code from the pull request head, which is the standard path to a compromised repository. The accepted consequence is that fork pull requests get a read only token and cannot be pushed to.
    - Set a `concurrency` group of `news-${{ github.event.pull_request.number || github.ref }}` with `cancel-in-progress: false` so overlapping runs queue rather than cancel.
    - Declare `permissions` of `contents: write` and `pull-requests: write`, referencing no secret other than the built in `GITHUB_TOKEN`.
    - Steps: checkout the pull request head ref and repository, set up Python 3.12 with no `pip install` since the generator is standard library only, run `python scripts/generate_news.py` so a non-zero exit fails the check with the generator error in the log and no commit, detect changes with `git diff --quiet -- news.html index.html`, and on a change from an in repository branch commit only `news.html` and `index.html` as `github-actions[bot]` and push to the pull request head branch.
    - Detect a fork as `github.event.pull_request.head.repo.full_name != github.repository`, and on that path report the check result without pushing while logging that the contributor must run the generator locally and commit the two pages.
    - On `workflow_dispatch`, regenerate on the dispatched ref and commit back to it, except when the dispatched ref is the default branch, where the job reports the diff in the log and fails rather than pushing to `main`, preserving the review gate.
    - Deploy nothing: merging to `main` triggers the existing Pages workflow, which publishes the regenerated pages.
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10_

  - [ ]* 13.2 Verify the workflow by live exercise
    - Run one manual dispatch dry run on a scratch branch and confirm the job completes and commits back to that branch.
    - Open one real pull request that adds a post and confirm the bot commit appears carrying the regenerated `news.html` and `index.html`.
    - Rerun on the unchanged branch and confirm the run completes with no additional commit.
    - Push a deliberately malformed post and confirm the check fails with the generator error visible in the log and no commit.
    - Merge and confirm the existing Pages deployment publishes with no further manual step.
    - Verify the fork path by inspecting the fork condition and the logged instruction, since contributors work on in repository branches by design.
    - _Requirements: 9.2, 9.3, 9.5, 9.6, 9.7, 9.10_

- [ ] 14. Final checkpoint - full pipeline
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 15. Refactor `scripts/generate_publications.py` onto `site_html` (deferrable)
  - [ ] 15.1 Replace the duplicated primitives with imports
    - Replace the bodies of `SentinelError`, `inject`, `_escape_text`, `_escape_attr`, and `_new_tab_aria_label` in `scripts/generate_publications.py` with imports from `scripts/site_html.py`, keeping the existing module level names, including `PUBLICATIONS_START` and `PUBLICATIONS_END`, as thin aliases or wrappers so the existing tests keep importing the same symbols from the same place.
    - This step is guarded by the existing 67 tests, whose Hypothesis property tests already pin `inject()` idempotence and structure preservation. If the extraction changes anything observable, those tests fail.
    - This step touches deployed code whose failure mode is a silently wrong `publications.html` on the next monthly sync. It may be skipped or deferred indefinitely: the news pipeline works with `site_html.py` in place and this file untouched. Do not perform it while the suite is red for any reason.
    - _Requirements: 5.1, 5.2, 5.5, 5.6_

  - [ ]* 15.2 Confirm the existing suite is unchanged
    - Run the full suite and confirm all 67 pre-existing tests still pass alongside the new news tests, with no change to any publications test file.
    - _Requirements: 5.3_

## Notes

- Tasks marked with `*` are optional test and verification sub-tasks and can be skipped for a faster first release. Core implementation tasks are never optional.
- Each of the 17 correctness properties from the design is implemented by exactly one property based test, each running a minimum of 100 iterations and carrying a comment tag naming the property, matching the convention in the existing suite.
- The generator is standard library only, so CI needs no `pip install` step and a contributor can run it with a bare Python 3.12. Task 9.4 includes an import allowlist test that keeps that true over time, which is also what keeps the no network and no credential claim honest.
- `MONTH_NAMES` is a hard coded tuple rather than `calendar.month_name` or `strftime("%B")`, both of which read the `LC_TIME` locale. A locale dependent month name would make output depend on the machine, which Requirement 5.7 forbids.
- Practical caveat carried over from earlier work on this repository: `styles.css` opens with a universal `* { margin: 0; padding: 0; box-sizing: border-box; }` reset. If generated markup ever looks cramped, the cause is the reset stripping browser defaults, not the generator. The fix belongs in `styles.css`, as it did for `.news-article ul` and `.news-article li`.
- The migration ships one intentional difference from the live page: the FEMP anchor gains `aria-label="femp.okstate.edu, opens in a new tab"`. Task 10.5 asserts it positively so nobody learns to ignore a failing snapshot.
- Task ordering is load bearing in three places: `site_html.py` before `generate_news.py`, the fixture capture in 10.1 before the sentinel edit in 10.4, and the migrated posts in 10.2 before that same edit so neither page is ever published empty.
- The workflow YAML cannot be usefully property tested, since it is configuration plus external service behavior that does not vary with input. It is verified by inspection against the requirement clauses plus the single live exercise in task 13.2.
- File touching tests use `tmp_path` copies of the two HTML pages, so no test can modify the real `news.html` or `index.html`.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "10.1", "10.3"] },
    { "id": 1, "tasks": ["2.1", "1.3"] },
    { "id": 2, "tasks": ["2.2"] },
    { "id": 3, "tasks": ["3.1", "2.3"] },
    { "id": 4, "tasks": ["3.2", "2.4"] },
    { "id": 5, "tasks": ["5.1", "3.3"] },
    { "id": 6, "tasks": ["6.1", "3.4", "5.2", "5.3"] },
    { "id": 7, "tasks": ["7.1", "6.2"] },
    { "id": 8, "tasks": ["7.6", "7.2", "7.5"] },
    { "id": 9, "tasks": ["9.1", "7.3", "7.7", "7.9"] },
    { "id": 10, "tasks": ["10.2", "7.4", "7.8", "9.2", "9.3"] },
    { "id": 11, "tasks": ["10.4"] },
    { "id": 12, "tasks": ["9.4", "10.5", "10.6", "12.1"] },
    { "id": 13, "tasks": ["12.2", "13.1"] },
    { "id": 14, "tasks": ["13.2", "15.1"] },
    { "id": 15, "tasks": ["15.2"] }
  ]
}
```
