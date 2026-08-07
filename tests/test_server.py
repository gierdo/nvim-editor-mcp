"""Tests for nvim-editor-mcp tools and connection logic."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from nvim_editor_mcp.connection import NvimConnection

# --- Connection ---


class TestNvimConnection:
    def test_not_connected_initially(self):
        c = NvimConnection()
        assert not c.is_connected

    def test_attach_nonexistent_socket(self, tmp_path):
        c = NvimConnection()
        result = c.attach(str(tmp_path / "nope"))
        assert "does not exist" in result
        assert not c.is_connected

    @patch("nvim_editor_mcp.connection.pynvim.attach")
    def test_attach_valid_socket(self, mock_attach, tmp_path):
        sock = tmp_path / "nvim.sock"
        sock.touch()
        c = NvimConnection()
        result = c.attach(str(sock))
        assert "Attached" in result
        assert c.is_connected
        mock_attach.assert_called_once_with("socket", path=str(sock))

    @patch("nvim_editor_mcp.connection.pynvim.attach")
    def test_get_with_configured_path(self, mock_attach):
        c = NvimConnection(socket_path="/some/path")
        c.get()
        mock_attach.assert_called_once_with("socket", path="/some/path")

    @patch("nvim_editor_mcp.connection.find_nvim_sockets", return_value=[])
    def test_get_no_sockets_raises(self, _):
        c = NvimConnection()
        with pytest.raises(RuntimeError, match="No Neovim instance found"):
            c.get()

    @patch("nvim_editor_mcp.connection.pynvim.attach")
    @patch("nvim_editor_mcp.connection.find_nvim_sockets", return_value=["/tmp/nvim.abc/0"])
    def test_get_single_socket_auto_attaches(self, _, mock_attach):
        c = NvimConnection()
        c.get()
        mock_attach.assert_called_once_with("socket", path="/tmp/nvim.abc/0")

    @patch("nvim_editor_mcp.connection.find_nvim_sockets", return_value=["/tmp/nvim.a/0", "/tmp/nvim.b/0"])
    def test_get_multiple_sockets_raises_with_list(self, _):
        c = NvimConnection()
        with pytest.raises(RuntimeError, match="Multiple Neovim instances"):
            c.get()


# --- Tools (mock connection) ---


@pytest.fixture
def nvim_mock():
    """Patch the module-level conn with a mock that returns a MagicMock for .get()."""
    mock = MagicMock()
    with patch("nvim_editor_mcp.server.conn") as conn_mock:
        conn_mock.get.return_value = mock
        conn_mock.attach = MagicMock(return_value="Attached to Neovim at /x")
        yield mock


class TestOpenFileTool:
    def test_opens_file(self, nvim_mock):
        from nvim_editor_mcp.server import open_file

        nvim_mock.funcs.fnameescape.return_value = "/tmp/foo.py"
        result = open_file("/tmp/foo.py", line=10)

        nvim_mock.command.assert_called_once_with("edit +10 /tmp/foo.py")
        assert "/tmp/foo.py" in result
        assert "10" in result


class TestSetQuickfixTool:
    def test_sets_quickfix(self, nvim_mock):
        from nvim_editor_mcp.server import set_quickfix

        items = [{"path": "/a.py", "line": 1, "text": "bad"}]
        result = set_quickfix(items, title="Test")

        nvim_mock.funcs.setqflist.assert_called_once()
        call_args = nvim_mock.funcs.setqflist.call_args[0]
        assert call_args[0] == []
        assert call_args[1] == " "
        assert call_args[2]["title"] == "Test"
        assert len(call_args[2]["items"]) == 1
        nvim_mock.command.assert_called_once_with("copen")
        assert "1 items" in result


class TestGetDiagnosticsTool:
    def test_returns_json(self, nvim_mock):
        from nvim_editor_mcp.server import get_diagnostics

        nvim_mock.exec_lua.return_value = [{"path": "/a.py", "line": 1, "message": "err"}]
        result = get_diagnostics()

        assert "/a.py" in result
        nvim_mock.exec_lua.assert_called_once()


class TestNotifyTool:
    def test_notify_info(self, nvim_mock):
        from nvim_editor_mcp.server import notify

        result = notify("hello", level="info")

        nvim_mock.exec_lua.assert_called_once()
        lua_call = nvim_mock.exec_lua.call_args[0][0]
        assert "hello" in lua_call
        assert ", 2)" in lua_call
        assert result == "Notified"

    def test_notify_error(self, nvim_mock):
        from nvim_editor_mcp.server import notify

        notify("boom", level="error")

        lua_call = nvim_mock.exec_lua.call_args[0][0]
        assert ", 4)" in lua_call


class TestNvimExecLuaTool:
    def test_returns_json(self, nvim_mock):
        from nvim_editor_mcp.server import nvim_exec_lua

        nvim_mock.exec_lua.return_value = 42
        result = nvim_exec_lua("return 42")

        assert "42" in result
        nvim_mock.exec_lua.assert_called_once_with("return 42")

    def test_passes_args(self, nvim_mock):
        from nvim_editor_mcp.server import nvim_exec_lua

        nvim_mock.exec_lua.return_value = ["line1"]
        nvim_exec_lua("return vim.api.nvim_buf_get_lines(...)", args=[0])

        nvim_mock.exec_lua.assert_called_once_with("return vim.api.nvim_buf_get_lines(...)", 0)
