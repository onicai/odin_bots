"""Tests for odin_bots.config — verbose/log helpers."""

from odin_bots.config import is_verbose, log, set_verbose


class TestVerboseFlag:
    """Test set_verbose / is_verbose state management."""

    def teardown_method(self):
        # Reset to default after each test
        set_verbose(True)

    def test_default_is_verbose(self):
        set_verbose(True)  # ensure default
        assert is_verbose() is True

    def test_set_verbose_false(self):
        set_verbose(False)
        assert is_verbose() is False

    def test_set_verbose_true(self):
        set_verbose(False)
        set_verbose(True)
        assert is_verbose() is True


class TestLog:
    """Test log() output gated by verbose flag."""

    def teardown_method(self):
        set_verbose(True)

    def test_log_prints_when_verbose(self, capsys):
        set_verbose(True)
        log("hello")
        assert capsys.readouterr().out == "hello\n"

    def test_log_silent_when_not_verbose(self, capsys):
        set_verbose(False)
        log("hello")
        assert capsys.readouterr().out == ""
