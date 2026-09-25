---
id: FEAT-20
title: CLI Accessors for All Headmatter
status: done
priority: 0
requires: []
metadata: {}
---

# CLI Accessors for All Headmatter

Right now, only `status` (which gets `status` from the headmatter) and `meta` (which gets the `metadata` from the headmatter) exist to provide pipeable accessors to headmatter data for tickets.

`show` exists, but prints the ticket information in a *human-centric* format which is not well suited for scripting.

To resolve this, accessors should be added to `docket <ticket_id> ...` in some manner to facilitate direct output of headmatter information in a pipeable way.

A note should be made in instruction files to ensure that any new ticket headmatter also receives an accessor.
