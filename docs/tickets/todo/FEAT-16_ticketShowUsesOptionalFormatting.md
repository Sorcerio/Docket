---
id: FEAT-16
title: Ticket Show Uses Optional Formatting
status: todo
priority: 2
requires: []
metadata: {}
---

# `docket <ticket> show` Uses Optional Formatting

`docket <ticket> show` should supply optional formatting.

By default, we should make the the current metadata display more robust since right now it's difficult to read. The Markdown content of the ticket should also be rendered using `rich.markdown.Markdown` instead of as plain text.

Up for debate if a non-formatted version even needs to exist since `cat <etc>` exists.
