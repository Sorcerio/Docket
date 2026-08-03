# Tickets

This directory is managed by `docket`. Read this before touching anything in it.

## What a ticket is

A markdown file with a YAML frontmatter block.

```markdown
---
id: CORE-14
title: Skirmish setup
status: todo
priority: 1
requires: [CORE-9, GEN-3]
---

# Skirmish setup

Prose, unparsed and unconstrained.
```

| Field | Meaning |
|---|---|
| `id` | `<KEY>-<NUM>`. Allocated at creation. Never change it. |
| `title` | Free text. May change. The filename does not follow it. |
| `status` | `todo`, `wip`, or `done`. Nothing else is valid. |
| `priority` | Integer, `0` most urgent. |
| `requires` | Ids this ticket depends on. May be empty. |
| `metadata` | Free-form `{key: value}` map for any tool or skill to attach data to. Namespace your key so it cannot collide with another consumer's. |

Any other field is preserved untouched, so this repository may add its own.

Everything below the frontmatter is yours. No tool parses it.

## The body is yours. The frontmatter is not.

A ticket file has two halves, and they have different rules.

**The body, everything below the closing `---`, is yours to edit directly.** Rewrite it, extend it, restructure it, correct it. No tool parses it and no tool will overwrite it. There is no MCP tool for editing a body, because editing it in place is the intended way. Do that freely and often, especially to record something you just worked out.

**The frontmatter block, and where the file lives, belong to the tool.** Do not hand-edit those fields, and do not create, move, rename, or delete ticket files yourself.

| Want to change | Do this |
|---|---|
| The prose in the body | Edit the file directly |
| `title`, `priority`, `requires` | `update_ticket` |
| one `metadata` entry | `set_metadata` |
| `status` | `set_status` |
| Nothing, you just want to read it | `read_ticket` |

Never move a file between `todo/` and `done/` yourself. The `status` field is the truth and the directory is a projection of it. `set_status` writes both together, and it is the only thing that does. A file moved by hand leaves the two disagreeing, and `validate` will report it as an error.

Filenames are frozen at creation. Retitling a ticket deliberately does not rename its file, because renaming would break every prose cross-reference pointing at it from other tickets. Do not rename one to "fix" a stale slug. It is stale on purpose.

## The rest of the tools

| To do this | Call this |
|---|---|
| See what exists | `list_tickets` |
| Read one ticket in full | `read_ticket` |
| Create a ticket | `create_ticket` |
| See the dependency graph | `graph` |
| See valid keys | `list_keys` |
| Add a new key | `add_key`, after asking the user |
| Check the set is sound | `validate` |

## Dependencies point one way

A ticket declares what it `requires`. It never declares what it blocks.

The reverse direction is derived, not stored. `read_ticket` returns both, so to find out what a ticket is blocking, read it and look at `requiredBy`. Do not add a "blocks" field. Storing both directions guarantees they eventually disagree, which is exactly what this design exists to prevent.

To change one edge, use `update_ticket` with `requires_add` or `requires_remove` rather than reading the list and passing it back with one entry different. Those edit the list in place, so nothing you did not name is at risk. Reserve `requires` for when you genuinely mean to replace the whole list, and never pass it in the same call as an edit, which is refused.

## Keys are closed

A ticket's key is the part before the hyphen. It groups related work.

Keys must be registered before use. `create_ticket` refuses an unregistered one, which is what stops a typo silently spawning an orphan group.

Call `list_keys` before creating a ticket rather than guessing.

**When no existing key fits, ask the user before adding one.** Use `AskUserQuestion`. Name the key you have in mind, say what it would group, and say why the existing keys do not cover the work. Offer the closest existing key as an alternative option, because most of the time that is the right answer.

Only once the user has agreed, call `add_key` with the key, a description, and the rationale they just gave you. Never call it on your own judgement. How this repository is carved up is the user's decision, and a key added without asking is a structural change nobody signed off on.

If you are mid-batch and the user is not there to answer, use the closest existing key and say so in the ticket body. Do not stall the batch, and do not invent a key.

## Write tickets for a reader who was not there

This is the part that matters most.

A ticket is read weeks later by someone, or something, with none of the context you have right now. Put that context in the ticket.

Include the architecture that was discussed, the assumptions being made, and the questions that were already asked and answered. State them plainly in the body, where a new reader will see them. A ticket that only makes sense to whoever was in the conversation is a ticket that will be redone from scratch.

## After writing a batch

Call `validate`.

A `requires` entry naming a ticket that does not exist yet is only a warning at creation time, so that writing a batch out of order does not strand you halfway. It becomes an error in `validate`. Run it when the batch is done and resolve what it reports.
