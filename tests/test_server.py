"""Tests for nvim-editor-mcp tools and connection logic."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from nvim_editor_mcp.connection import (
    NvimConnection,
    NvimInstanceInfo,
    find_nvim_sockets,
    select_matching_instance,
)

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

    def test_detach_not_connected(self):
        c = NvimConnection()
        result = c.detach()
        assert "Not attached" in result
        assert not c.is_connected

    @patch("nvim_editor_mcp.connection.pynvim.attach")
    def test_detach_after_attached(self, mock_attach, tmp_path):
        sock = tmp_path / "nvim.sock"
        sock.touch()
        c = NvimConnection()
        c.attach(str(sock))
        assert c.is_connected

        result = c.detach()
        assert "Detached" in result
        assert not c.is_connected
        mock_attach.return_value.close.assert_called_once()

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

    @patch(
        "nvim_editor_mcp.connection.inspect_nvim_instances",
        return_value=[
            NvimInstanceInfo(socket="/tmp/nvim.a/0", cwd="/other/a", buffers=["a.py"], herdr_pane_id="w1:p1"),
            NvimInstanceInfo(socket="/tmp/nvim.b/0", cwd="/other/b", buffers=["b.py"], herdr_pane_id="w2:p1"),
        ],
    )
    @patch("nvim_editor_mcp.connection.select_matching_instance", return_value=None)
    @patch("nvim_editor_mcp.connection.find_nvim_sockets", return_value=["/tmp/nvim.a/0", "/tmp/nvim.b/0"])
    def test_get_multiple_sockets_raises_with_list(self, *_):
        c = NvimConnection()
        with pytest.raises(RuntimeError, match="Multiple Neovim instances") as exc_info:
            c.get()
        msg = str(exc_info.value)
        assert "/other/a" in msg
        assert "w1:p1" in msg
        assert "a.py" in msg

    @patch("nvim_editor_mcp.connection.pynvim.attach")
    @patch(
        "nvim_editor_mcp.connection.inspect_nvim_instances",
        return_value=[
            NvimInstanceInfo(socket="/tmp/nvim.a/0", cwd="/other/a"),
            NvimInstanceInfo(socket="/tmp/nvim.b/0", cwd="/match/cwd"),
        ],
    )
    @patch(
        "nvim_editor_mcp.connection.select_matching_instance",
        return_value=NvimInstanceInfo(socket="/tmp/nvim.b/0", cwd="/match/cwd"),
    )
    @patch("nvim_editor_mcp.connection.find_nvim_sockets", return_value=["/tmp/nvim.a/0", "/tmp/nvim.b/0"])
    def test_get_multiple_sockets_auto_attaches_matching_cwd(self, _find, _sel, _insp, mock_attach):
        c = NvimConnection()
        c.get()
        mock_attach.assert_called_once_with("socket", path="/tmp/nvim.b/0")
        assert c._socket_path == "/tmp/nvim.b/0"


class TestSelectMatchingInstance:
    def test_exact_cwd_match(self, tmp_path):
        d1 = tmp_path / "p1"
        d2 = tmp_path / "p2"
        d1.mkdir()
        d2.mkdir()
        instances = [
            NvimInstanceInfo(socket="/s1", cwd=str(d1)),
            NvimInstanceInfo(socket="/s2", cwd=str(d2)),
        ]
        matched = select_matching_instance(instances, agent_cwd=str(d2), agent_tab_id="", agent_workspace_id="")
        assert matched is not None
        assert matched.socket == "/s2"

    def test_fallback_to_herdr_tab(self, tmp_path):
        d1 = tmp_path / "p1"
        d2 = tmp_path / "p2"
        d3 = tmp_path / "p3"
        for d in (d1, d2, d3):
            d.mkdir()
        instances = [
            NvimInstanceInfo(socket="/s1", cwd=str(d1), herdr_tab_id="w1:t1", herdr_workspace_id="w1"),
            NvimInstanceInfo(socket="/s2", cwd=str(d2), herdr_tab_id="w1:t2", herdr_workspace_id="w1"),
        ]
        matched = select_matching_instance(instances, agent_cwd=str(d3), agent_tab_id="w1:t2", agent_workspace_id="w1")
        assert matched is not None
        assert matched.socket == "/s2"

    def test_fallback_to_herdr_workspace(self, tmp_path):
        d1 = tmp_path / "p1"
        d2 = tmp_path / "p2"
        d3 = tmp_path / "p3"
        for d in (d1, d2, d3):
            d.mkdir()
        instances = [
            NvimInstanceInfo(socket="/s1", cwd=str(d1), herdr_tab_id="w1:t1", herdr_workspace_id="w1"),
            NvimInstanceInfo(socket="/s2", cwd=str(d2), herdr_tab_id="w2:t1", herdr_workspace_id="w2"),
        ]
        matched = select_matching_instance(instances, agent_cwd=str(d3), agent_tab_id="w2:t9", agent_workspace_id="w2")
        assert matched is not None
        assert matched.socket == "/s2"

    def test_tiebreak_multiple_same_cwd_by_herdr_tab(self, tmp_path):
        d1 = tmp_path / "p1"
        d1.mkdir()
        instances = [
            NvimInstanceInfo(socket="/s1", cwd=str(d1), herdr_tab_id="w1:t1", herdr_workspace_id="w1"),
            NvimInstanceInfo(socket="/s2", cwd=str(d1), herdr_tab_id="w1:t2", herdr_workspace_id="w1"),
        ]
        matched = select_matching_instance(instances, agent_cwd=str(d1), agent_tab_id="w1:t2", agent_workspace_id="w1")
        assert matched is not None
        assert matched.socket == "/s2"

    def test_prefers_same_workspace_over_other_workspace_cwd(self, tmp_path):
        d1 = tmp_path / "p1"
        d2 = tmp_path / "p2"
        d1.mkdir()
        d2.mkdir()
        instances = [
            NvimInstanceInfo(socket="/s1", cwd=str(d1), herdr_tab_id="w2:t1", herdr_workspace_id="w2"),
            NvimInstanceInfo(socket="/s2", cwd=str(d2), herdr_tab_id="w1:t1", herdr_workspace_id="w1"),
        ]
        matched = select_matching_instance(instances, agent_cwd=str(d1), agent_tab_id="w1:t2", agent_workspace_id="w1")
        assert matched is not None
        assert matched.socket == "/s2"

    def test_same_workspace_prefers_same_cwd(self, tmp_path):
        d1 = tmp_path / "p1"
        d2 = tmp_path / "p2"
        d1.mkdir()
        d2.mkdir()
        instances = [
            NvimInstanceInfo(socket="/s1", cwd=str(d1), herdr_tab_id="w1:t1", herdr_workspace_id="w1"),
            NvimInstanceInfo(socket="/s2", cwd=str(d2), herdr_tab_id="w1:t2", herdr_workspace_id="w1"),
        ]
        matched = select_matching_instance(instances, agent_cwd=str(d2), agent_tab_id="w1:t1", agent_workspace_id="w1")
        assert matched is not None
        assert matched.socket == "/s2"


class TestFindNvimSockets:
    def test_discovers_xdg_and_tmp_sockets(self, tmp_path, monkeypatch):
        import socket as sock_mod

        xdg = tmp_path / "xdg"
        xdg.mkdir()
        tmp = tmp_path / "tmp"
        nested = tmp / "nvim.user" / "abc123"
        nested.mkdir(parents=True)

        s1_path = xdg / "nvim.12345.0"
        s2_path = nested / "nvim.67890.0"
        not_sock = xdg / "nvim.dir.0"
        not_sock.mkdir()

        s1 = sock_mod.socket(sock_mod.AF_UNIX, sock_mod.SOCK_STREAM)
        s2 = sock_mod.socket(sock_mod.AF_UNIX, sock_mod.SOCK_STREAM)
        try:
            s1.bind(str(s1_path))
            s2.bind(str(s2_path))
            monkeypatch.setenv("XDG_RUNTIME_DIR", str(xdg))
            monkeypatch.setenv("TMPDIR", str(tmp))
            found = find_nvim_sockets()
            assert str(s1_path) in found
            assert str(s2_path) in found
            assert str(not_sock) not in found
        finally:
            s1.close()
            s2.close()


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
        from nvim_editor_mcp.server import QuickfixItem, set_quickfix

        items: list[QuickfixItem] = [{"path": "/a.py", "line": 1, "text": "bad"}]
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


class TestDetachTool:
    def test_detach_calls_conn_detach(self):
        from nvim_editor_mcp.server import detach_nvim

        with patch("nvim_editor_mcp.server.conn") as conn_mock:
            conn_mock.detach.return_value = "Detached from Neovim"
            result = detach_nvim()
            assert result == "Detached from Neovim"
            conn_mock.detach.assert_called_once()


class TestNotifyActions:
    def test_no_notification_by_default(self, nvim_mock):
        from nvim_editor_mcp import server
        from nvim_editor_mcp.server import open_file

        server.notify_actions = False
        nvim_mock.funcs.fnameescape.return_value = "/tmp/foo.py"
        open_file("/tmp/foo.py", line=10)

        # No notify calls should be made since notify_actions is False.
        # exec_lua is only used by notifications when open_file is called.
        nvim_mock.exec_lua.assert_not_called()

    def test_notification_when_enabled(self, nvim_mock):
        from nvim_editor_mcp import server
        from nvim_editor_mcp.server import open_file

        server.notify_actions = True
        nvim_mock.funcs.fnameescape.return_value = "/tmp/foo.py"
        open_file("/tmp/foo.py", line=10)

        # A notify call (via exec_lua) should be made since notify_actions is True.
        nvim_mock.exec_lua.assert_called_once()
        lua_call = nvim_mock.exec_lua.call_args[0][0]
        assert "vim.notify" in lua_call
        assert "MCP Action: open_file" in lua_call

        # Clean up
        server.notify_actions = False
