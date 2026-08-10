---
id: FEAT-15
title: Use Title Case for Tickets
status: todo
priority: 1
requires: []
metadata: {}
---

# Use Title Case for Tickets

Add a *script level* enforcement of proper title case for ticket titles.

Filenames remain the camelCase setup as before. This only applies to titles within the `title` key and the first automatically added header.

Existing titles in the `title` key and the first automatically added header (if possible) are checked for proper title case when `validate` is run. Any non-compliant titles will be flagged with a *warning* that includes what the title should look like. The intention is that running `validate` will be useful to both a human operator and an MCP agent operator to correct any existing non-compliant titles.
