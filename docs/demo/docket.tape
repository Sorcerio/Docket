# Docket demo recording.
#
# Renders the README demo GIF against this repository's own live ticket store.
# Run from the repository root: vhs docs/demo/docket.tape

Output docs/demo/docket.gif

Require docket
Require git

Set Shell bash
Set Theme "Catppuccin Mocha"
Set FontSize 18
Set Width 1400
Set Height 800
Set Padding 20
Set Margin 20
Set MarginFill "#674EFF"
Set BorderRadius 10
Set WindowBar Colorful
Set Framerate 60
Set TypingSpeed 60ms

# Put this repository's console scripts on PATH so the recording can type a bare
# `docket`, then clear the setup away before capture begins.
Hide
Type `export PATH="$PWD/.venv/Scripts:$PWD/.venv/bin:$PATH"`
Enter
Type `export PS1="$ "`
Enter
Type "clear"
Enter
Show

# The store as it stands.
Type "docket list"
Enter
Sleep 2s

# Create a ticket that depends on an existing one.
Type `docket new --key FEAT --title "Cache the graph render" --requires FEAT-1`
Enter
Wait
Sleep 1500ms

Type "docket list"
Enter
Sleep 2s

# Move it to wip. Status is the truth and the directory follows it.
Type "docket status FEAT-3 wip"
Enter
Wait
Sleep 2s

Hide
Type "clear"
Enter
Show

# Half the promise: the ticket is a plain markdown file a human can just read.
Type "cat docs/tickets/todo/FEAT-3_cacheTheGraphRender.md"
Enter
Sleep 3s

Hide
Type "clear"
Enter
Show

# The other half: the same ticket with both dependency directions resolved.
Type "docket show FEAT-3"
Enter
Sleep 3500ms

Hide
Type "clear"
Enter
Show

# The graph is mermaid source on stdout, so it pipes and redirects.
Type "docket graph"
Enter
Sleep 3s

Type "docket validate"
Enter
Wait
Sleep 2s

# Close on the install line, typed but never run, so the last frame is the
# invitation rather than a result. The `#` lines are shell comments, which puts
# the copy on screen without printing anything.
Hide
Type "clear"
Enter
Show
Sleep 500ms
Type "# Plain markdown for you. Structured MCP for your agent."
Enter
Sleep 1500ms
Type "# One command per repository."
Enter
Sleep 1500ms
Type@90ms "uv tool install git+https://github.com/Sorcerio/Docket"
Sleep 4s
