from python.helpers import fd_probe


def test_enabled_flag_parsing(monkeypatch):
    monkeypatch.setenv("A0_FD_PROBE", "1")
    assert fd_probe.enabled() is True

    monkeypatch.setenv("A0_FD_PROBE", "true")
    assert fd_probe.enabled() is True

    monkeypatch.setenv("A0_FD_PROBE", "0")
    assert fd_probe.enabled() is False


def test_classify_target_types():
    assert fd_probe._classify_target("socket:[123]") == "socket"
    assert fd_probe._classify_target("pipe:[123]") == "pipe"
    assert fd_probe._classify_target("/dev/pts/2") == "pty"
    assert fd_probe._classify_target("anon_inode:[eventfd]") == "anon_inode"
    assert fd_probe._classify_target("/tmp/some-file.txt") == "file"
