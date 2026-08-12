---
id: BUG-2
title: Cannot Clear with Set Command
status: done
priority: 0
requires: []
metadata: {}
---

# Cannot Clear With Set Command

When running the `docket set` command to clear data, an error is presented despite CLI instructions suggesting otherwise.

Example:

```bash
> docket set FEAT-4 --requires ""
Usage: docket set [-h] [--title TITLE] [--priority PRIORITY] [--requires REQUIRES] id
docket set: error: argument --requires: expected one argument

> docket set FEAT-4 --requires   
Usage: docket set [-h] [--title TITLE] [--priority PRIORITY] [--requires REQUIRES] id
docket set: error: argument --requires: expected one argument
```

Expected results are that you can actually clear requirements and other values as documented.
