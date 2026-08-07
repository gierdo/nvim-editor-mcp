"""MCP server bridging tool calls to Neovim editor actions via RPC.

Usage:
    nvim-editor-mcp --socket /path/to/nvim.socket
    nvim-editor-mcp  (auto-discovers socket via $NVIM env var)
    nvim-editor-mcp  (no socket — starts anyway, discovers on first tool call)

Exposes tools: attach_nvim, open_file, set_quickfix, get_diagnostics, nvim_exec_lua, notify
"""

from __future__ import annotations

import json
from typing import Literal

from fastmcp import FastMCP

from nvim_editor_mcp.connection import NvimConnection

mcp = FastMCP("nvim-editor-mcp")
conn = NvimConnection()


@mcp.tool
def attach_nvim(socket: str) -> str:
    """Attach to a specific Neovim instance by socket path.

    Use this when multiple Neovim instances are running and you need to select one.
    """
    return conn.attach(socket)


@mcp.tool
def open_file(path: str, line: int = 1) -> str:
    """Open a file in Neovim at a specific line."""
    nvim = conn.get()
    nvim.command(f"edit +{line} {nvim.funcs.fnameescape(path)}")
    return f"Opened {path} at line {line}"


@mcp.tool
def set_quickfix(items: list[dict], title: str = "MCP findings") -> str:
    """Populate Neovim's quickfix list with locations and open it."""
    nvim = conn.get()
    qf_items = [{"filename": e["path"], "lnum": e["line"], "col": e.get("col", 1), "text": e["text"]} for e in items]
    nvim.funcs.setqflist([], " ", {"title": title, "items": qf_items})
    nvim.command("copen")
    return f"Quickfix: {title} ({len(qf_items)} items)"


@mcp.tool
def get_diagnostics(
    path: str | None = None,
    severity: Literal["error", "warn", "info", "hint"] = "warn",
) -> str:
    """Get LSP diagnostics from Neovim for a file or all open buffers."""
    min_severity = {"error": 1, "warn": 2, "info": 3, "hint": 4}[severity]
    nvim = conn.get()

    lua_code = f"""
    local diags = vim.diagnostic.get(nil, {{severity = {{min = {min_severity}}}}})
    local results = {{}}
    for _, d in ipairs(diags) do
        local bufname = vim.api.nvim_buf_get_name(d.bufnr)
        if not {json.dumps(path)} or bufname == {json.dumps(path or "")} then
            table.insert(results, {{
                path = bufname,
                line = d.lnum + 1,
                col = d.col + 1,
                severity = d.severity,
                message = d.message,
                source = d.source or "",
            }})
        end
    end
    return results
    """
    return json.dumps(nvim.exec_lua(lua_code), indent=2)


@mcp.tool
def nvim_exec_lua(code: str, args: list | None = None) -> str:
    """Execute arbitrary Lua code in Neovim and return the result as JSON.

    The code should be a Lua expression or block. Use `return` to send a value back.
    Optional positional args are available in Lua as `...` (varargs) or via `select(n, ...)`.

    Examples:
        code="return vim.api.nvim_get_current_buf()"
        code="return vim.api.nvim_buf_get_lines(select(1, ...), 0, -1, false)", args=[0]
        code="vim.api.nvim_set_option_value('number', true, {})"
    """
    result = conn.get().exec_lua(code, *(args or []))
    return json.dumps(result, indent=2, default=str)


@mcp.tool
def notify(
    message: str,
    level: Literal["info", "warn", "error"] = "info",
) -> str:
    """Show a notification message in Neovim."""
    level_map = {"info": 2, "warn": 3, "error": 4}
    conn.get().exec_lua(f"vim.notify({json.dumps(message)}, {level_map[level]})")
    return "Notified"


def main() -> None:
    import argparse
    import os
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(description="MCP server bridging to Neovim")
    parser.add_argument("--socket", required=False, help="Neovim socket path. Falls back to $NVIM env var.")
    cli_args = parser.parse_args()

    socket_arg = cli_args.socket or os.environ.get("NVIM")
    if socket_arg:
        path = Path(socket_arg)
        if not path.exists():
            print(f"Warning: socket {path} does not exist, will discover on first tool call", file=sys.stderr)
        else:
            conn._socket_path = str(path)

    mcp.run()
