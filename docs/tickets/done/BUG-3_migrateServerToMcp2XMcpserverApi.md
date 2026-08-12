---
id: BUG-3
title: Migrate Server to MCP 2.x MCPServer API
status: done
priority: 0
requires: []
metadata: {}
---

# Migrate server to mcp 2.x MCPServer API

## Problem

`src/docket/server.py` imports `from mcp.server.fastmcp import FastMCP`. That module no longer exists in `mcp` 2.0.0. A fresh install outside this repository resolved `mcp>=1.28.1` to 2.0.0 and the entry point died immediately:

```
File "...\site-packages\docket\server.py", line 22, in <module>
    from mcp.server.fastmcp import FastMCP
ModuleNotFoundError: No module named 'mcp.server.fastmcp'
```

The repository's own `uv.lock` pins 1.28.1, so development never saw it. Only installed users did.

The immediate bleeding was stopped by tightening the dependency to `mcp>=1.28.1,<2` in `pyproject.toml`. That is a holding action, not the fix. This ticket is the fix.

## What changed in mcp 2.x

`FastMCP` was renamed and moved. The replacement is `MCPServer`, living at `mcp.server.mcpserver` and re-exported from `mcp.server`:

```python
from mcp.server import MCPServer
```

Alongside it the package now ships `mcp_types` as a separate distribution, and `mcp.server` exports `CacheHint`, `ServerRequestContext`, `NotificationOptions`, and `InitializationOptions`.

## Work

- Swap the import and the `mcp: FastMCP = FastMCP(...)` construction for `MCPServer`, confirming `name` and `instructions` are still the constructor's parameter names.
- Audit the private poke at line 56, `mcp._mcp_server.version = __version__`. It reaches through `FastMCP` into the lowlevel server because `FastMCP` accepted no version of its own. `MCPServer` may take a version directly, in which case the private access disappears and the comment above it goes with it. If it does not, find where the attribute moved rather than assuming the old path survived.
- Verify the tool decorator surface. Every handler in this module is registered through it, so a signature or naming change there touches all of them.
- Re-widen the pin to `mcp>=2,<3` once the migration lands, and refresh `uv.lock`.
- Run the server against a real client and confirm the handshake advertises the correct version, not the `mcp` package's.

## Notes

Bound the upper end of the range this time. The unbounded `>=` is what let a major release reach users unannounced.
