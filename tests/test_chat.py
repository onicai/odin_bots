"""Tests for odin_bots.cli.chat — Chat command and persona integration."""

from unittest.mock import patch, MagicMock

from typer.testing import CliRunner

import odin_bots.config as cfg
from odin_bots.cli import app
from odin_bots.cli.chat import (
    _block_to_dict,
    _describe_tool_call,
    _generate_startup,
    _get_language_code,
    _format_api_error,
    _run_tool_loop,
    _Spinner,
    _MAX_TOOL_ITERATIONS,
    QUOTE_TOPICS,
)
from odin_bots.persona import Persona

runner = CliRunner()


class TestChatCommand:
    @patch("odin_bots.cli.chat.run_chat")
    def test_explicit_chat_command(self, mock_run_chat):
        result = runner.invoke(app, ["chat"])
        assert result.exit_code == 0
        mock_run_chat.assert_called_once()
        args = mock_run_chat.call_args
        assert args.kwargs["persona_name"] == "iconfucius"

    @patch("odin_bots.cli.chat.run_chat")
    def test_chat_with_persona_flag(self, mock_run_chat):
        result = runner.invoke(app, ["chat", "--persona", "iconfucius"])
        assert result.exit_code == 0
        args = mock_run_chat.call_args
        assert args.kwargs["persona_name"] == "iconfucius"

    @patch("odin_bots.cli.chat.run_chat")
    def test_chat_with_bot_flag(self, mock_run_chat):
        result = runner.invoke(app, ["chat", "--bot", "bot-2"])
        assert result.exit_code == 0
        args = mock_run_chat.call_args
        assert args.kwargs["bot_name"] == "bot-2"

    @patch("odin_bots.cli.chat.run_chat")
    @patch("odin_bots.skills.executor.execute_tool", return_value={
        "status": "ok", "config_exists": True, "wallet_exists": True,
        "env_exists": True, "has_api_key": True, "ready": True,
    })
    def test_bare_invocation_starts_chat(self, mock_exec, mock_run_chat):
        result = runner.invoke(app, [])
        assert result.exit_code == 0
        mock_run_chat.assert_called_once()

    @patch("odin_bots.cli.chat.run_chat")
    @patch("odin_bots.skills.executor.execute_tool", return_value={
        "status": "ok", "config_exists": True, "wallet_exists": True,
        "env_exists": True, "has_api_key": True, "ready": True,
    })
    def test_bare_with_persona_option(self, mock_exec, mock_run_chat):
        result = runner.invoke(app, ["--persona", "iconfucius"])
        assert result.exit_code == 0
        args = mock_run_chat.call_args
        assert args.kwargs["persona_name"] == "iconfucius"


class TestPersonaCommands:
    def test_persona_list(self):
        result = runner.invoke(app, ["persona", "list"])
        assert result.exit_code == 0
        assert "iconfucius" in result.output

    def test_persona_show(self):
        result = runner.invoke(app, ["persona", "show", "iconfucius"])
        assert result.exit_code == 0
        assert "IConfucius" in result.output
        assert "claude" in result.output

    def test_persona_show_not_found(self):
        result = runner.invoke(app, ["persona", "show", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# Startup generation
# ---------------------------------------------------------------------------

def _make_persona(**overrides) -> Persona:
    """Create a test Persona with sensible defaults."""
    defaults = dict(
        name="TestBot",
        description="Test",
        voice="Test voice",
        risk="conservative",
        budget_limit=0,
        bot="bot-1",
        ai_backend="claude",
        ai_model="test-model",
        system_prompt="You are a test bot.",
        greeting_prompt=(
            "Reply with exactly three lines (separate each with a blank line):\n"
            "Line 1: A quote about {topic}. Start with \"{icon} \".\n"
            "Line 2: Welcome the user. One sentence.\n"
            "Line 3: Tell user to type 'exit' to leave. One sentence."
        ),
        goodbye_prompt="Say goodbye in one sentence.",
    )
    defaults.update(overrides)
    return Persona(**defaults)


class TestGenerateStartup:
    def test_returns_greeting_and_goodbye(self):
        """_generate_startup returns a (greeting, goodbye) tuple."""
        mock_backend = MagicMock()
        mock_backend.chat.return_value = (
            "☕️ A wise quote about coffee.\n\n"
            "Welcome to Odin.fun, friend.\n\n"
            "Type 'exit' when your journey is done.\n\n"
            "May your path be ever illuminated."
        )
        persona = _make_persona()
        greeting, goodbye = _generate_startup(mock_backend, persona, "en")
        assert len(greeting) > 0
        assert len(goodbye) > 0
        assert "illuminated" in goodbye

    def test_uses_persona_greeting_prompt_template(self):
        """The greeting prompt template gets {icon} and {topic} filled in."""
        mock_backend = MagicMock()
        mock_backend.chat.return_value = "Line1\n\nLine2\n\nLine3\n\nGoodbye"
        persona = _make_persona(
            greeting_prompt="Say hi about {topic} with {icon}."
        )
        _generate_startup(mock_backend, persona, "en")
        call_args = mock_backend.chat.call_args
        user_msg = call_args[0][0][0]["content"]
        # Placeholders should be replaced with actual values
        assert "{topic}" not in user_msg
        assert "{icon}" not in user_msg

    def test_uses_persona_system_prompt(self):
        """The system prompt passed to the backend is the persona's."""
        mock_backend = MagicMock()
        mock_backend.chat.return_value = "Quote\n\nWelcome\n\nExit\n\nBye"
        persona = _make_persona(system_prompt="Custom system prompt.")
        _generate_startup(mock_backend, persona, "en")
        call_args = mock_backend.chat.call_args
        assert call_args[1]["system"] == "Custom system prompt."

    def test_includes_goodbye_prompt_in_request(self):
        """The goodbye prompt from the persona is included in the API request."""
        mock_backend = MagicMock()
        mock_backend.chat.return_value = "Quote\n\nWelcome\n\nExit\n\nBye"
        persona = _make_persona(goodbye_prompt="Bid farewell warmly.")
        _generate_startup(mock_backend, persona, "en")
        call_args = mock_backend.chat.call_args
        user_msg = call_args[0][0][0]["content"]
        assert "Bid farewell warmly." in user_msg


class TestLanguageDetection:
    def test_english_default(self, monkeypatch):
        monkeypatch.setattr("locale.getdefaultlocale", lambda: ("en_US", "UTF-8"))
        assert _get_language_code() == "en"

    def test_chinese_detected(self, monkeypatch):
        monkeypatch.setattr("locale.getdefaultlocale", lambda: ("zh_CN", "UTF-8"))
        assert _get_language_code() == "cn"

    def test_none_locale_defaults_to_english(self, monkeypatch):
        monkeypatch.setattr("locale.getdefaultlocale", lambda: (None, None))
        assert _get_language_code() == "en"


class TestFormatApiError:
    def test_credit_balance_error(self):
        e = Exception("Your credit balance is too low")
        msg = _format_api_error(e)
        assert "credit" in msg.lower()
        assert "console.anthropic.com" in msg

    def test_auth_error(self):
        e = Exception("Invalid api_key provided")
        msg = _format_api_error(e)
        assert "Authentication" in msg

    def test_rate_limit_error(self):
        e = Exception("rate limit exceeded")
        msg = _format_api_error(e)
        assert "Rate limited" in msg

    def test_overloaded_error(self):
        e = Exception("API is overloaded")
        msg = _format_api_error(e)
        assert "overloaded" in msg.lower()

    def test_generic_error_passthrough(self):
        e = Exception("Something weird happened")
        msg = _format_api_error(e)
        assert "Something weird happened" in msg


class TestQuoteTopics:
    def test_topics_not_empty(self):
        assert len(QUOTE_TOPICS) > 0

    def test_each_topic_has_required_keys(self):
        for entry in QUOTE_TOPICS:
            assert "cn" in entry
            assert "en" in entry
            assert "icon" in entry


class TestSpinner:
    def test_spinner_context_manager(self):
        """Spinner starts and stops without errors."""
        import time
        with _Spinner("testing..."):
            time.sleep(0.1)
        # If we get here, the spinner cleaned up properly


# ---------------------------------------------------------------------------
# Tool use helpers
# ---------------------------------------------------------------------------

class TestDescribeToolCall:
    def test_fund(self):
        desc = _describe_tool_call("fund", {"bot_name": "bot-1", "amount": 5000})
        assert "bot-1" in desc
        assert "5,000" in desc

    def test_trade_buy(self):
        desc = _describe_tool_call(
            "trade_buy",
            {"token_id": "29m8", "amount": 1000, "bot_name": "bot-1"},
        )
        assert "29m8" in desc
        assert "1,000" in desc
        assert "bot-1" in desc

    def test_trade_sell(self):
        desc = _describe_tool_call(
            "trade_sell",
            {"token_id": "29m8", "amount": "all", "bot_name": "bot-1"},
        )
        assert "29m8" in desc
        assert "all" in desc

    def test_withdraw(self):
        desc = _describe_tool_call(
            "withdraw", {"amount": "5000", "bot_name": "bot-1"}
        )
        assert "bot-1" in desc

    def test_wallet_send(self):
        desc = _describe_tool_call(
            "wallet_send", {"amount": "1000", "address": "bc1qtest"}
        )
        assert "bc1qtest" in desc

    def test_unknown_tool_fallback(self):
        desc = _describe_tool_call("something", {"a": 1})
        assert "something" in desc


class TestBlockToDict:
    def test_text_block(self):
        block = MagicMock()
        block.type = "text"
        block.text = "Hello"
        result = _block_to_dict(block)
        assert result == {"type": "text", "text": "Hello"}

    def test_tool_use_block(self):
        block = MagicMock()
        block.type = "tool_use"
        block.id = "id_123"
        block.name = "wallet_balance"
        block.input = {"all_bots": True}
        result = _block_to_dict(block)
        assert result["type"] == "tool_use"
        assert result["id"] == "id_123"
        assert result["name"] == "wallet_balance"
        assert result["input"] == {"all_bots": True}


class TestRunToolLoop:
    def test_text_only_response(self):
        """Text-only response prints and returns."""
        backend = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Here is your answer."
        response = MagicMock()
        response.content = [text_block]
        backend.chat_with_tools.return_value = response

        messages = []
        _run_tool_loop(backend, messages, "system", [], "TestBot")

        # Should have added assistant message
        assert len(messages) == 1
        assert messages[0]["role"] == "assistant"
        assert messages[0]["content"] == "Here is your answer."

    def test_tool_call_then_text(self):
        """Tool call followed by text response."""
        backend = MagicMock()

        # First response: tool call
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "id_1"
        tool_block.name = "persona_list"
        tool_block.input = {}
        resp1 = MagicMock()
        resp1.content = [tool_block]

        # Second response: text only
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Available personas: iconfucius"
        resp2 = MagicMock()
        resp2.content = [text_block]

        backend.chat_with_tools.side_effect = [resp1, resp2]

        messages = []
        _run_tool_loop(backend, messages, "system", [], "TestBot")

        # Should have: assistant (tool_use), user (tool_result), assistant (text)
        assert len(messages) == 3
        assert messages[0]["role"] == "assistant"
        assert messages[1]["role"] == "user"
        assert messages[2]["role"] == "assistant"

    def test_max_iterations_guard(self):
        """Loop stops after MAX_TOOL_ITERATIONS."""
        backend = MagicMock()

        # Always return a tool call
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "id_loop"
        tool_block.name = "persona_list"
        tool_block.input = {}
        response = MagicMock()
        response.content = [tool_block]
        backend.chat_with_tools.return_value = response

        messages = []
        _run_tool_loop(backend, messages, "system", [], "TestBot")

        # Should have called chat_with_tools exactly MAX_TOOL_ITERATIONS times
        assert backend.chat_with_tools.call_count == _MAX_TOOL_ITERATIONS
