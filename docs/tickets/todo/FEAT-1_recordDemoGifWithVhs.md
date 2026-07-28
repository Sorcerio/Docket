---
id: FEAT-1
title: Record demo GIF with VHS
status: todo
priority: 2
requires: []
---

# Record demo GIF with VHS

Record terminal demo showing Docket in action, for top of README.

Use [VHS](https://github.com/charmbracelet/vhs) (charmbracelet) to script and render the recording, not a manual screen capture, so it's reproducible and diffable.

Suggested flow to capture:
- `docket create-ticket` (or equivalent CLI) creating a ticket
- `docket list` showing it
- An agent reading/updating the ticket via MCP (`read_ticket` / `set_status`), if practical to show in one terminal

Output as a GIF, embed near the top of README.md. Keep it short, a few seconds looping is more effective than a long recording.
