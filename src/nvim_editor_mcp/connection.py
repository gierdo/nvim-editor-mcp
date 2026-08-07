"""Neovim connection management with lazy discovery."""

from __future__ import annotations

import os
from pathlib import Path

import pynvim


class NvimConnection:
    """Lazy connection to a Neovim instance with auto-discovery."""

    def __init__(self, socket_path: str | None = None) -> None:
        self._socket_path = socket_path
        self._nvim: pynvim.Nvim | None = None

    @property
    def is_connected(self) -> bool:
        return self._nvim is not None

    def attach(self, socket: str) -> str:
        """Attach to a specific Neovim socket. Returns status message."""
        path = Path(socket)
        if not path.exists():
            return f"Error: socket {socket} does not exist"
        self._nvim = pynvim.attach("socket", path=str(path))
        self._socket_path = socket
        return f"Attached to Neovim at {socket}"

    def get(self) -> pynvim.Nvim:
        """Return the attached instance, auto-connecting if possible, or raise with discovery info."""
        if self._nvim is not None:
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
            return self._nvim

        socket_list = "\n".join(f"  [{i}] {s}" for i, s in enumerate(sockets))
        msg = (
            f"Multiple Neovim instances found:\n{socket_list}\n\n"
            "Call the `attach_nvim` tool with the socket path to connect."
        )
        raise RuntimeError(msg)


def find_nvim_sockets() -> list[str]:
    """Discover running Neovim instance sockets on the filesystem."""
    candidates: list[str] = []
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    candidates.extend(str(p) for p in Path(runtime_dir).glob("nvim.*/0"))
    candidates.extend(str(p) for p in Path("/tmp").glob("nvim.*/0"))  # noqa: S108

    seen: set[str] = set()
    results: list[str] = []
    for c in candidates:
        real = str(Path(c).resolve())
        if real not in seen and Path(c).exists():
            seen.add(real)
            results.append(c)
    return sorted(results)
