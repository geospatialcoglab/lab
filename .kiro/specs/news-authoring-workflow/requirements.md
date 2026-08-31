# Requirements Document

## Introduction

The lab news section currently lives in two hand-edited places that must be kept in sync: the full article list in `news.html` and a condensed two-item mirror in `index.html`. The two locations use different markup (`news-article` with `h2` versus `news-item` with `h3`), so adding one post means writing HTML twice and getting both right. Today that work requires editing HTML directly and, in practice, the principal investigator's involvement.

This feature replaces hand-editing with a structured data source plus a generator. A contributor writes one Markdown file per news post. A generator renders both the `news.html` article list and the `index.html` preview from that single source and splices each rendered block between HTML comment sentinels, preserving every other byte of both pages. Review happens through a pull request, so a contributor needs collaborator access to the repository but never the principal investigator's credentials.

The design deliberately mirrors the existing, tested publications pipeline (`scripts/generate_publications.py`, `scripts/curated_publications.json`, sentinel-based `inject()`, and the review-gated `sync-publications.yml` workflow that opens a pull request instead of pushing to the default branch). The data format is kept simple and conventional so a form-based content management system can be layered on top of the same files later without changing the format.

### Scope Notes and Assumptions

- The site has no build system and no static site generator. Pages are served as committed files by GitHub Pages, so the generated HTML is committed to the repository rather than built at deploy time.
- The generator uses the Python standard library only, matching the publications generator, so no Markdown library is available and the accepted post body syntax is an explicitly defined Markdown subset.
- Post dates carry month precision (for example `2026-08`), displayed as `August 2026`, matching the existing `news-date` values.
- Contributors work on branches inside the repository rather than on forks, because the review workflow needs write access to the pull request branch.
- The live `news.html` currently contains three articles (August 2026, February 2026, July 2025) and `index.html` previews the two most recent.

## Glossary

- **News_System**: The complete feature comprising the news data directory, the generator, and the review workflow.
- **Post_File**: A single UTF-8 Markdown file describing one news post, named `<slug>.md`.
- **Slug**: The Post_File name without the `.md` extension, restricted to lowercase letters, digits, and hyphens.
- **News_Data_Directory**: The repository directory that holds every Post_File and is the single source of truth for news content.
- **Front_Matter**: The metadata block at the top of a Post_File, delimited by a line containing exactly `---` before and after, holding `key: value` pairs.
- **Post_Body**: The Markdown content of a Post_File that follows the closing Front_Matter delimiter.
- **Post_Month**: The Front_Matter `date` value, written as `YYYY-MM`.
- **Display_Month**: The human-readable rendering of Post_Month, formatted as `Month Year` (for example `August 2026`).
- **Body_Parser**: The generator component that converts a Post_Body into a Post_Document.
- **Post_Document**: The in-memory structured representation of a parsed Post_File, comprising metadata fields and an ordered sequence of body blocks.
- **News_Renderer**: The generator component that converts ordered Post_Documents into the HTML block for the News_Page.
- **Preview_Renderer**: The generator component that converts ordered Post_Documents into the HTML block for the Home_Page preview.
- **Injector**: The generator component that replaces the text between a pair of sentinels in an HTML file.
- **News_Sentinels**: The HTML comment markers `<!-- NEWS:START -->` and `<!-- NEWS:END -->` in the News_Page.
- **Preview_Sentinels**: The HTML comment markers `<!-- NEWS_PREVIEW:START -->` and `<!-- NEWS_PREVIEW:END -->` in the Home_Page.
- **News_Page**: The repository file `news.html`.
- **Home_Page**: The repository file `index.html`.
- **News_Generator**: The command-line program that reads the News_Data_Directory and updates the News_Page and the Home_Page.
- **Preview_Count**: The number of most recent posts shown on the Home_Page, defined in exactly one place in the News_Generator, with a default value of 2.
- **Sync_Workflow**: The GitHub Actions workflow that runs the News_Generator for a pull request and for manual dispatch.
- **Contributor**: A repository collaborator with write access who adds or edits a Post_File.
- **Reviewer**: A repository maintainer who approves and merges a pull request.
- **External_Link**: A link whose target is an absolute URL on a host other than `geospatialcognitionlab.com`.
- **House_Dash_Rule**: The site convention that presented text contains no em dash (U+2014) and no en dash (U+2013).

## Requirements

### Requirement 1: Single Source of Truth for News Content

**User Story:** As a graduate student contributor, I want to add a news post by creating one plain text file, so that I can publish lab news without editing HTML in two places.

#### Acceptance Criteria

1. THE News_System SHALL store each news post as one Post_File in the News_Data_Directory.
2. THE News_Generator SHALL read every file with the `.md` extension in the News_Data_Directory as a Post_File.
3. WHEN the News_Generator runs successfully, THE News_Generator SHALL update both the News_Page article list and the Home_Page preview from the same set of Post_Files in a single execution.
4. THE News_Generator SHALL accept a Post_File whose Front_Matter contains the keys `title`, `date`, and `teaser`.
5. THE News_Generator SHALL accept the optional Front_Matter keys `short_title`, `image`, and `image_alt`.
6. WHERE a Post_File omits `short_title`, THE Preview_Renderer SHALL use the `title` value as the Home_Page headline.
7. THE News_Generator SHALL treat the Slug as the identity of a post for ordering and for reporting validation errors.
8. THE News_Generator SHALL require no credentials and no network access to run.

### Requirement 2: Post Body Expressiveness

**User Story:** As a contributor, I want to write multi-paragraph posts with subheadings, lists, links, emphasis, and an optional image, so that I can reproduce the structure of the existing recruitment article.

#### Acceptance Criteria

1. THE Body_Parser SHALL convert a block of consecutive non-blank text lines into a paragraph block.
2. THE Body_Parser SHALL convert a line beginning with `## ` into a subheading block, and THE News_Renderer SHALL render a subheading block as an `h3` element.
3. THE Body_Parser SHALL convert consecutive lines beginning with `- ` into a single unordered list block whose items preserve source order.
4. THE Body_Parser SHALL convert the inline form `[label](target)` into a link, the inline form `**text**` into a `strong` element, and the inline form `*text*` into an `em` element.
5. WHERE a Post_File supplies the `image` key, THE News_Renderer SHALL render an `img` element carrying the class `news-image` at the start of the article body.
6. WHERE a Post_File supplies the `image` key, THE News_Generator SHALL require a non-empty `image_alt` value for the image's `alt` attribute.
7. THE News_Generator SHALL escape `&`, `<`, `>`, and `"` in every text value taken from a Post_File, including `title`, `short_title`, `teaser`, paragraph text, subheading text, list item text, link labels, and `image_alt`.
8. THE News_Generator SHALL emit the ampersand character as the entity `&amp;` in generated HTML.
9. WHEN the News_Renderer or the Preview_Renderer emits an External_Link, THE renderer SHALL add `target="_blank"`, `rel="noopener noreferrer"`, and an `aria-label` that states the link label followed by the phrase `opens in a new tab`.
10. WHEN the News_Renderer or the Preview_Renderer emits a link that is not an External_Link, THE renderer SHALL emit the anchor element without a `target` attribute and without a `rel` attribute.
11. WHEN a Post_File supplies text containing `&`, `<`, `>`, or `"`, THE News_Generator SHALL emit that character only in its escaped form and SHALL emit no occurrence of that character as active markup.

### Requirement 3: News Page Rendering

**User Story:** As a site visitor, I want the news page to look exactly as it does today, so that generated posts are indistinguishable from the hand-written ones.

#### Acceptance Criteria

1. THE News_Renderer SHALL render each post as an `article` element carrying the class `news-article`.
2. THE News_Renderer SHALL render the Display_Month inside a `span` element carrying the class `news-date` as the first child of the `article` element.
3. THE News_Renderer SHALL render the post `title` inside an `h2` element following the `news-date` element.
4. THE News_Renderer SHALL render every post in the News_Data_Directory on the News_Page.
5. THE News_Renderer SHALL indent generated markup to match the indentation depth of the existing article list so the generated block reads as hand-written HTML.
6. THE News_Renderer SHALL reuse the class names and element structure already styled in `styles.css` so that no change to `styles.css` is required for the migrated posts.
7. THE News_Renderer SHALL render the body blocks of a post in the order those blocks appear in the Post_Body.

### Requirement 4: Home Page Preview Rendering

**User Story:** As a site visitor, I want the home page to show the most recent news items, so that I see current lab activity without leaving the landing page.

#### Acceptance Criteria

1. THE Preview_Renderer SHALL render each previewed post as an `article` element carrying the class `news-item`.
2. THE Preview_Renderer SHALL render the Display_Month inside a `span` element carrying the class `news-date` as the first child of the `article` element.
3. THE Preview_Renderer SHALL render the `short_title` value, or the `title` value when `short_title` is absent, inside an `h3` element.
4. THE Preview_Renderer SHALL render the `teaser` value as a single `p` element and SHALL exclude the Post_Body from the Home_Page preview.
5. THE Preview_Renderer SHALL render the Preview_Count most recent posts.
6. WHERE the News_Data_Directory holds fewer posts than Preview_Count, THE Preview_Renderer SHALL render every available post.
7. WHEN the Preview_Count value changes, THE News_Generator SHALL produce the corresponding Home_Page preview on the next run with no edit to the Home_Page markup.

### Requirement 5: Marker-Based Injection

**User Story:** As a maintainer, I want generation to touch only the news blocks, so that the rest of both pages stays exactly as written.

#### Acceptance Criteria

1. THE Injector SHALL replace only the text strictly between the News_Sentinels in the News_Page and only the text strictly between the Preview_Sentinels in the Home_Page.
2. THE Injector SHALL preserve every byte outside the replaced regions, including the sentinel comment strings themselves.
3. WHEN the News_Generator runs twice against an unchanged News_Data_Directory, THE News_Generator SHALL produce byte-identical News_Page and Home_Page content on the second run.
4. WHEN the News_Generator runs against an unchanged News_Data_Directory whose content is already published, THE News_Generator SHALL produce a zero-byte difference in the repository.
5. IF either sentinel of a required pair is absent from its target file, THEN THE News_Generator SHALL report a descriptive error naming the missing sentinel and the file, and SHALL exit with a non-zero status.
6. IF an end sentinel appears before its matching start sentinel, THEN THE News_Generator SHALL report a descriptive error and SHALL exit with a non-zero status.
7. THE News_Generator SHALL produce identical output for identical input regardless of the operating system, the file enumeration order, and the run timestamp.

### Requirement 6: Deterministic Ordering

**User Story:** As a contributor, I want post order to follow the post date, so that I do not have to place my post in the right position by hand.

#### Acceptance Criteria

1. THE News_Generator SHALL order posts by Post_Month in descending order so that the most recent post appears first.
2. WHEN two or more posts share the same Post_Month, THE News_Generator SHALL order those posts by Slug in descending lexicographic order.
3. THE News_Generator SHALL apply the same ordering to the News_Page article list and to the Home_Page preview selection.
4. THE News_Generator SHALL derive order from Post_Month and Slug rather than from file system enumeration order.

### Requirement 7: Validation and Fail-Closed Behavior

**User Story:** As a Reviewer, I want a malformed post to stop the run with a clear message, so that a mistake never produces a broken page.

#### Acceptance Criteria

1. IF a Post_File omits a required Front_Matter key, THEN THE News_Generator SHALL report an error naming the Slug and the missing key, and SHALL exit with a non-zero status.
2. IF a Post_File contains a Front_Matter key outside the accepted set, THEN THE News_Generator SHALL report an error naming the Slug and the unrecognized key, and SHALL exit with a non-zero status.
3. IF a Post_File `date` value does not match the pattern `YYYY-MM` with a month in the range 01 through 12, THEN THE News_Generator SHALL report an error naming the Slug and the invalid value, and SHALL exit with a non-zero status.
4. IF a Post_File lacks the opening or closing Front_Matter delimiter, THEN THE News_Generator SHALL report an error naming the Slug, and SHALL exit with a non-zero status.
5. IF a Post_File contains a required field whose value is empty after whitespace is stripped, THEN THE News_Generator SHALL report an error naming the Slug and the field, and SHALL exit with a non-zero status.
6. IF a Slug contains a character outside lowercase letters, digits, and hyphens, THEN THE News_Generator SHALL report an error naming the file, and SHALL exit with a non-zero status.
7. IF any text presented to a visitor contains an em dash or an en dash, THEN THE News_Generator SHALL report an error that names the Slug, names the offending character, quotes the line of source text containing that character, and states that the Contributor replaces the character with a comma, a colon, or the word `to` for a numeric range, and SHALL exit with a non-zero status, enforcing the House_Dash_Rule.
8. IF a Post_Body line uses a Markdown construct outside the defined subset, THEN THE News_Generator SHALL report an error naming the Slug and the line number, and SHALL exit with a non-zero status.
9. IF the News_Data_Directory contains no Post_File, THEN THE News_Generator SHALL report an error and SHALL exit with a non-zero status, leaving both target pages unchanged.
10. WHEN the News_Generator detects any validation error, THE News_Generator SHALL write no bytes to the News_Page and no bytes to the Home_Page.
11. WHEN the News_Generator writes output, THE News_Generator SHALL update both target files or neither target file.
12. WHEN the News_Generator exits with a non-zero status, THE News_Generator SHALL leave the previously published News_Page and Home_Page content intact.

### Requirement 8: Migration of Existing Posts

**User Story:** As a maintainer, I want the current posts moved into the data directory, so that there is one source of truth rather than two.

#### Acceptance Criteria

1. THE News_System SHALL provide one Post_File for each news post currently present in the News_Page.
2. WHEN the News_Generator runs against the migrated News_Data_Directory, THE News_Renderer SHALL reproduce the text content, heading levels, list items, emphasis, and link targets of each existing article.
3. WHEN the News_Generator runs against the migrated News_Data_Directory, THE Preview_Renderer SHALL reproduce the existing Home_Page preview headlines, Display_Month values, and teaser text.
4. THE News_System SHALL preserve the existing link attributes of the migrated articles, including the mail link, the internal site link, and the External_Link attributes.
5. WHEN migration is complete, THE News_Page and the Home_Page SHALL contain no hand-maintained news article markup outside the sentinel regions.

### Requirement 9: Review-Gated Regeneration

**User Story:** As a Contributor, I want my pull request to show the rendered pages, so that a Reviewer approves the real result and no one needs the principal investigator's credentials.

#### Acceptance Criteria

1. WHEN a pull request targeting the default branch adds or modifies a file in the News_Data_Directory, THE Sync_Workflow SHALL run the News_Generator against the pull request head branch.
2. WHEN the News_Generator produces a change to the News_Page or the Home_Page during a pull request run, THE Sync_Workflow SHALL commit the generated files to the pull request head branch so the Reviewer sees the rendered result in the same pull request.
3. WHEN the News_Generator produces no change during a pull request run, THE Sync_Workflow SHALL complete successfully and add no commit.
4. THE Sync_Workflow SHALL limit committed paths to the News_Page and the Home_Page.
5. IF the News_Generator exits with a non-zero status, THEN THE Sync_Workflow SHALL fail the check, report the generator error output in the run log, and add no commit.
6. WHERE a pull request originates from a fork, THE Sync_Workflow SHALL run the News_Generator, report the result as a failed or passed check without committing, and state in the run log that the Contributor must run the News_Generator locally.
7. THE Sync_Workflow SHALL support manual dispatch so a maintainer can regenerate on demand.
8. THE Sync_Workflow SHALL operate using the built-in workflow token with `contents: write` and `pull-requests: write` permissions and SHALL require no personal access token.
9. THE Sync_Workflow SHALL queue overlapping runs so that at most one run per pull request is in flight.
10. WHEN a Reviewer merges the pull request into the default branch, THE existing GitHub Pages deployment workflow SHALL publish the updated pages with no further manual step.

### Requirement 10: Contributor Enablement

**User Story:** As a graduate student who has never edited the site, I want written instructions and a working example, so that I can add a post on my first attempt.

#### Acceptance Criteria

1. THE News_System SHALL document the Post_File format, including every accepted Front_Matter key and the accepted Post_Body syntax, in `HOW-TO-UPDATE.txt`.
2. THE News_System SHALL document the contributor procedure covering branch creation, Post_File creation, pull request submission, and review.
3. THE News_System SHALL document the command that runs the News_Generator locally.
4. THE News_System SHALL provide a template Post_File that a Contributor copies to start a new post.
5. WHEN the documented procedure is followed, THE News_System SHALL require repository collaborator access and SHALL require no credential belonging to the principal investigator.
6. THE News_System SHALL document the removal of the previous instruction to mirror the two most recent posts into the Home_Page by hand.
7. THE News_System SHALL document that a word processor such as Microsoft Word or Google Docs converts a typed hyphen into an em dash without notice, SHALL document how a Contributor disables that conversion, and SHALL document how a Contributor replaces an em dash or an en dash already present in a draft.
