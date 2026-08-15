import builtins

import pytest

import file_actions


class FakeVersionFile:
    def __init__(self, content):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.content


def _patch_proc_version(monkeypatch, content=None, error=None):
    def fake_open(path, *args, **kwargs):
        if path == "/proc/version":
            if error:
                raise error
            return FakeVersionFile(content)
        return builtins.open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)


def test_is_wsl_false_on_windows(monkeypatch):
    monkeypatch.setattr(file_actions.sys, "platform", "win32")
    assert file_actions._is_wsl() is False


def test_is_wsl_false_on_macos(monkeypatch):
    monkeypatch.setattr(file_actions.sys, "platform", "darwin")
    assert file_actions._is_wsl() is False


def test_is_wsl_true_when_proc_version_mentions_microsoft(monkeypatch):
    monkeypatch.setattr(file_actions.sys, "platform", "linux")
    _patch_proc_version(monkeypatch, content="Linux version 6.6.87.2-microsoft-standard-WSL2")

    assert file_actions._is_wsl() is True


def test_is_wsl_false_on_plain_linux(monkeypatch):
    monkeypatch.setattr(file_actions.sys, "platform", "linux")
    _patch_proc_version(monkeypatch, content="Linux version 6.6.0-generic")

    assert file_actions._is_wsl() is False


def test_is_wsl_false_when_proc_version_missing(monkeypatch):
    monkeypatch.setattr(file_actions.sys, "platform", "linux")
    _patch_proc_version(monkeypatch, error=FileNotFoundError("/proc/version"))

    assert file_actions._is_wsl() is False


def test_is_wsl_false_on_unicode_decode_error(monkeypatch):
    monkeypatch.setattr(file_actions.sys, "platform", "linux")
    _patch_proc_version(
        monkeypatch, error=UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid byte")
    )

    assert file_actions._is_wsl() is False


def test_open_path_windows_uses_startfile(monkeypatch):
    monkeypatch.setattr(file_actions.sys, "platform", "win32")
    calls = []
    monkeypatch.setattr(file_actions.os, "startfile", lambda p: calls.append(p), raising=False)

    file_actions.open_path("C:\\some\\path")

    assert calls == ["C:\\some\\path"]


def test_open_path_macos_uses_open_command(monkeypatch):
    monkeypatch.setattr(file_actions.sys, "platform", "darwin")
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return None

    monkeypatch.setattr(file_actions.subprocess, "run", fake_run)

    file_actions.open_path("/some/path")

    assert calls[0][0] == ["open", "/some/path"]
    assert calls[0][1]["check"] is True
    assert calls[0][1]["timeout"] == file_actions.OPEN_TIMEOUT


def test_open_path_plain_linux_uses_xdg_open(monkeypatch):
    monkeypatch.setattr(file_actions.sys, "platform", "linux")
    monkeypatch.setattr(file_actions, "_is_wsl", lambda: False)
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return None

    monkeypatch.setattr(file_actions.subprocess, "run", fake_run)

    file_actions.open_path("/some/path")

    assert calls[0][0] == ["xdg-open", "/some/path"]
    assert calls[0][1]["check"] is True
    assert calls[0][1]["timeout"] == file_actions.OPEN_TIMEOUT


def test_open_path_wsl_converts_path_and_calls_explorer(monkeypatch):
    monkeypatch.setattr(file_actions.sys, "platform", "linux")
    monkeypatch.setattr(file_actions, "_is_wsl", lambda: True)
    calls = []

    class FakeCompletedProcess:
        stdout = "\\\\wsl.localhost\\Ubuntu\\home\\luke\\output\n"

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        if args[0] == "wslpath":
            return FakeCompletedProcess()
        return None

    monkeypatch.setattr(file_actions.subprocess, "run", fake_run)

    file_actions.open_path("/home/luke/output")

    assert calls[0][0] == ["wslpath", "-w", "/home/luke/output"]
    assert calls[0][1]["check"] is True
    assert calls[0][1]["timeout"] == file_actions.OPEN_TIMEOUT

    assert calls[1][0] == ["explorer.exe", "\\\\wsl.localhost\\Ubuntu\\home\\luke\\output"]
    assert calls[1][1]["check"] is False
    assert calls[1][1]["timeout"] == file_actions.OPEN_TIMEOUT


def test_open_path_wsl_explorer_nonzero_exit_does_not_raise(monkeypatch):
    # explorer.exe is known to exit non-zero even on success; check=False must
    # mean open_path never raises because of that exit code alone.
    monkeypatch.setattr(file_actions.sys, "platform", "linux")
    monkeypatch.setattr(file_actions, "_is_wsl", lambda: True)

    class FakeCompletedProcess:
        stdout = "C:\\Users\\luke\\output\n"

    def fake_run(args, **kwargs):
        if args[0] == "wslpath":
            return FakeCompletedProcess()
        return None

    monkeypatch.setattr(file_actions.subprocess, "run", fake_run)

    file_actions.open_path("/home/luke/output")


def test_open_path_propagates_timeout_expired(monkeypatch):
    monkeypatch.setattr(file_actions.sys, "platform", "linux")
    monkeypatch.setattr(file_actions, "_is_wsl", lambda: False)

    def fake_run(args, **kwargs):
        raise file_actions.subprocess.TimeoutExpired(cmd=args, timeout=kwargs.get("timeout"))

    monkeypatch.setattr(file_actions.subprocess, "run", fake_run)

    with pytest.raises(file_actions.subprocess.TimeoutExpired):
        file_actions.open_path("/some/path")
