# Requirements Document

## Introduction

This feature adds three capabilities to the existing Geospatial Cognition Lab static website (plain HTML/CSS/JS, hosted on GitHub Pages):

1. A short news announcement on `news.html` stating that the lab is recruiting a funded PhD student.
2. An expanded news article on `news.html` presenting the full PhD recruitment call written by Dr. McWhorter (the announcement and the full call live in the same news item — no separate standalone page).
3. An automated pipeline that periodically pulls the lab's publications from the Google Scholar profile and regenerates the publications list on `publications.html`, keeping it updated as new work is published over time.

A key technical constraint shapes requirement 3: Google Scholar provides no official public API and actively blocks automated scraping (CAPTCHAs, IP blocking). Because the site is static and served by GitHub Pages, a live client-side fetch from the browser is not feasible. Based on user decisions, the chosen approach is a **scheduled GitHub Actions workflow** that runs on a monthly cadence and can also be triggered manually on demand. Rather than committing directly to the live site, when the sync produces a change it proposes the update via a pull request that the maintainer reviews and merges, so nothing is published without review. When the sync fails, the previously committed (last good) `publications.html` is preserved and manual editing remains the accepted fallback.

The recruitment call text has been supplied by the user. One detail — the full funding specifics beyond "guaranteed funding for the first two years" — is pending and is treated as a to-be-confirmed value in the content.

## Glossary

- **Site**: The Geospatial Cognition Lab static website served from GitHub Pages at geospatialcognitionlab.com.
- **News_Page**: The `news.html` document containing the `.news-list` of `<article class="news-article">` items.
- **News_Item**: A single `<article class="news-article">` element with a `.news-date` span, a heading, and paragraph content.
- **Recruitment_Announcement**: The News_Item that announces the funded PhD recruitment and contains the full recruitment call.
- **Publications_Page**: The `publications.html` document containing the `.publications-list` of `.pub-year` blocks and `.publication` entries.
- **Scholar_Profile**: The Google Scholar profile at `https://scholar.google.com/citations?user=Xu5F1CAAAAAJ&hl=en`.
- **Sync_Workflow**: The scheduled GitHub Actions workflow that fetches publications from the Scholar_Profile, regenerates the Publications_Page, and proposes any change via a Sync_Pull_Request rather than committing directly to the default branch.
- **Sync_Pull_Request**: The pull request that the Sync_Workflow opens or updates, containing the regenerated Publications_Page on a dedicated sync branch, for maintainer review before merging into the default branch.
- **Generator_Script**: The script invoked by the Sync_Workflow that transforms fetched publication data into the Publications_Page HTML markup.
- **Last_Good_Version**: The most recently committed, successfully generated version of the Publications_Page prior to any failed sync attempt.
- **Site_Style**: The existing shared markup and CSS conventions of the Site (`.navbar`, `.page-header`, `.section`/`.section-gray`, `.footer`, and the news/publication class patterns).

## Requirements

### Requirement 1: PhD Recruitment Announcement on the News Page

**User Story:** As a lab director, I want a news announcement that the lab is recruiting a funded PhD student, so that prospective applicants learn about the opportunity when they visit the news page.

#### Acceptance Criteria

1. THE News_Page SHALL contain exactly one Recruitment_Announcement News_Item whose text states that the Geospatial Cognition Lab is recruiting a PhD student, that the position is funded, and that the position is in-residence.
2. THE Recruitment_Announcement SHALL be an `<article class="news-article">` element that contains one `<span class="news-date">` element and one heading element, matching the element structure used by the other News_Items in the `.news-list`.
3. THE Recruitment_Announcement SHALL be the first `<article class="news-article">` child element within the `.news-list` container, appearing before all other News_Items.
4. THE Recruitment_Announcement SHALL display a `.news-date` value formatted as a full month name followed by a space and a four-digit year (for example, "February 2026"), matching the format of the existing `.news-date` values on the News_Page.
5. THE Recruitment_Announcement `.news-date` value SHALL be equal to or later than the `.news-date` value of every other News_Item in the `.news-list`, so that it is the most recent item.

### Requirement 2: Full Recruitment Call Content

**User Story:** As a prospective PhD applicant, I want to read the complete recruitment call with all program, qualification, funding, and application details, so that I can decide whether to apply and know how to do so.

#### Acceptance Criteria

1. THE Recruitment_Announcement SHALL display the complete recruitment call content inline within the same News_Item on news.html, without requiring navigation to a separate page or distinct URL.
2. THE Recruitment_Announcement SHALL state that the position is a funded, in-residence PhD position in the Fire & Emergency Management Administration (FEMP) program at Oklahoma State University in Stillwater, with research conducted through the Geospatial Cognition Lab.
3. THE Recruitment_Announcement SHALL state that the available start terms are Spring 2027 or Fall 2027.
4. THE Recruitment_Announcement SHALL describe the program and lab context, including the multidisciplinary nature of FEMP, the in-residence graduate cohort in Stillwater, the network of remote MS and PhD students, and the live hybrid (in-person and Zoom) course format.
5. THE Recruitment_Announcement SHALL list the qualifications and preferred skills, and SHALL state that a completed master's degree is required for admission.
6. THE Recruitment_Announcement SHALL state that the position includes guaranteed funding for the first two years, with additional anticipated support through teaching assistantships and externally funded research projects.
7. WHERE detailed funding specifics remain unconfirmed, THE Recruitment_Announcement SHALL present the confirmed funding statement using the "guaranteed funding for the first two years" language, AND SHALL enclose any unconfirmed specifics within a visible placeholder marker (bracketed text) that is visually distinguishable from surrounding confirmed content.
8. THE Recruitment_Announcement SHALL provide application instructions directing applicants to email Dr. Chelsie McWhorter at Chelsie.McWhorter@okstate.edu, and SHALL list the four required materials: a CV, unofficial transcripts, a brief (defined as one to two paragraph) statement of research interests, and preferred start semester.
9. THE Recruitment_Announcement SHALL present the application email address (Chelsie.McWhorter@okstate.edu) as a mailto: hyperlink.
10. WHEN a visitor activates the application email hyperlink, THE Recruitment_Announcement SHALL open the visitor's default email client with the recipient address (Chelsie.McWhorter@okstate.edu) pre-filled.
11. THE Recruitment_Announcement SHALL state that applications are reviewed on a rolling basis until the position is filled, and that materials received on or before October 1, 2026 receive priority consideration for a Spring 2027 start.
12. THE Recruitment_Announcement SHALL present references to the Geospatial Cognition Lab website (geospatialcognitionlab.com) and the FEMP program website (femp.okstate.edu) as hyperlinks whose destinations resolve to those respective addresses.

### Requirement 3: Automated Publication Sync from Google Scholar

**User Story:** As a lab director, I want the publications page to be regenerated automatically from my Google Scholar profile, so that new publications appear on the site over time without manual re-entry for every paper.

#### Acceptance Criteria

1. THE Sync_Workflow SHALL be implemented as a GitHub Actions workflow within the Site repository.
2. WHEN the Sync_Workflow runs, THE Sync_Workflow SHALL fetch publication data from the Scholar_Profile identified by user id Xu5F1CAAAAAJ, retrying up to 3 attempts and applying a 120-second timeout per attempt.
3. WHEN the Sync_Workflow runs successfully, THE Generator_Script SHALL produce Publications_Page markup that reuses the existing .publications-list container, groups each publication set within a .pub-year element in descending year order, and maps each publication's authors to a .pub-authors element, title to a .pub-title element, venue to a .pub-venue element, and link to a .pub-link element within a .publication element.
4. WHEN the Sync_Workflow produces regenerated Publications_Page markup, THE Sync_Workflow SHALL group publications by year in descending year order.
5. WHEN a byte-for-byte comparison shows the regenerated Publications_Page differs from the committed version, THE Sync_Workflow SHALL push the regenerated Publications_Page to a dedicated sync branch and open or update a Sync_Pull_Request targeting the default branch, rather than committing directly to the default branch.
6. WHEN a byte-for-byte comparison shows the regenerated Publications_Page is identical to the committed version, THE Sync_Workflow SHALL open no Sync_Pull_Request and make no change.
7. THE regenerated Publications_Page SHALL change only the content within the .publications-list container and SHALL preserve the navbar, page header, footer, and referenced stylesheet and script unchanged.
8. WHILE the Sync_Workflow is not manually triggered, THE Sync_Workflow SHALL run on a scheduled trigger.
9. IF the Sync_Workflow fails to fetch publication data after 3 attempts, THEN THE Sync_Workflow SHALL open no Sync_Pull_Request, preserve the existing Publications_Page unchanged, and report the run as failed.
10. IF the fetched publication data contains zero publications, THEN THE Sync_Workflow SHALL open no Sync_Pull_Request and preserve the existing Publications_Page unchanged.
11. THE Sync_Workflow SHALL NOT modify the default-branch Publications_Page directly, AND changes SHALL reach the default branch only through the maintainer merging the Sync_Pull_Request.
12. WHEN the Sync_Workflow opens or updates a Sync_Pull_Request, THE Sync_Workflow SHALL rely on GitHub's standard pull-request notifications to inform the maintainer so that the maintainer reviews the diff before merging.

### Requirement 4: Sync Scheduling and Manual Trigger

**User Story:** As a lab director, I want the sync to run on a regular schedule and also on demand, so that publications stay current without me remembering to run it, while still letting me refresh it immediately when needed.

#### Acceptance Criteria

1. THE Sync_Workflow SHALL run automatically on a schedule of once per calendar month, on the 1st day of the month at 00:00 UTC.
2. THE Sync_Workflow SHALL support manual on-demand triggering from the repository's Actions interface.
3. WHEN the Sync_Workflow is triggered manually, THE Sync_Workflow SHALL perform the same fetch, generation, and pull-request proposal behavior as a scheduled run.
4. IF a Sync_Workflow run is triggered (scheduled or manual) while another Sync_Workflow run is already in progress, THEN THE Sync_Workflow SHALL either queue the new run to start after the in-progress run completes or cancel one of the runs, ensuring no more than one run proposes a Sync_Pull_Request at the same time.
5. IF a Sync_Workflow run fails to complete its fetch, generation, or pull-request proposal steps, THEN THE Sync_Workflow SHALL report a failed run status in the repository's Actions interface and SHALL propose no Sync_Pull_Request containing partial or incomplete results.

### Requirement 5: Failure Handling and Manual Fallback

**User Story:** As a lab director, I want the site to remain intact when the Scholar sync fails, so that a blocked or broken automated run never degrades the live publications page.

#### Acceptance Criteria

1. IF the Sync_Workflow does not obtain a valid publication dataset from the Scholar_Profile after exhausting all retry attempts, THEN THE Sync_Workflow SHALL leave the Last_Good_Version of the Publications_Page byte-for-byte unchanged in the repository.
2. IF the Sync_Workflow fails to retrieve publication data from the Scholar_Profile, THEN THE Sync_Workflow SHALL NOT propose a Sync_Pull_Request that removes, empties, or reduces the number of existing publication entries on the Publications_Page.
3. IF the Sync_Workflow fails, THEN THE Sync_Workflow SHALL report a non-successful (failed) run status visible in the repository's Actions interface, including an indication of the failure reason (retrieval failure or below-threshold result).
4. THE Publications_Page SHALL be stored as a hand-editable file such that a manual commit to it is published without requiring a successful Sync_Workflow run and is not reverted by the Sync_Workflow unless a subsequent run succeeds and meets the minimum threshold.
5. IF the fetched publication dataset contains fewer entries than the configured minimum threshold (default 1 entry, adjustable via configuration), THEN THE Sync_Workflow SHALL treat the run as a failure and SHALL leave the Last_Good_Version unchanged.
6. WHEN the Sync_Workflow requests publication data from the Scholar_Profile, THE Sync_Workflow SHALL retry the request up to 3 times before declaring a retrieval failure.
7. IF a single request to the Scholar_Profile does not return a response within 30 seconds, THEN THE Sync_Workflow SHALL treat that request as failed.
