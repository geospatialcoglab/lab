# Implementation Plan: Site Recruitment & Scholar Updates

## Overview

This plan implements two independent workstreams that can ship separately:

- **Workstream A — Hand-authored content (Requirements 1, 2):** add the PhD recruitment article to `news.html` and mirror a condensed entry into the `index.html` Recent News preview. These are static HTML edits with no runtime logic; verification is manual/visual plus optional HTML well-formedness checks.
- **Workstream B — Automated publication sync (Requirements 3, 4, 5):** insert injection sentinels into `publications.html`, implement the Python `Generator_Script` (`scripts/generate_publications.py`), cover its pure transformation core and fetch layer with `pytest` (property-based tests for the design's Correctness Properties, with `scholarly` mocked), pin the `scholarly` dependency, and wire the scheduled GitHub Actions workflow. The generator uses a **curated-merge** strategy so the two hand-entered publications are preserved with their original wording: a small `scripts/curated_publications.json` is merged (dedupe, curated wins) with the Scholar-fetched records after the threshold guard, and the Scholar-fetched count still drives the below-threshold guard.

Sequencing rules: the sentinel edit precedes the generator; the generator and its tests precede the workflow wiring. Workstream A has no dependency on Workstream B, so content can be committed and published independently.

## Tasks

- [x] 1. Author the PhD recruitment announcement on `news.html`
  - [x] 1.1 Insert the recruitment article as the topmost news item
    - Add a new `<article class="news-article">` as the first child of `.news-list`, above the existing "A Lab is Born" item, matching the sibling element structure (one `<span class="news-date">` + heading + content).
    - Set the `.news-date` to a full-month-name + four-digit-year value (e.g., "February 2026" or later) that is the most recent date on the page.
    - Use `<h2>` for the announcement title and `<h3>` subheadings for "About the Program & Lab", "Qualifications & Preferred Skills", "Funding", and "How to Apply".
    - Render the preferred-skills list as a `<ul>` of `<li>` items and state that a completed master's degree is required.
    - State the position is a funded, in-residence PhD in the FEMP program at OSU Stillwater with research through the Geospatial Cognition Lab; list Spring 2027 / Fall 2027 start terms; describe FEMP's multidisciplinary nature, the in-residence cohort, the remote MS/PhD network, and the live hybrid (in-person + Zoom) format.
    - State guaranteed funding for the first two years plus anticipated TA and externally funded support; wrap any unconfirmed funding specifics in a visually distinct bracketed placeholder (e.g., `<em>[… to be confirmed]</em>`).
    - Provide the application email as a `mailto:Chelsie.McWhorter@okstate.edu` hyperlink, list the four required materials (CV, unofficial transcripts, 1–2 paragraph statement of research interests, preferred start semester), and state the rolling review with October 1, 2026 priority for a Spring 2027 start.
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
    - Implement `normalize(records) -> list[Publication]` with the defensive mapping: author reformatting ("A and B and C" → "A, B, & C"), year parsing with an explicit unparseable-year bucket, venue assembly from `journal` + `volume` + `pages` (journal wrapped in `<em>`), and the link fallback chain (real DOI → `pub_url` → Scholar entry URL) with the matching `link_label` ("DOI →" vs "Link →"); skip records lacking a title and never emit an empty link.
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
    - Define `RetrievalError` and `BelowThresholdError`, wire `main()`/argument parsing (`--author-id`, `--html-file`, `--min-threshold`, `--max-retries`, `--request-timeout`, `--attempt-timeout`), and orchestrate fetch → normalize → threshold-guard (on the Scholar-fetched count) → load_curated + merge → render → inject → write-only-if-different (merge runs after the threshold guard and before render), exiting non-zero on `RetrievalError`, `BelowThresholdError`, or missing sentinels / write errors and 0 otherwise.
    - _Requirements: 3.1, 3.2, 3.9, 3.10, 5.1, 5.2, 5.4, 5.5, 5.6, 5.7_

  - [x] 4.6 Add curated publications source and merge/dedupe
    - Create `scripts/curated_publications.json` containing the two existing hand-entered entries as `Publication`-shaped JSON records (`authors`, `title`, `venue` with `<em>` journal markup, `year`, `link`, `link_label`): the 2025 IJDRR paper — McWhorter, C., Hegarty, M., Baylis, K., & Montello, D. R.; "Mapping the response: A survey of municipal firefighter navigation training and practices in the United States."; _International Journal of Disaster Risk Reduction_, 123, 105446; DOI `https://doi.org/10.1016/j.ijdrr.2025.105446` — and the 2020 encyclopedia chapter — McWhorter, C., & Acheson, G.; "Reading the American Cemetery."; In A. Kobayashi (Ed.), _International Encyclopedia of Human Geography_ (2nd ed., pp. 291-300). Elsevier; DOI `https://doi.org/10.1007/978-3-030-02438-3_159`.
    - Implement `load_curated()` to read this file into `Publication` records and `merge(curated, pubs)` to produce the deduplicated union keyed by normalized (case-insensitive, whitespace/punctuation-stripped) title plus DOI equality, with the curated entry winning on a match; the merge runs after the threshold guard and before render.
    - _Requirements: 3.3, 5.4_

- [x] 5. Test the Generator_Script (`pytest`, `scholarly` mocked)
  - [x]* 5.1 Property test: rendering determinism / idempotent regeneration
    - **Property 1: Rendering determinism and idempotent regeneration** — assert `render_list` produces byte-identical output across repeated invocations for the same normalized input, and that regenerating over an unchanged fixture yields an identical file (zero diff → zero commit).
    - **Validates: Requirements 3.5, 3.6**

  - [x]* 5.2 Property test: structure preservation under injection
    - **Property 2: Structure preservation under injection** — assert `inject` replaces only the region between the sentinels and leaves every byte outside that region unchanged, for arbitrary generated blocks and surrounding HTML.
    - **Validates: Requirements 3.7**

  - [x]* 5.3 Property test: deterministic ordering
    - **Property 4: Deterministic ordering** — assert rendered output groups publications by year in strictly descending order with a stable title-ascending tiebreak within each year.
    - **Validates: Requirements 3.4**

  - [x]* 5.4 Property test: total normalization and defined link output
    - **Property 5: Total normalization and defined link output** — assert `normalize` never crashes on records with missing or inconsistent fields and that every rendered publication has a non-empty `.pub-link` href from the DOI → `pub_url` → Scholar-entry-URL fallback chain.
    - **Validates: Requirements 3.3**

  - [x]* 5.5 Property test: threshold boundary
    - **Property 6: Threshold boundary** — assert a commit-eligible run occurs iff `n >= min-threshold`, testing `0`, `threshold - 1`, and `threshold`; below-threshold fails non-destructively.
    - **Validates: Requirements 5.5**

  - [x]* 5.6 Test: non-destructiveness under failure
    - **Property 3: Non-destructiveness under failure** — with `scholarly` mocked to raise (retrieval failure) and to return an empty/below-threshold set, assert the process exits non-zero and `publications.html` bytes are unchanged (no commit).
    - **Validates: Requirements 3.9, 3.10, 5.1, 5.2, 5.5**

  - [x]* 5.7 Test: fetch retry and empty-result handling (mocked)
    - Mock `scholarly` so each attempt raises and assert the retry loop makes up to 3 attempts before raising `RetrievalError`; mock a zero-record success and assert `BelowThresholdError`; use fixtures captured from a realistic `scholarly` response shape.
    - _Requirements: 3.2, 3.10, 5.5, 5.6_

  - [x]* 5.8 Property test: curated-entry preservation and deduplication
    - **Property 7: Curated-entry preservation and deduplication** — over generated Scholar result sets, assert every curated publication appears exactly once and any Scholar duplicate of a curated work (by normalized title or shared DOI) collapses to one entry with the curated wording; non-duplicate Scholar entries are all retained.
    - **Validates: Requirements 3.3, 5.4**

- [x] 6. Checkpoint - generator core and tests
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Pin the sync dependency
  - [x] 7.1 Add `requirements.txt` pinning `scholarly`
    - Create a `requirements.txt` at the repo root pinning a specific `scholarly` version for reproducible installs in the workflow.
    - _Requirements: 3.1, 3.2_

- [x] 8. Wire up the Sync_Workflow
  - [x] 8.1 Create `.github/workflows/sync-publications.yml`
    - Configure triggers `schedule` with cron `0 0 1 * *` and `workflow_dispatch` (identical job for both), a `sync-publications` concurrency group with `cancel-in-progress: false`, and `contents: write` permission.
    - Add steps: checkout → setup Python → install from `requirements.txt` (`scholarly`) → run `scripts/generate_publications.py` → commit and push as `github-actions[bot]` only when `git status --porcelain` shows a diff; a non-zero script exit fails the job with no commit.
    - _Requirements: 3.1, 3.5, 3.6, 3.8, 3.9, 4.1, 4.2, 4.3, 4.4, 4.5, 5.3_

- [x] 9. Final checkpoint - sync pipeline
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional (content validation and the property/unit test sub-tasks) and can be skipped for a faster MVP; core implementation tasks are never optional.
- Workstream A (tasks 1–2) and Workstream B (tasks 3–9) are independent — content can ship without the sync.
- Property-based test sub-tasks map directly to the design's Correctness Properties (Properties 1–7) and each references the requirement clause it validates.
- The two hand-entered publications are preserved via a curated-merge (`scripts/curated_publications.json` + `merge`/dedupe, curated wins); the merge runs after the threshold guard, and the Scholar-fetched count — not the merged count — still drives the below-threshold guard.
- The static content edits have no automated tests; verification is manual/visual with optional HTML well-formedness checks. The workflow YAML is validated by inspection and a manual `workflow_dispatch` dry run rather than unit tests.
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
    { "id": 8, "tasks": ["8.1"] }
  ]
}
```
