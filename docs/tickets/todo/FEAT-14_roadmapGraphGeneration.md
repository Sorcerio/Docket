---
id: FEAT-14
title: Roadmap Graph Generation
status: todo
priority: 2
requires: [FEAT-6]
metadata: {}
---

# Roadmap Graph Generation

Generates a Markdown file named `roadmap.md` with an embedded (code fenced) Mermaid diagram using the `graph` command.

This will allow repos to automatically maintain a visual ticket graph in the repo.

Fallbacks or culling for older tickets (as pertaining to `requires` distance from open tickets) should also be considered here since Mermaid.js does have a maximum node count.
