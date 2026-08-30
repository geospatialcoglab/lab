# Implementation Plan: Site Recruitment & Scholar Updates

## Overview

This plan implements two independent workstreams that can ship separately, plus a post-launch section recording the corrections and enhancements made after the first release:

- **Workstream A, hand-authored content (Requirements 1, 2):** add the PhD recruitment article to `news.html` and mirror a condensed entry into the `index.html` Recent News preview. These are static HTML edits with no runtime logic; verification is manual/visual plus optional HTML well-formedness checks.
- **Workstream B, automated publication sync (Requirements 3, 4, 5):** insert injection sentinels into `publications.html`, implement the Python `Generator_Script` (`scripts/generate_publications.py`), cover its pure transformation core and fetch layer with `pytest` (property-based tests for the design's Correctness Properties, with `scholarly` mocked), pin the `scholarly` dependency, and wire the scheduled GitHub Actions workflow. The generator uses a **curated-merge** strategy so the two hand-entered publications are preserved with their original wording: a small `scripts/curated_publications.json` is merged (dedupe, curated wins) with the Scholar-fetched records after the threshold guard, and the Scholar-fetched count still drives the below-threshold guard.
- **Post-launch work (Requirements 2, 3, 6):** section 10 records what shipped after the initial release: a citation correction, author emphasis in rendered author lists, new-tab publication links, the site-wide ampersand and outbound-link passes, presentation fixes in `styles.css`, and finalizing the funding statement.

Sequencing rules: the sentinel edit precedes the generator; the generator and its tests precede the workflow wiring. Workstream A has no dependency on Workstream B, so content can be committed and published independently.

## Tasks

- [x] 1. Author the PhD recruitment announcement on `news.html`
  - [x] 1.1 Insert the recruitment article as the topmost news item
    - Add a new `<article class="news-article">` as the first child of `.news-list`, above the existing "A Lab is Born" item, matching the sibling element structure (one `<span class="news-date">` + heading + content).
    - Set the `.news-date` to a full-month-name + four-digit-year value (e.g., "February 2026" or later) that is the most recent date on the page.
    - Use `<h2>` for the announcement title and `<h3>` subheadings for "About the Program & Lab", "Qualifications & Preferred Skills", "Funding", and "How to Apply".
    - Render the preferred-skills list as a `<ul>` of `<li>` items and state that a completed master's degree is required.
    - State the position is a funded, in-residence PhD in the FEMP program at OSU Stillwater with research through the Geospatial Cognition Lab; list Spring 2027 / Fall 2027 start terms; describe FEMP's multidisciplinary nature, the in-residence cohort, the remote MS/PhD network, and the live hybrid (in-person + Zoom) format.
    - State guaranteed funding for the first two years plus anticipated TA and externally funded support. The first draft wrapped the remaining unconfirmed specifics in a visually distinct bracketed placeholder; that placeholder was removed in task 10.7, so this content now stands as final text.
    - Provide the application email as a `mailto:Chelsie.McWhorter@okstate.edu` hyperlink, list the four required materials (CV, unofficial transcripts, one to two paragraph statement of research interests, preferred start semester), and state the rolling review with October 1, 2026 priority for a Spring 2027 start.
    - Render the lab site (`geospatialcognitionlab.com`) and FEMP site (`femp.okstate.edu`) as `<a>` hyperlinks resolving to those addresses.
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12_

  - [x]* 1.2 Validate `news.html` well-formedness and links
    - Run the edited page through an HTML validator to confirm no unclosed tags and that the `mailto:` and external links are well-formed.
    - _Requirements: 2.9, 2.12_

- [x] 2. Mirror the announcement in the homepage Recent News preview
  - [x] 2.1 Update `index.html` `.news-preview`
    - Add a condensed `<article class="news-item">` (`.news-date` + `<h3>` + one-sentence teaser `<p>`) for the PhD recruitment as the newest of the two shown items, dropping the current oldest ("Dr. McWhorter Joins OSU") so "A Lab is Born" remains second.
    - Keep the teaser to a single sentence with the full detail living in the `news.html` article; do not couple this edit to any automation.
    - _Requirements: 1.1, 1.3_

  - [x]* 2.2 Validate `index.html` well-formedness
    - Run the edited homepage through an HTML validator for well-formedness.
    - _Requirements: 1.3_

- [x] 3. Prepare `publications.html` for marker-based injection
  - [x] 3.1 Insert the publication sentinels
    - Add `<!-- PUBLICATIONS:START -->` and `<!-- PUBLICATIONS:END -->` HTML comments around the existing `.publications-list` inner content, leaving the `.publications-list` open/close tags and everything outside the sentinels byte-for-byte unchanged.
    - Keep the file fully hand-editable so manual edits between the sentinels remain valid.
    - _Requirements: 3.7, 5.4_

- [x] 4. Implement the Generator_Script pure core (`scripts/generate_publications.py`)
  - [x] 4.1 Define the `Publication` model and `normalize()`
    - Add the frozen `Publication` dataclass (`title`, `authors`, `venue`, `year`, `link`, `link_label`).
    - Implement `normalize(records) -> list[Publication]` with the defensive mapping: author reformatting ("A and B and C" to "A, B, & C"), year parsing with an explicit unparseable-year bucket, venue assembly from `journal` + `volume` + `pages` (journal wrapped in `<em>`), and the link fallback chain (real DOI, then `pub_url`, then Scholar entry URL) with the matching `link_label` ("DOI →" vs "Link →"); skip records lacking a title and never emit an empty link.
    - _Requirements: 3.3_

  - [x] 4.2 Implement `render_list()`
    - Group publications into `.pub-year` blocks in strictly descending year order with a stable title-ascending tiebreak within a year; emit `.publication`/`.pub-authors`/`.pub-title`/`.pub-venue`/`.pub-link` markup matching the existing pattern.
    - Make output a pure function of the normalized list (fixed formatting, stable ordering) so identical input yields identical bytes.
    - _Requirements: 3.3, 3.4, 3.5, 3.6_

  - [x] 4.3 Implement `inject()`
    - Locate `<!-- PUBLICATIONS:START -->` and `<!-- PUBLICATIONS:END -->` and replace only the text strictly between them, preserving all other bytes; abort with an error if either sentinel is missing.
    - _Requirements: 3.7_

  - [x] 4.4 Implement `check_threshold()`
    - Implement `check_threshold(pubs, min_threshold)` raising `BelowThresholdError` when `len(pubs) < min_threshold` (default 1, configurable), covering the zero-record case.
    - _Requirements: 3.10, 5.5_

  - [x] 4.5 Implement the fetch layer and CLI wiring
    - Implement `fetch_publications(author_id)` using `scholarly` (look up author id `Xu5F1CAAAAAJ`, `fill()`, retrieve bib fields) inside a retry loop of up to 3 attempts, a 30s per-request timeout and a 120s per-attempt timeout, raising `RetrievalError` when all attempts are exhausted.
    - Define `RetrievalError` and `BelowThresholdError`, wire `main()`/argument parsing (`--author-id`, `--html-file`, `--min-threshold`, `--max-retries`, `--request-timeout`, `--attempt-timeout`), and orchestrate fetch, normalize, threshold-guard (on the Scholar-fetched count), load_curated + merge, render, inject, write-only-if-different (merge runs after the threshold guard and before render), exiting non-zero on `RetrievalError`, `BelowThresholdError`, or missing sentinels / write errors and 0 otherwise.
    - _Requirements: 3.1, 3.2, 3.9, 3.10, 5.1, 5.2, 5.4, 5.5, 5.6, 5.7_

  - [x] 4.6 Add curated publications source and merge/dedupe
    - Create `scripts/curated_publications.json` containing the two existing hand-entered entries as `Publication`-shaped JSON records (`authors`, `title`, `venue` with `<em>` journal markup, `year`, `link`, `link_label`): the 2025 IJDRR paper (McWhorter, C., Hegarty, M., Baylis, K., & Montello, D. R.; "Mapping the response: A survey of municipal firefighter navigation training and practices in the United States."; _International Journal of Disaster Risk Reduction_, 123, 105446; DOI `https://doi.org/10.1016/j.ijdrr.2025.105446`) and the 2020 book chapter. The 2020 entry was initially entered with the wrong source and was corrected in task 10.1; the DOI `https://doi.org/10.1007/978-3-030-02438-3_159` was correct from the start.
    - Implement `load_curated()` to read this file into `Publication` records and `merge(curated, pubs)` to produce the deduplicated union keyed by normalized (case-insensitive, whitespace/punctuation-stripped) title plus DOI equality, with the curated entry winning on a match; the merge runs after the threshold guard and before render.
    - _Requirements: 3.3, 3.17, 5.4_

- [x] 5. Test the Generator_Script (`pytest`, `scholarly` mocked)
  - [x]* 5.1 Property test: rendering determinism / idempotent regeneration
    - **Property 1: Rendering determinism and idempotent regeneration** - assert `render_list` produces byte-identical output across repeated invocations for the same normalized input, and that regenerating over an unchanged fixture yields an identical file (zero diff, therefore zero commit).
    - **Validates: Requirements 3.5, 3.6**

  - [x]* 5.2 Property test: structure preservation under injection
    - **Property 2: Structure preservation under injection** - assert `inject` replaces only the region between the sentinels and leaves every byte outside that region unchanged, for arbitrary generated blocks and surrounding HTML.
    - **Validates: Requirements 3.7**

  - [x]* 5.3 Property test: deterministic ordering
    - **Property 4: Deterministic ordering** - assert rendered output groups publications by year in strictly descending order with a stable title-ascending tiebreak within each year.
    - **Validates: Requirements 3.4**

  - [x]* 5.4 Property test: total normalization and defined link output
    - **Property 5: Total normalization and defined link output** - assert `normalize` never crashes on records with missing or inconsistent fields and that every rendered publication has a non-empty `.pub-link` href from the DOI, `pub_url`, Scholar-entry-URL fallback chain.
    - **Validates: Requirements 3.3**

  - [x]* 5.5 Property test: threshold boundary
    - **Property 6: Threshold boundary** - assert a commit-eligible run occurs if and only if `n >= min-threshold`, testing `0`, `threshold - 1`, and `threshold`; below-threshold fails non-destructively.
    - **Validates: Requirements 5.5**

  - [x]* 5.6 Test: non-destructiveness under failure
    - **Property 3: Non-destructiveness under failure** - with `scholarly` mocked to raise (retrieval failure) and to return an empty/below-threshold set, assert the process exits non-zero and `publications.html` bytes are unchanged (no commit).
    - **Validates: Requirements 3.9, 3.10, 5.1, 5.2, 5.5**

  - [x]* 5.7 Test: fetch retry and empty-result handling (mocked)
    - Mock `scholarly` so each attempt raises and assert the retry loop makes up to 3 attempts before raising `RetrievalError`; mock a zero-record success and assert `BelowThresholdError`; use fixtures captured from a realistic `scholarly` response shape.
    - _Requirements: 3.2, 3.10, 5.5, 5.6_

  - [x]* 5.8 Property test: curated-entry preservation and deduplication
    - **Property 7: Curated-entry preservation and deduplication** - over generated Scholar result sets, assert every curated publication appears exactly once and any Scholar duplicate of a curated work (by normalized title or shared DOI) collapses to one entry with the curated wording; non-duplicate Scholar entries are all retained.
    - **Validates: Requirements 3.3, 3.17, 5.4**

- [x] 6. Checkpoint - generator core and tests
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Pin the sync dependency
  - [x] 7.1 Add `requirements.txt` pinning `scholarly`
    - Create a `requirements.txt` at the repo root pinning a specific `scholarly` version for reproducible installs in the workflow.
    - _Requirements: 3.1, 3.2_

- [x] 8. Wire up the Sync_Workflow
  - [x] 8.1 Create `.github/workflows/sync-publications.yml`
    - Configure triggers `schedule` with cron `0 0 1 * *` and `workflow_dispatch` (identical job for both), a `sync-publications` concurrency group with `cancel-in-progress: false`, and `contents: write` plus `pull-requests: write` permissions.
    - Add steps: checkout, setup Python, install `scholarly`, run `scripts/generate_publications.py`, then open or update a review pull request on the `auto/publications-sync` branch via `peter-evans/create-pull-request@v6` (scoped to `publications.html` with `add-paths`, `base: main`, `delete-branch: true`), so changes reach the default branch only when the maintainer merges; a non-zero script exit fails the job and no pull request is created or updated.
    - _Requirements: 3.1, 3.5, 3.6, 3.8, 3.9, 3.11, 3.12, 4.1, 4.2, 4.3, 4.4, 4.5, 5.3_

- [x] 9. Final checkpoint - sync pipeline
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Post-launch corrections and enhancements
  - [x] 10.1 Correct the 2020 publication citation in `scripts/curated_publications.json`
    - Replace the incorrect attribution (International Encyclopedia of Human Geography, Elsevier, ed. Kobayashi, pp. 291-300) with the correct source: Acheson, G., & McWhorter, C. "Reading the American Cemetery." In S. D. Brunn & R. Kehrein (Eds.), _Handbook of the Changing World Language Map_ (pp. 2847-2870). Springer International Publishing. 2020. Acheson is first author, and the DOI `https://doi.org/10.1007/978-3-030-02438-3_159` was already correct.
    - Write the ampersand in the `venue` string as `&amp;`, because the generator emits `venue` verbatim as trusted HTML while escaping `authors` and `title`.
    - _Requirements: 3.3, 5.4, 6.7_

  - [x] 10.2 Emphasize the PI surname in rendered author lists
    - Add the module constant `HIGHLIGHT_AUTHOR = "McWhorter"` and the `--highlight-author` CLI flag (an empty string disables bolding).
    - Add the pure helper `_highlight_author(escaped_authors, surname)` wrapping whole-word, case-sensitive occurrences of the surname in `<strong>`, and call it from `_render_publication()` **after** `_escape_text()`: the `authors` field is HTML-escaped, so the bolding cannot be stored in `curated_publications.json` (a literal `<strong>` there would render as visible text), and applying it post-escape is what keeps it injection-safe because the only raw tags in the output are the ones the renderer adds. Publications that a future Scholar sync adds inherit the emphasis with no manual editing.
    - _Requirements: 3.13, 3.14_

  - [x] 10.3 Open publication links in a new tab
    - Emit the `.pub-link` anchor attributes in the fixed order href, class, `target="_blank"`, `rel="noopener noreferrer"`, aria-label, so the output stays byte-stable. `rel="noopener noreferrer"` is a security requirement: it prevents tab-nabbing and referrer leakage.
    - Add the pure helper `_new_tab_aria_label(link_label)` deriving the accessible name with the decorative trailing arrow (U+2192) stripped, so a screen reader announces "DOI, opens in a new tab" rather than reading the glyph; degenerate labels yield "opens in a new tab" alone.
    - _Requirements: 3.15, 3.16_

  - [x] 10.4 Escape bare ampersands site-wide
    - Replace all 46 bare ampersands across the 10 html pages with `&amp;` entities so the markup is valid, covering Google Fonts URLs, Scholar URLs, aria-label values, and visible text.
    - Leave existing character entities alone; do not double-escape.
    - _Requirements: 6.1, 6.2_

  - [x] 10.5 Open outbound links in a new tab site-wide
    - Add `target="_blank"` and `rel="noopener noreferrer"` to every hyperlink whose destination is outside `geospatialcognitionlab.com`.
    - Leave internal and relative links, `mailto:` links, and self-referential links to the lab domain in the same tab.
    - Append `, opens in a new tab` to icon links that already carried an aria-label.
    - _Requirements: 6.3, 6.4, 6.5_

  - [x] 10.6 Presentation fixes in `styles.css`
    - Give `.news-article h3` a 2rem top margin so the subheadings in the long recruitment article have breathing room.
    - Give `.news-article ul` and `.news-article li` explicit padding and type styling, restoring the list indent that the global `* { margin: 0; padding: 0 }` reset had stripped.
    - Pin link colors to the palette instead of the default browser blue: `--accent` on the light card backgrounds, and cream (`--bg-main`) with an underline in the dark olive homepage section, where `--accent` fails contrast.
    - _Requirements: 1.2, 2.5_

  - [x] 10.7 Finalize the recruitment funding statement
    - Remove the bracketed to-be-confirmed placeholder from the Funding section of the recruitment article so the two-year funding guarantee, plus the anticipated TA and externally funded support, stands as final text with no placeholder marker.
    - _Requirements: 2.6, 2.7_

  - [x] 10.8 Apply the no-dash content style rule
    - Confirm the presented text of every page contains no em dash (U+2014) and no en dash (U+2013) characters; the site currently contains zero of either.
    - _Requirements: 6.6_

  - [x] 10.9 Property test: author emphasis applied post-escape
    - **Property 8: Author emphasis is applied after escaping and is never injectable** - in `tests/test_highlight.py`, assert the rendered `.pub-authors` content equals `_highlight_author(_escape_text(authors), surname)`: source markup characters appear only as entities, the `<strong>` pairs are the only raw tags, whole-word case-sensitive matches are wrapped while substring matches are not, an empty surname disables bolding, curated entries render with the emphasis, and rendering stays deterministic.
    - **Validates: Requirements 3.13, 3.14**

  - [x] 10.10 Property test: link attributes always present and deterministic
    - **Property 9: Link attributes are always present and deterministic** - in `tests/test_link_attributes.py`, assert every `.pub-link` anchor carries href, class, `target="_blank"`, `rel="noopener noreferrer"`, and aria-label in that fixed order, that the visible label is unchanged, that the aria-label derivation handles arrow, arrow-free, and degenerate labels, that the aria-label and href are attribute-escaped, and that repeated renders are byte-identical.
    - **Validates: Requirements 3.15, 3.16**

## Notes

- Tasks marked with `*` are optional (content validation and the property/unit test sub-tasks) and can be skipped for a faster MVP; core implementation tasks are never optional.
- Workstream A (tasks 1 and 2) and Workstream B (tasks 3 through 9) are independent, so content can ship without the sync. Section 10 records post-launch work that touched both.
- Property-based test sub-tasks map directly to the design's Correctness Properties (Properties 1 through 9) and each references the requirement clause it validates.
- The test suite currently stands at 67 passing tests. Modules: `test_normalize.py`, `test_rendering.py`, `test_injection.py`, `test_threshold.py`, `test_merge.py`, `test_pipeline_failure.py`, plus the post-launch `test_highlight.py` (author emphasis, including that highlighting happens after escaping so it is not injectable) and `test_link_attributes.py` (new-tab attributes, aria-label derivation, href escaping, determinism).
- The two hand-entered publications are preserved via a curated-merge (`scripts/curated_publications.json` + `merge`/dedupe, curated wins); the merge runs after the threshold guard, and the Scholar-fetched count, not the merged count, still drives the below-threshold guard.
- Escaping asymmetry to remember when editing curated data: `authors` and `title` are HTML-escaped at render time, while `venue` is emitted verbatim as trusted HTML, so any ampersand in curated venue text must be written `&amp;` in the JSON.
- The static content edits have no automated tests; verification is manual/visual with optional HTML well-formedness and entity checks. The workflow YAML is validated by inspection and a manual `workflow_dispatch` dry run rather than unit tests.
- `scholarly` is always mocked in tests; no live Google Scholar calls are made in CI.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "3.1", "4.1", "7.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "4.2"] },
    { "id": 2, "tasks": ["2.2", "4.3"] },
    { "id": 3, "tasks": ["4.4"] },
    { "id": 4, "tasks": ["4.6"] },
    { "id": 5, "tasks": ["4.5"] },
    { "id": 6, "tasks": ["5.1", "5.2", "5.4", "5.5", "5.6", "5.8"] },
    { "id": 7, "tasks": ["5.3", "5.7"] },
    { "id": 8, "tasks": ["8.1"] },
    { "id": 9, "tasks": ["10.1", "10.2", "10.3", "10.4", "10.5", "10.6", "10.7", "10.8"] },
    { "id": 10, "tasks": ["10.9", "10.10"] }
  ]
}
```
