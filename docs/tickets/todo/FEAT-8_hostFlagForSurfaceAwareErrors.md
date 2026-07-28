---
id: FEAT-8
title: Host Flag
status: todo
priority: 4
requires: []
---

# Host Flag

Docket runs under three hosts and knows which one only by accident.
`cli.py` and `server.py` each know what they are, but nothing below them does, so any code that needs to answer "who is calling" cannot.

Add that answer as a first-class piece of state.
A `Host` enum with three members, `MCP`, `CLI`, and `MODULE`, living in core, readable by anything that needs it.
`MODULE` is the default, so importing `docket` as a library never claims to be an entry point it is not.
`cli.main` and `server.main` set it as their first act, before any core call can run.

This is general host identity, not an error-message mechanism.
Error phrasing is the first consumer and the one that prompted the ticket, but the flag exists for anything that legitimately differs by host.

## Things that will want it

Error recovery text is the known case, described below.

Beyond that, output and formatting decisions belong here.
The CLI can style and wrap, the MCP surface must not, and a library caller should get neither.
Whether progress or warnings are printed at all is a host question.

So is anything interactive.
A prompt, a confirmation, or a retry loop is reasonable under `CLI`, impossible under `MCP`, and wrong under `MODULE`.

So is verbosity and detail level, since an agent reading a tool result and a person reading a terminal want different amounts of the same information.

The list is open on purpose.
The rule is that the flag answers "who is calling", and callers decide what to do with the answer.
Nothing that determines whether an operation is *allowed* may branch on it, because a rule that changes by host is two rules that will drift.

## The error audit

Two messages already cross the line, in opposite directions.
`Config.requireKnownKey` ends with "Ask the user whether to add a new one, then call add_key", which names an MCP tool no CLI user can call.
`findConfigPath` ends with "Run 'docket deploy .' at the repository root to create one", which names a shell command the MCP server cannot run.
The first became more visible when `docket list --key` and `docket graph --key` began rejecting unregistered keys, since it now reaches the CLI from four commands rather than two.

Walk every `DocketError` raised in `docket.core` and split each message into the fact and the recovery.
The fact is the same for every host.
The recovery is the part naming `add_key`, `docket key add`, `docket deploy .`, `list_keys`, or any other tool or command, and that part is chosen by the flag.
Under `MODULE` a message names no tool and no command, since a library caller has neither.

At minimum this covers `requireKnownKey`, `findConfigPath`, and the key refusal on `Store.create`.
The sweep is finished rather than sampled.

## Alternatives already considered and rejected

Passing a recovery string into each core call was rejected because it threads presentation text through the core, and because it solves only the error case rather than the general question.
Sniffing `sys.argv[0]` or whether stdin is a terminal was rejected because both entry points are console scripts and the CLI is piped often enough that the check would misfire.
Leaving the recovery out of the core entirely, and appending it at each surface, was rejected because the server does not catch `DocketError` at all, so there is no place to append it without wrapping every tool.

## Notes

The flag is process global, so tests must reset it.
A fixture setting it to `MODULE` and restoring the previous value afterwards keeps one test from leaking a host into the next.

`MODULE` being the default matters for the test suite too, since the tests import the package rather than launching either entry point.
Any behavior that reads the flag needs a test per host, not one test under whichever host happened to be set.
