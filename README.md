# nvim-editor-mcp

MCP server bridging tool calls to Neovim editor actions via RPC.

Exposes Neovim operations (open files, run Lua, diagnostics, quickfix,
notifications) as [Model Context Protocol](https://modelcontextprotocol.io/)
tools, so AI agents can drive your editor — whether spawned directly from
Neovim or orchestrated alongside Neovim in a **Herdr** workspace.

## Installation

Requires [uv](https://docs.astral.sh/uv/) and Python ≥ 3.11.

```sh
uv tool install .
```

This puts `nvim-editor-mcp` on your `PATH`.

## Usage

```sh
# Auto-discover socket (via $NVIM, Herdr topology, or cwd matching)
nvim-editor-mcp

# Explicit socket path
nvim-editor-mcp --socket /tmp/nvim.sock

# Show a Vim message whenever the MCP performs an action
nvim-editor-mcp --notify
# Or via environment variable: NVIM_MCP_NOTIFY=true nvim-editor-mcp
```

The server runs in stdio MCP mode. If no `--socket` is given and `$NVIM` is
unset, the server starts without an active connection and lazily resolves the
target Neovim instance on the first tool call (or via `attach_nvim`).

## Herdr Integration & Workflow

`nvim-editor-mcp` has first-class integration with **Herdr**, enabling
multi-pane workflows where coding agents and Neovim instances run side by side
in organized workspaces and tabs.

### How It Works

When multiple Neovim instances are running across the system, `nvim-editor-mcp`
inspects each discovered socket and queries the active Herdr session
(`$HERDR_SOCKET_PATH`) to collect rich context for every editor instance:

- **Working directory (`cwd`)** and **open buffers** from Neovim.
- **Herdr topology (`pane`, `tab`, `workspace`)** from the instance's
  `HERDR_PANE_ID`, `HERDR_TAB_ID`, and `HERDR_WORKSPACE_ID` environment
  variables, cross-referenced against a live Herdr `session.snapshot` so moved
  panes and human-readable workspace/tab labels stay accurate.

Example output from `list_nvim_instances`:

```text
  [0] /run/user/1000/nvim.12345.0 | cwd: /home/user/app/backend | herdr: [pane w1:p1, tab w1:t1 (api), workspace w1 (app)] | buffers: [src/main.py, tests/test_api.py] [recommended]
  [1] /run/user/1000/nvim.23456.0 | cwd: /home/user/app/frontend | herdr: [pane w1:p3, tab w1:t2 (web), workspace w1 (app)] | buffers: [src/App.tsx]
  [2] /run/user/1000/nvim.34567.0 | cwd: /home/user/other-repo | herdr: [pane w2:p1, tab w2:t1 (main), workspace w2 (other)] | buffers: [README.md]
```

### Instance Selection & Agent Workflow

Agents orchestrated inside a Herdr workspace should interact with a Neovim
instance in the **same Herdr workspace**, preferring instances in the **same
working directory**:

1. **Explicit socket (`--socket` or `$NVIM`)**: Used immediately when provided
   (for example, when launched from inside Neovim via
   [codecompanion.nvim](https://github.com/olimorris/codecompanion.nvim)).
2. **Single running instance**: Automatically attached when only one Neovim
   socket exists on the host.
3. **Automatic workspace & `cwd` matching**: When multiple instances are
   running, `nvim-editor-mcp` compares the agent's Herdr caller context
   (`$HERDR_PANE_ID`, `$HERDR_TAB_ID`, `$HERDR_WORKSPACE_ID`) and working
   directory against all running instances:
   - Scopes candidates to instances in the **same Herdr workspace** when
     running inside Herdr.
   - Prefers an instance in the **same working directory (`cwd`)** (breaking
     ties using the agent's Herdr **tab**).
   - Falls back to an unambiguous instance in the same Herdr **tab**, and then
     the single instance in the same Herdr **workspace**.
4. **Disambiguation via `list_nvim_instances` and `attach_nvim`**: If multiple
   instances remain ambiguous (e.g., two Neovim panes open in different
   subdirectories of the same Herdr workspace when neither matches the agent's
   exact `cwd`), the tool call returns the full instance listing. The agent
   should:
   - Inspect `list_nvim_instances` (which marks `[attached]` or
     `[recommended]` when a match exists).
   - Select an instance in the **same Herdr workspace** (`$HERDR_WORKSPACE_ID`),
     preferring one in the **same working directory** (or closest project
     directory / tab).
   - Call `attach_nvim(socket="/path/to/socket")` to bind the session.

### Tools

| Tool | Description |
| ------- | ------------- |
| `list_nvim_instances` | List running Neovim instances with socket path, `cwd`, open buffers, Herdr pane/tab/workspace info, and `[attached]` / `[recommended]` markers |
| `attach_nvim` | Connect to a Neovim instance by socket path, or auto-attach to the matching instance in the current working directory / Herdr workspace |
| `detach_nvim` | Detach from the current Neovim instance |
| `open_file` | Open a file at a specific line |
| `set_quickfix` | Populate the quickfix list and open it |
| `get_diagnostics` | Fetch LSP diagnostics for a file or all open buffers |
| `nvim_exec_lua` | Execute arbitrary Lua in Neovim and return the result as JSON |
| `notify` | Show a notification message in Neovim |

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
