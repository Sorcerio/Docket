---
id: FEAT-10
title: Tree Style CLI Commands
status: todo
priority: 2
requires: []
metadata: {}
---

# Tree Style CLI Commands

Right now the commands are:

```
new       Create a ticket.
show      Show a ticket with its resolved dependency context.
list      List ticket summaries.
set       Change a ticket's title, priority, or dependencies.
status    Change a ticket's status, moving its file to match.
meta      Inspect and manage a ticket's metadata map.
graph     Render the dependency graph as mermaid source.
key       Inspect and manage the key registry.
validate  Run every integrity rule.
deploy    Install docket into a repository.
upgrade   Refresh the deployed templates in a repository.
```

Instead, we should group ticket commands like this

```
ticket       Manage a specific ticket
    new      Create a ticket.
    show     Show a ticket with its resolved dependency context.
    set*     Change a ticket's traits.
    status*  Change a ticket's status, moving its file to match.
    meta     Inspect and manage a ticket's metadata map.
list         List ticket summaries.
graph        Render the dependency graph as mermaid source.
key          Inspect and manage the key registry.
validate     Run every integrity rule.
deploy       Install docket into a repository.
upgrade      Refresh the deployed templates in a repository.
```

Semantically `set` and `status` appear to operate the same medium: changing the ticket. But since `status` also reads, it is a defensible split. Lets review this pair specifically.
