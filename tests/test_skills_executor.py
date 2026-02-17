"""Tests for odin_bots.skills.executor — Tool dispatch and execution."""

from unittest.mock import patch

from odin_bots.skills.executor import execute_tool


class TestExecuteToolDispatch:
    def test_unknown_tool_returns_error(self):
        result = execute_tool("nonexistent_tool", {})
        assert result["status"] == "error"
        assert "Unknown tool" in result["error"]

    def test_persona_list_returns_personas(self):
        result = execute_tool("persona_list", {})
        assert result["status"] == "ok"
        assert "personas" in result
        assert "iconfucius" in result["personas"]

    def test_persona_show_returns_details(self):
        result = execute_tool("persona_show", {"name": "iconfucius"})
        assert result["status"] == "ok"
        assert result["name"] == "IConfucius"
        assert result["ai_backend"] == "claude"
        assert result["risk"] == "conservative"

    def test_persona_show_unknown_returns_error(self):
        result = execute_tool("persona_show", {"name": "nonexistent"})
        assert result["status"] == "error"
        assert "not found" in result["error"]

    def test_persona_show_missing_name_returns_error(self):
        result = execute_tool("persona_show", {})
        assert result["status"] == "error"
        assert "required" in result["error"].lower()


class TestTokenLookupExecutor:
    def test_token_lookup_known_token(self):
        """token_lookup should find IConfucius by name."""
        with patch("odin_bots.tokens._search_api", return_value=[]):
            result = execute_tool("token_lookup", {"query": "IConfucius"})
        assert result["status"] == "ok"
        assert result["known_match"] is not None
        assert result["known_match"]["id"] == "29m8"

    def test_token_lookup_missing_query_returns_error(self):
        result = execute_tool("token_lookup", {})
        assert result["status"] == "error"
        assert "required" in result["error"].lower()
