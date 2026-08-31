---
title: Post Title Goes Here: A Colon In The Title Is Fine
date: 2026-01
teaser: One or two sentences that appear on the homepage preview. Inline markup works here, including a link to the [News page](news.html).
---

This file is a template. Copy it to a new file in content/news/ named like 2026-01-my-post-title.md, using lowercase letters, numbers, and hyphens only, then edit the front matter above and replace this body text. The leading underscore in this template's file name is what keeps it out of the generated pages, so your copy must not start with an underscore.

The front matter is the block between the two lines that contain only three hyphens. Every line inside it is a key, a colon, then the value, and only the first colon on the line counts as the separator. Three keys are required: title, date, and teaser. The date carries month precision only, in the form of a four digit year, a hyphen, and a two digit month from 01 to 12.

Two front matter keys are optional. Add short_title when the full title is too long to read well as the homepage headline; the homepage then shows the short version and the News page keeps the full title. Add image together with image_alt to place one photo at the top of the post body, and note that the pair travels together: if you supply image you must also supply a non-empty image_alt describing the photo for a screen reader.

## Use this style for a subheading

A subheading is a single line beginning with two hash marks and a space, and it renders as an h3. The accepted body constructs are:

- A paragraph, which is any block of text with a blank line above and below it. Lines inside one block are joined together with a single space, so you can wrap them however you like.
- A subheading, which is a single line beginning with two hash marks and a space.
- A bulleted list, which is one or more consecutive lines each beginning with a hyphen and a space. Consecutive lines form one list.
- A link, written as the label in square brackets followed immediately by the target in parentheses.
- Bold text, wrapped in a pair of double asterisks on each side.
- Italic text, wrapped in a single asterisk on each side.

Here are the three inline forms together in one sentence: read the full call on the [News page](news.html), notice that **this text is bold**, and that *this text is italic*.

## What the generator will not accept

Anything outside the list above is a hard error naming the file and the line number, not a silent misrendering. Not supported: numbered lists, nested lists, tables, block quotes, code fences or inline code using the backtick character, inline image syntax in the body, raw HTML tags, and any heading other than the two hash mark form.

## The one that will bite you

The generator rejects the em dash character and the en dash character anywhere in a post, front matter included. Microsoft Word and Google Docs insert them automatically when you type a hyphen between words, so a draft written in either one almost certainly contains a few. Use a comma or a colon where you wanted a dash, and the word *to* for a range, as in 2024 to 2026. Pasting as plain text when you move a draft into this file avoids carrying them in.
