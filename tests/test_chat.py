"""Tests for odin_bots.cli.chat — Chat command and persona integration."""

from unittest.mock import patch, MagicMock

from typer.testing import CliRunner

import odin_bots.config as cfg
from odin_bots.cli import app
from odin_bots.cli.chat import (
    _generate_startup,
    _get_language_code,
    _format_api_error,
    _Spinner,
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
    def test_bare_invocation_starts_chat(self, mock_run_chat):
        result = runner.invoke(app, [])
        assert result.exit_code == 0
        mock_run_chat.assert_called_once()

    @patch("odin_bots.cli.chat.run_chat")
    def test_bare_with_persona_option(self, mock_run_chat):
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
