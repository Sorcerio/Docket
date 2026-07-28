---
id: BUG-1
title: Fix Character Encoding Issue in FEAT-5
status: done
priority: 1
requires: []
---

# Fix Character Encoding Issue in FEAT-5

To create FEAT-5, the following command was run:

```bash
docket new --key FEAT --title "Selectiong Options in CLI" --body "For Key selection, Priority selection, and any other where a discrete set of options are available for selection in the user facing CLI, the options should be presented and the appropriate `argparse` setup for discrete selections should be used."
```

Note that the " \`argparse\` " inside FEAT-5's body came out as ` rgparse ` (leading and trailing space character included).
This means that some text encoding along the way is messed up and \` characters are important for code related work, so this must be fixed!

This does not appear to have occurred when the MCP made similar tickets with \` characters.
So, this could be related to Win11 Powershell executions of the provided command.
