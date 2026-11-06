"""Neovim connection management with lazy discovery."""

from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass, field
from pathlib import Path

import pynvim

_INSPECT_LUA = """
local bufs = {}
for _, b in ipairs(vim.api.nvim_list_bufs()) do
    if vim.api.nvim_buf_is_loaded(b) and vim.bo[b].buflisted then
        local name = vim.api.nvim_buf_get_name(b)
        if name ~= "" then
            table.insert(bufs, vim.fn.fnamemodify(name, ":~:."))
        end
    end
end
return {
    cwd = vim.fn.getcwd(),
    buffers = bufs,
    herdr_pane_id = vim.env.HERDR_PANE_ID or "",
    herdr_tab_id = vim.env.HERDR_TAB_ID or "",
    herdr_workspace_id = vim.env.HERDR_WORKSPACE_ID or "",
}
"""


@dataclass
class NvimInstanceInfo:
    """Metadata inspected from a live Neovim socket."""

    socket: str
    cwd: str = ""
    buffers: list[str] = field(default_factory=list)
    herdr_pane_id: str = ""
    herdr_tab_id: str = ""
    herdr_workspace_id: str = ""
    herdr_tab_label: str = ""
    herdr_workspace_label: str = ""

    def format_line(self, index: int | None = None) -> str:
        prefix = f"  [{index}] " if index is not None else "- "
        parts = [f"{prefix}{self.socket}"]
        if self.cwd:
            parts.append(f"cwd: {self.cwd}")
        if self.herdr_pane_id:
            ws = (
                f"{self.herdr_workspace_id} ({self.herdr_workspace_label})"
                if self.herdr_workspace_label
                else self.herdr_workspace_id
            )
            tab = f"{self.herdr_tab_id} ({self.herdr_tab_label})" if self.herdr_tab_label else self.herdr_tab_id
            loc = ", ".join(
                x
                for x in (f"pane {self.herdr_pane_id}", f"tab {tab}" if tab else "", f"workspace {ws}" if ws else "")
                if x
            )
            parts.append(f"herdr: [{loc}]")
        if self.buffers:
            shown = ", ".join(self.buffers[:5])
            if len(self.buffers) > 5:
                shown += f" (+{len(self.buffers) - 5} more)"
            parts.append(f"buffers: [{shown}]")
        return " | ".join(parts)


class NvimConnection:
    """Lazy connection to a Neovim instance with auto-discovery."""

    def __init__(self, socket_path: str | None = None) -> None:
        self._socket_path = socket_path
        self._nvim: pynvim.Nvim | None = None

    @property
    def is_connected(self) -> bool:
        if self._nvim is not None and self._socket_path and not Path(self._socket_path).exists():
            self.detach()
        return self._nvim is not None

    def attach(self, socket: str) -> str:
        """Attach to a specific Neovim socket. Returns status message."""
        path = Path(socket)
        if not path.exists():
            return f"Error: socket {socket} does not exist"
        if self._nvim is not None:
            self.detach()
        self._nvim = pynvim.attach("socket", path=str(path))
        self._socket_path = socket
        return f"Attached to Neovim at {socket}"

    def detach(self) -> str:
        """Detach from the Neovim instance."""
        if self._nvim is None and self._socket_path is None:
            return "Not attached to any Neovim instance"

        if self._nvim is not None:
            try:
                self._nvim.close()
            except Exception:  # noqa: BLE001, S110
                pass
            self._nvim = None

        self._socket_path = None
        return "Detached from Neovim"

    def get(self) -> pynvim.Nvim:
        """Return the attached instance, auto-connecting if possible, or raise with discovery info."""
        if self.is_connected and self._nvim is not None:
            return self._nvim

        if self._socket_path:
            self._nvim = pynvim.attach("socket", path=self._socket_path)
            return self._nvim

        sockets = find_nvim_sockets()
        if not sockets:
            msg = "No Neovim instance found. Start Neovim or pass --socket."
            raise RuntimeError(msg)

        if len(sockets) == 1:
            self._nvim = pynvim.attach("socket", path=sockets[0])
            self._socket_path = sockets[0]
            return self._nvim

        instances = inspect_nvim_instances(sockets)
        matched = select_matching_instance(instances)
        if matched is not None:
            self._nvim = pynvim.attach("socket", path=matched.socket)
            self._socket_path = matched.socket
            return self._nvim

        socket_list = "\n".join(inst.format_line(i) for i, inst in enumerate(instances))
        msg = (
            f"Multiple Neovim instances found:\n{socket_list}\n\n"
            "Call the `attach_nvim` tool with the socket path to connect "
            "(when in a Herdr workspace, select an instance in the same workspace, "
            "preferring the same working directory)."
        )
        raise RuntimeError(msg)


def _norm_path(path: str) -> str:
    if not path:
        return ""
    try:
        return str(Path(path).resolve())
    except OSError:
        return path


def _fetch_herdr_snapshot() -> tuple[dict[str, str], dict[str, str], dict[str, tuple[str, str]]]:
    """Query the Herdr Unix socket for workspace labels, tab labels, and live pane locations."""
    sock_path = os.environ.get("HERDR_SOCKET_PATH")
    if not sock_path or not Path(sock_path).exists():
        return {}, {}, {}
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            s.connect(sock_path)
            req = json.dumps({"id": "nvim-mcp:snapshot", "method": "session.snapshot", "params": {}}) + "\n"
            s.sendall(req.encode())
            chunks: list[bytes] = []
            while True:
                data = s.recv(65536)
                if not data:
                    break
                chunks.append(data)
                if b"\n" in data:
                    break
        raw = b"".join(chunks).split(b"\n", 1)[0]
        snap = json.loads(raw).get("result", {}).get("snapshot", {})
        ws_labels = {w["workspace_id"]: w.get("label", "") for w in snap.get("workspaces", []) if "workspace_id" in w}
        tab_labels = {t["tab_id"]: t.get("label", "") for t in snap.get("tabs", []) if "tab_id" in t}
        pane_locs = {
            p["pane_id"]: (str(p.get("tab_id", "")), str(p.get("workspace_id", "")))
            for p in snap.get("panes", [])
            if "pane_id" in p
        }
        return ws_labels, tab_labels, pane_locs
    except Exception:  # noqa: BLE001
        return {}, {}, {}


def inspect_nvim_instances(sockets: list[str] | None = None) -> list[NvimInstanceInfo]:
    """Inspect all discovered Neovim sockets for cwd, open buffers, and Herdr metadata."""
    if sockets is None:
        sockets = find_nvim_sockets()
    ws_labels, tab_labels, pane_locs = _fetch_herdr_snapshot()
    results: list[NvimInstanceInfo] = []
    for sock in sockets:
        try:
            nvim = pynvim.attach("socket", path=sock)
        except Exception:  # noqa: BLE001, S112
            continue
        info = NvimInstanceInfo(socket=sock)
        try:
            data = nvim.exec_lua(_INSPECT_LUA)
            if isinstance(data, dict):
                info.cwd = str(data.get("cwd", ""))
                info.buffers = [str(b) for b in data.get("buffers", [])]
                info.herdr_pane_id = str(data.get("herdr_pane_id", ""))
                live_tab, live_ws = pane_locs.get(info.herdr_pane_id, ("", ""))
                info.herdr_tab_id = live_tab or str(data.get("herdr_tab_id", ""))
                info.herdr_workspace_id = live_ws or str(data.get("herdr_workspace_id", ""))
                info.herdr_tab_label = tab_labels.get(info.herdr_tab_id, "")
                info.herdr_workspace_label = ws_labels.get(info.herdr_workspace_id, "")
        except Exception:  # noqa: BLE001, S110
            pass
        finally:
            try:
                nvim.close()
            except Exception:  # noqa: BLE001, S110
                pass
        results.append(info)
    return results


def select_matching_instance(
    instances: list[NvimInstanceInfo],
    agent_cwd: str | None = None,
    agent_tab_id: str | None = None,
    agent_workspace_id: str | None = None,
) -> NvimInstanceInfo | None:
    """Select an unambiguous Neovim instance matching the agent's Herdr workspace and cwd."""
    target_cwd = _norm_path(agent_cwd if agent_cwd is not None else str(Path.cwd()))
    live_tab, live_ws = "", ""
    agent_pane_id = os.environ.get("HERDR_PANE_ID", "")
    if agent_pane_id and (agent_tab_id is None or agent_workspace_id is None):
        _, _, pane_locs = _fetch_herdr_snapshot()
        live_tab, live_ws = pane_locs.get(agent_pane_id, ("", ""))
    tab_id = agent_tab_id if agent_tab_id is not None else (live_tab or os.environ.get("HERDR_TAB_ID", ""))
    ws_id = (
        agent_workspace_id if agent_workspace_id is not None else (live_ws or os.environ.get("HERDR_WORKSPACE_ID", ""))
    )

    candidates = instances
    if ws_id:
        ws_matches = [i for i in instances if i.herdr_workspace_id == ws_id]
        if ws_matches:
            candidates = ws_matches

    if target_cwd:
        cwd_matches = [i for i in candidates if i.cwd and _norm_path(i.cwd) == target_cwd]
        if len(cwd_matches) == 1:
            return cwd_matches[0]
        if len(cwd_matches) > 1:
            if tab_id:
                tab_cwd = [i for i in cwd_matches if i.herdr_tab_id == tab_id]
                if len(tab_cwd) == 1:
                    return tab_cwd[0]
            return None

    if tab_id:
        tab_matches = [i for i in candidates if i.herdr_tab_id == tab_id]
        if len(tab_matches) == 1:
            return tab_matches[0]
        if len(tab_matches) > 1:
            return None

    if ws_id and len(candidates) == 1 and candidates[0].herdr_workspace_id == ws_id:
        return candidates[0]

    return None


def find_nvim_sockets() -> list[str]:
    """Discover running Neovim instance sockets on the filesystem."""
    candidates: list[str] = []
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    for pattern in ("nvim.*.*", "nvim.*/0", "nvim.*/*/nvim.*.*", "nvim.*/*/0"):
        candidates.extend(str(p) for p in Path(runtime_dir).glob(pattern))

    tmp_dirs = ["/tmp"]  # noqa: S108
    env_tmp = os.environ.get("TMPDIR")
    if env_tmp and env_tmp not in tmp_dirs:
        tmp_dirs.append(env_tmp)
    for d in tmp_dirs:
        for pattern in ("nvim.*/*/nvim.*.*", "nvim.*/*/0", "nvim.*/0", "nvim.*.*"):
            candidates.extend(str(p) for p in Path(d).glob(pattern))

    seen: set[str] = set()
    results: list[str] = []
    for c in candidates:
        p = Path(c)
        try:
            real = str(p.resolve())
            if real not in seen and p.is_socket():
                seen.add(real)
                results.append(c)
        except OSError:
            continue
    return sorted(results)
