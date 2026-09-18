---
id: FEAT-6
title: Templates for Tickets per Key
status: todo
priority: 3
requires: []
---

# Templates for Tickets per Key

Using a templater like `jinja2` (decide an appropriate vector during implementation), Keys can optionally have a custom template for their tickets.

Use case is that for Features, freeform writing like in this ticket is acceptable.
However, for tickets like Bugs, having specific sections pre-established for things like "What Happened", "Reproduction Steps", and "What is Expected" are standard.

## Notes from FEAT-18

`jinja2` is already a dependency, added by `FEAT-18` to render the offsite authoring brief, so the choice of templater is made unless there is a reason to revisit it.

`FEAT-18` renders one document shipped inside the package, through `_buildEnvironment` in `docket.core.handoff` and `readPackageText` in `docket.core.resources`. What this ticket needs is different enough to be worth naming: the templates are authored by the consumer repository rather than shipped, so they load from the working tree rather than from package data, and they render against one ticket rather than against the registry. The environment construction is the only piece worth sharing, and hoisting it out of `handoff.py` into something like `docket.core.templating` is the natural move once there is a second caller to shape it against.

On the command surface, `docket docs` is taken by `FEAT-18` and `docket template` is deliberately left free for this. `docket key template BUG` is worth weighing against it, since a template is a property of a key and keys already have their own group.
