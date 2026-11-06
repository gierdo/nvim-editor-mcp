# nvim-editor-mcp

MCP server bridging tool calls to Neovim editor actions via RPC.

Exposes Neovim operations (open files, run Lua, diagnostics, quickfix,
notifications) as [Model Context Protocol](https://modelcontextprotocol.io/)
tools, so AI agents can drive your editor.

## Installation

Requires [uv](https://docs.astral.sh/uv/) and Python ≥ 3.11.

```sh
uv tool install .
```

This puts `nvim-editor-mcp` on your `PATH`.

## Usage

`nvim-editor-mcp` auto-discovers the  socket from the `$NVIM` env var, which is
set when the mcp is started from nvim, e.g. through
[codecompanion](https://github.com/olimorris/codecompanion.nvim)

```sh
nvim-editor-mcp

# Explicit socket path
nvim-editor-mcp --socket /tmp/nvim.sock

# Show a Vim message whenever the MCP performs an action
nvim-editor-mcp --notify
# Or via environment variable: NVIM_MCP_NOTIFY=true nvim-editor-mcp
```

The server starts in stdio MCP mode. If no socket is given and `$NVIM` is
unset, it starts anyway and discovers the socket on the first tool call (via
`attach_nvim`).

### Tools

| Tool | Description |
| ------- | ------------- |
| `list_nvim_instances` | List running Neovim instances with socket path, cwd, open buffers, and Herdr pane info |
| `attach_nvim` | Connect to a Neovim instance by socket path (or auto-attach to the matching instance) |
| `detach_nvim` | Detach from the current Neovim instance |
| `open_file` | Open a file at a specific line |
| `set_quickfix` | Populate the quickfix list |
| `get_diagnostics` | Fetch LSP diagnostics |
| `nvim_exec_lua` | Execute arbitrary Lua in Neovim |
| `notify` | Show a notification in Neovim |

### MCP client configuration

```json
{
  "mcpServers": {
    "nvim-editor-mcp": {
      "command": "nvim-editor-mcp"
    }
  }
}
```

## Development

### Setup

```sh
uv sync
```

This creates a `.venv` and installs all runtime + dev dependencies.

### Linting & formatting

```sh
uv run ruff check .
uv run ruff format .
```

### Type checking

```sh
uv run ty check
```

### Tests

```sh
uv run pytest
```

### All checks (CI-style)

```sh
uv run ruff check . && uv run ruff format --check . && uv run ty check && uv run pytest
```

## License

GPL-2.0
