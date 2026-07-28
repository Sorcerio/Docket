# Docket demo recording.
#
# Renders the README demo GIF against this repository's own live ticket store.
# Run from the repository root: vhs docs/demo/docket.tape
#
# On Windows, prepend the shim beside this tape to PATH, along with git's bin directory.
# Without the shim, ttyd fails to spawn a shell and VHS hangs forever with no output.
# See docs/demo/ttyd.cmd for the details.
#   $env:PATH = "$PWD\docs\demo;C:\Program Files\Git\bin;$env:PATH"
#
# The recording creates FEAT-3, leaves it behind, and clears it again on the next run.
# Re-rendering therefore needs no manual reset.
#
# That cleanup deletes any ticket whose id is FEAT-3.
# Renumber this tape if FEAT-3 ever becomes a real ticket in this repository.

Output docs/demo/docket.gif

Require docket
Require git

Set Shell bash

# Wide enough for the wrapped ticket body, and roughly 28 rows tall so `docket show` never scrolls.
# Wait+Screen matches only the visible viewport, so anything scrolled away is unmatchable.
Set FontSize 20
Set LineHeight 1.5
Set FontFamily "iMWritingMono Nerd Font Mono"
Set Width 1600
Set Height 880
Set Padding 20
Set Margin 15
Set MarginFill "#0f19f8"
Set BorderRadius 10
Set Theme "Dark Pastel"

# Nothing in a terminal moves fast enough to need more than 30fps.
# A still cursor keeps idle frames byte identical, so the long pauses cost almost nothing in the GIF.
Set Framerate 30
Set CursorBlink false
Set TypingSpeed 40ms

# Put this repository's console scripts on PATH, so the recording can type a bare `docket`.
Hide
Type `export PATH="$PWD/.venv/Scripts:$PWD/.venv/bin:$PATH"`
Enter
Type `export PS1="$ "`
Enter

# Disable history expansion, so a `!` inside a typed body is not swallowed as a history reference.
Type "set +H"
Enter

# Drop the ticket a previous recording left behind, so this run allocates FEAT-3 again rather than FEAT-4.
# The glob covers a retitled file, and both directories cover a run that reached a done status.
Type `rm -f docs/tickets/todo/FEAT-3_*.md docs/tickets/done/FEAT-3_*.md`
Enter

# Clear the setup away before capture begins.
Type "clear"
Enter
Show

# The store as it stands.
Type "docket list"
Enter
Wait+Screen /FEAT-2/
Sleep 1500ms

# Create a ticket that depends on an existing one.
Type@25ms `docket new --key FEAT --title "Cache the graph render" --requires FEAT-1 --body "Well do something!"`
Enter
Wait+Screen /Created FEAT-/
Sleep 1s

Type "docket list"
Enter
Wait+Screen /Cache the graph render/
Sleep 1500ms

# Move it to wip.
# Status is the truth and the directory follows it.
Type "docket status FEAT-3 wip"
Enter
Wait+Screen /is now wip/
Sleep 1200ms

Hide
Type "clear"
Enter
Show

# Half the promise: the ticket is a plain markdown file a human can just read.
Type@25ms "cat docs/tickets/todo/FEAT-3_cacheTheGraphRender.md"
Enter
Wait+Screen /requires/
Sleep 3s

Hide
Type "clear"
Enter
Show

# The other half: the same ticket with both dependency directions resolved.
Type "docket show FEAT-3"
Enter
Wait+Screen /Required by/
Sleep 3s

# Clear first, so validate's one line of output cannot be pushed off the visible viewport.
Hide
Type "clear"
Enter
Show

Type "docket validate"
Enter
Wait+Screen /No findings/
Sleep 1500ms

# Close on the install line, typed but never run, so the last frame is the invitation rather than a result.
# The `#` lines are shell comments, which puts the copy on screen without printing anything.
Hide
Type "clear"
Enter
Show
Sleep 500ms
Type@30ms "# Plain markdown for you. Structured MCP for your agent."
Enter
Sleep 1200ms
Type@30ms "# One command per repository."
Enter
Sleep 1s
Type@60ms "uv tool install git+https://github.com/Sorcerio/Docket"
Sleep 3500ms
