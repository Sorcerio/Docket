---
id: BUG-6
title: Key Removal Checks Usage Outside the Lock
status: todo
priority: 4
requires: [BUG-5]
metadata: {}
---

# Key removal checks usage outside the lock

## Problem

Removing a key is two locked operations with an unlocked gap between them.

`docket key reject` calls `store.usedKeys()`, which takes the shared lock, releases it, and then calls `config.removeKey(usedBy=...)`, which takes the exclusive lock. A ticket created under that key in the gap is not seen by the usage check, so the removal proceeds and strands the new ticket under a key that no longer exists. `validate` reports it afterwards, which is the same shape of "only noticed later" failure `BUG-5` was about.

The same gap exists for any caller pairing a read with a decision to write, but this is the only one in the codebase today.

## Why it was left open

`BUG-5` closed the read-modify-write races inside `docket.core` by holding one lock across each individual operation. This one cannot be closed the same way, because the two halves live in the caller rather than in one core method.

The obvious fix, having `removeKey` compute `usedBy` itself inside its own write lock, does not work. `usedKeys()` calls `loadAll()`, which takes the shared lock, and `filelock.ReadWriteLock` raises `RuntimeError` on a write-to-read downgrade rather than allowing the nesting. That constraint is why `Store` has a private `__loadAllUnlocked` at all.

## Directions, undecided

- Hoist the lock to the command level, so a CLI command or MCP handler opens one exclusive lock and every core call inside it uses an unlocked form. Correct and general, but it means every core method needs both a locked and an unlocked variant, and the rule about which to call becomes something every future caller has to get right.
- Give `Config.removeKey` an unlocked usage scan, reusing `Store.__loadAllUnlocked` through some shared seam, so the whole check-and-remove sits in one write lock. Narrow and cheap, but it couples `Config` to `Store`, which currently only depends the other way.
- Accept the gap and make the failure recoverable instead, by having `key reject` re-check inside the lock and refuse with the usual "N tickets use it" error. Does not remove the race, converts it from silent stranding into a loud refusal.

## Notes

Not reachable by accident in single-user work. It needs a ticket created under a key in the same seconds that key is being removed, which in practice means an agent and a human acting at once, or two agents.

Related ordering detail from `BUG-5`: `removeKey` now checks `usedBy` before taking the lock and checks registration after, because the registration check reads state the lock protects. Removing a key that is both unregistered and reported as used therefore reports "in use" rather than "not registered". Not reachable through the CLI, but whatever fixes this ticket should tidy that ordering up.
