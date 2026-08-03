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
# The demo runs under its own DOCK key, registered before capture and removed after.
# That fixes the ids at DOCK-1 through DOCK-3 however many real tickets exist, and no real ticket is ever touched.
#
# Setup and teardown are both idempotent, so a render that fails partway leaves nothing behind.

Output docs/demo/docket.gif

Require docket
Require git

Set Shell bash

# Wide enough for the wrapped ticket body, and roughly 28 rows tall so no beat scrolls.
# Wait+Screen matches only the visible viewport, so anything scrolled away is unmatchable.
Set FontSize 20
Set LineHeight 1.5
Set FontFamily "iMWritingMono Nerd Font Mono"
Set Width 1600
Set Height 880
Set Padding 20
# Set Margin 15
# Set MarginFill "#0f19f8"
# Set BorderRadius 10
Set Theme "Dark Pastel"
# Set WindowBar Colorful

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

# Clear anything a failed render left behind, before registering the key again.
# Tickets go first, because `key remove` refuses while any ticket still uses the key.
# Both commands are allowed to fail on a clean store, so their errors are discarded.
Type `rm -f docs/tickets/todo/DOCK-*.md docs/tickets/done/DOCK-*.md`
Enter
Type `docket key remove DOCK > /dev/null 2>&1; true`
Enter

# Register the demo key and seed the two tickets the recording opens on.
# Creation order fixes the ids, so the ticket created on camera is always DOCK-3.
Type `docket key add DOCK "demo tickets" --rationale "Reserved for the README demo recording."`
Enter
Type `docket new DOCK "Render the dependency graph"`
Enter
Type `docket new DOCK "Move a ticket when status changes"`
Enter

# Clear the setup away before capture begins.
Type "clear"
Enter
Show

# The store as it stands.
# Filtering by key holds this to three rows however large the real store grows.
Type "docket list DOCK"
Enter
Wait+Screen /DOCK-2/
Sleep 1500ms

# Create a ticket that depends on an existing one.
Type@25ms `docket new DOCK "Cache the graph render" --requires DOCK-1 --body "The graph is recomputed on every call."`
Enter
Wait+Screen /Created DOCK-3/
Sleep 1s

Type "docket list DOCK"
Enter
Wait+Screen /Cache the graph render/
Sleep 1500ms

# Move it to wip.
# Status is the truth and the directory follows it.
Type "docket DOCK-3 wip"
Enter
Wait+Screen /is now wip/
Sleep 1200ms

Hide
Type "clear"
Enter
Show

# Half the promise: the ticket is a plain markdown file a human can just read.
Type@25ms "cat docs/tickets/todo/DOCK-3_cacheTheGraphRender.md"
Enter
Wait+Screen /requires/
Sleep 3s

Hide
Type "clear"
Enter
Show

# The other half: the same ticket with both dependency directions resolved.
Type "docket DOCK-3"
Enter
Wait+Screen /Required by/
Sleep 3s

Hide
Type "clear"
Enter
Show

# The graph is mermaid source on stdout, so it pipes and redirects.
# The wait matches the final line, which proves the whole graph landed.
Type "docket graph DOCK"
Enter
Wait+Screen /class DOCK_3 wip/
Sleep 3500ms

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

# Remove the demo tickets and the demo key, leaving the store exactly as it was found.
Hide
Type `rm -f docs/tickets/todo/DOCK-*.md docs/tickets/done/DOCK-*.md`
Enter
Type "docket key remove DOCK"
Enter
