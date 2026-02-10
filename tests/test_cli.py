"""Tests for odin_bots.cli — CLI routing, help, init, config commands."""

import os
from dataclasses import dataclass, field
from unittest.mock import patch, MagicMock, call

import pytest
from typer.testing import CliRunner

from odin_bots.cli import app, state, _resolve_bot_names, _print_banner
from odin_bots.cli.balance import BotBalances

runner = CliRunner()


# ---------------------------------------------------------------------------
# Help output
# ---------------------------------------------------------------------------

class TestHelpOutput:
    def test_no_args_shows_help(self):
        result = runner.invoke(app, [])
        # Typer no_args_is_help returns exit code 0
        assert result.exit_code in (0, 2)
        assert "Setup (one time):" in result.output
        assert "odin-bots init" in result.output
        assert "odin-bots wallet create" in result.output
        assert "Step 1." in result.output

    def test_help_flag(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Setup (one time):" in result.output
        assert "How to use your bots:" in result.output

    def test_help_lists_all_commands(self):
        result = runner.invoke(app, ["--help"])
        assert "init" in result.output
        assert "config" in result.output
        assert "balance" in result.output
        assert "fund" in result.output
        assert "withdraw" in result.output
        assert "trade" in result.output
        assert "wallet" in result.output

    def test_no_deposit_command(self):
        result = runner.invoke(app, ["--help"])
        # deposit command should be removed
        lines = result.output.split("\n")
        command_lines = [l for l in lines if l.strip().startswith("deposit")]
        assert len(command_lines) == 0


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

class TestPrintBanner:
    def test_banner_output(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.argv", ["odin-bots", "balance"])
        _print_banner()
        output = capsys.readouterr().out
        assert "$" in output
        assert "odin-bots balance" in output


# ---------------------------------------------------------------------------
# Resolve bot names
# ---------------------------------------------------------------------------

class TestResolveBotNames:
    def test_global_bot(self, odin_project):
        state.bot_name = "bot-2"
        state.all_bots = False
        result = _resolve_bot_names()
        assert result == ["bot-2"]
        state.bot_name = None

    def test_per_command_bot(self, odin_project):
        state.bot_name = None
        state.all_bots = False
        result = _resolve_bot_names(bot="bot-3")
        assert result == ["bot-3"]

    def test_global_all_bots(self, odin_project):
        state.bot_name = None
        state.all_bots = True
        result = _resolve_bot_names()
        assert set(result) == {"bot-1", "bot-2", "bot-3"}
        state.all_bots = False

    def test_per_command_all_bots(self, odin_project):
        state.bot_name = None
        state.all_bots = False
        result = _resolve_bot_names(all_bots=True)
        assert set(result) == {"bot-1", "bot-2", "bot-3"}

    def test_no_flag_exits(self, odin_project):
        from click.exceptions import Exit
        state.bot_name = None
        state.all_bots = False
        with pytest.raises(Exit):
            _resolve_bot_names()


# ---------------------------------------------------------------------------
# Init command
# ---------------------------------------------------------------------------

class TestInitCommand:
    def test_creates_config_and_gitignore(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ODIN_BOTS_ROOT", str(tmp_path))
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert (tmp_path / "odin-bots.toml").exists()
        assert (tmp_path / ".gitignore").exists()
        assert "Created odin-bots.toml" in result.output

    def test_refuses_overwrite_without_force(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ODIN_BOTS_ROOT", str(tmp_path))
        (tmp_path / "odin-bots.toml").write_text("existing")
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_force_overwrites(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ODIN_BOTS_ROOT", str(tmp_path))
        (tmp_path / "odin-bots.toml").write_text("old")
        result = runner.invoke(app, ["init", "--force"])
        assert result.exit_code == 0
        content = (tmp_path / "odin-bots.toml").read_text()
        assert "[bots.bot-1]" in content

    def test_custom_bot_name(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ODIN_BOTS_ROOT", str(tmp_path))
        result = runner.invoke(app, ["init", "--name", "alpha"])
        assert result.exit_code == 0
        content = (tmp_path / "odin-bots.toml").read_text()
        assert "[bots.alpha]" in content


# ---------------------------------------------------------------------------
# Config command
# ---------------------------------------------------------------------------

class TestConfigCommand:
    def test_shows_config(self, odin_project):
        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        assert "bot-1" in result.output
        assert "bot-2" in result.output


# ---------------------------------------------------------------------------
# Command routing (mock run_* functions)
# ---------------------------------------------------------------------------

class TestFundRouting:
    @patch("odin_bots.cli.fund.run_fund")
    def test_fund_requires_bot_flag(self, mock_run_fund, odin_project):
        result = runner.invoke(app, ["fund", "5000"])
        assert result.exit_code == 1
        assert "--bot" in result.output
        assert "--all-bots" in result.output
        mock_run_fund.assert_not_called()

    @patch("odin_bots.cli.fund.run_fund")
    def test_fund_bot_before_command(self, mock_run_fund, odin_project):
        result = runner.invoke(app, ["--bot", "bot-2", "fund", "3000"])
        args = mock_run_fund.call_args
        assert args.kwargs["bot_names"] == ["bot-2"]
        assert args.kwargs["amount"] == 3000

    @patch("odin_bots.cli.fund.run_fund")
    def test_fund_bot_after_command(self, mock_run_fund, odin_project):
        result = runner.invoke(app, ["fund", "3000", "--bot", "bot-2"])
        args = mock_run_fund.call_args
        assert args.kwargs["bot_names"] == ["bot-2"]

    @patch("odin_bots.cli.fund.run_fund")
    def test_fund_all_bots_before_command(self, mock_run_fund, odin_project):
        result = runner.invoke(app, ["--all-bots", "fund", "1000"])
        args = mock_run_fund.call_args
        assert set(args.kwargs["bot_names"]) == {"bot-1", "bot-2", "bot-3"}

    @patch("odin_bots.cli.fund.run_fund")
    def test_fund_all_bots_after_command(self, mock_run_fund, odin_project):
        result = runner.invoke(app, ["fund", "1000", "--all-bots"])
        args = mock_run_fund.call_args
        assert set(args.kwargs["bot_names"]) == {"bot-1", "bot-2", "bot-3"}


class TestWithdrawRouting:
    @patch("odin_bots.cli.withdraw.run_withdraw")
    def test_withdraw_requires_bot_flag(self, mock_run_withdraw, odin_project):
        result = runner.invoke(app, ["withdraw", "1000"])
        assert result.exit_code == 1
        assert "--bot" in result.output
        mock_run_withdraw.assert_not_called()

    @patch("odin_bots.cli.withdraw.run_withdraw")
    def test_withdraw_bot_before_command(self, mock_run_withdraw, odin_project):
        result = runner.invoke(app, ["--bot", "bot-1", "withdraw", "1000"])
        mock_run_withdraw.assert_called_once()
        args = mock_run_withdraw.call_args
        assert args.kwargs["amount"] == "1000"
        assert args.kwargs["bot_name"] == "bot-1"

    @patch("odin_bots.cli.withdraw.run_withdraw")
    def test_withdraw_bot_after_command(self, mock_run_withdraw, odin_project):
        result = runner.invoke(app, ["withdraw", "1000", "--bot", "bot-1"])
        mock_run_withdraw.assert_called_once()
        args = mock_run_withdraw.call_args
        assert args.kwargs["bot_name"] == "bot-1"

    @patch("odin_bots.cli.withdraw.run_withdraw")
    def test_withdraw_all_bots_before_command(self, mock_run_withdraw, odin_project):
        result = runner.invoke(app, ["--all-bots", "withdraw", "all"])
        assert mock_run_withdraw.call_count == 3

    @patch("odin_bots.cli.withdraw.run_withdraw")
    def test_withdraw_all_bots_after_command(self, mock_run_withdraw, odin_project):
        result = runner.invoke(app, ["withdraw", "all", "--all-bots"])
        assert mock_run_withdraw.call_count == 3


class TestTradeRouting:
    @patch("odin_bots.cli.trade.run_trade")
    def test_trade_requires_bot_flag(self, mock_run_trade, odin_project):
        result = runner.invoke(app, ["trade", "buy", "29m8", "1000"])
        assert result.exit_code == 1
        assert "--bot" in result.output
        mock_run_trade.assert_not_called()

    @patch("odin_bots.cli.trade.run_trade")
    def test_trade_bot_before_command(self, mock_run_trade, odin_project):
        result = runner.invoke(app, ["--bot", "bot-1", "trade", "buy", "29m8", "1000"])
        mock_run_trade.assert_called_once()
        args = mock_run_trade.call_args
        assert args.kwargs["action"] == "buy"
        assert args.kwargs["token_id"] == "29m8"
        assert args.kwargs["amount"] == "1000"

    @patch("odin_bots.cli.trade.run_trade")
    def test_trade_bot_after_command(self, mock_run_trade, odin_project):
        result = runner.invoke(app, ["trade", "buy", "29m8", "1000", "--bot", "bot-1"])
        mock_run_trade.assert_called_once()
        args = mock_run_trade.call_args
        assert args.kwargs["bot_name"] == "bot-1"

    @patch("odin_bots.cli.trade.run_trade")
    def test_trade_sell(self, mock_run_trade, odin_project):
        result = runner.invoke(app, ["--bot", "bot-1", "trade", "sell", "29m8", "500"])
        args = mock_run_trade.call_args
        assert args.kwargs["action"] == "sell"


class TestBalanceRouting:
    @patch("odin_bots.cli.balance.run_all_balances")
    def test_balance_requires_bot_flag(self, mock_run, odin_project):
        result = runner.invoke(app, ["balance"])
        assert result.exit_code == 1
        assert "--bot" in result.output
        mock_run.assert_not_called()

    @patch("odin_bots.cli.balance.run_all_balances")
    def test_balance_all_bots_after_command(self, mock_run, odin_project):
        result = runner.invoke(app, ["balance", "--all-bots"])
        mock_run.assert_called_once()
        args = mock_run.call_args
        assert set(args.kwargs["bot_names"]) == {"bot-1", "bot-2", "bot-3"}

    @patch("odin_bots.cli.balance.run_all_balances")
    def test_balance_all_bots_before_command(self, mock_run, odin_project):
        result = runner.invoke(app, ["--all-bots", "balance"])
        mock_run.assert_called_once()
        args = mock_run.call_args
        assert set(args.kwargs["bot_names"]) == {"bot-1", "bot-2", "bot-3"}

    @patch("odin_bots.cli.balance.run_all_balances")
    def test_balance_bot_before_command(self, mock_run, odin_project):
        result = runner.invoke(app, ["--bot", "bot-2", "balance"])
        args = mock_run.call_args
        assert args.kwargs["bot_names"] == ["bot-2"]

    @patch("odin_bots.cli.balance.run_all_balances")
    def test_balance_bot_after_command(self, mock_run, odin_project):
        result = runner.invoke(app, ["balance", "--bot", "bot-2"])
        args = mock_run.call_args
        assert args.kwargs["bot_names"] == ["bot-2"]


# ---------------------------------------------------------------------------
# Sweep command
# ---------------------------------------------------------------------------

class TestSweepRouting:
    @patch("odin_bots.cli.withdraw.run_withdraw")
    @patch("odin_bots.cli.trade.run_trade")
    @patch("odin_bots.cli.balance.collect_balances")
    def test_sweep_requires_bot_flag(self, mock_collect, mock_trade, mock_withdraw,
                                      odin_project):
        result = runner.invoke(app, ["sweep"])
        assert result.exit_code == 1
        assert "--bot" in result.output
        mock_collect.assert_not_called()

    @patch("odin_bots.cli.withdraw.run_withdraw")
    @patch("odin_bots.cli.trade.run_trade")
    @patch("odin_bots.cli.balance.collect_balances")
    def test_sweep_single_bot(self, mock_collect, mock_trade, mock_withdraw,
                               odin_project):
        mock_collect.return_value = BotBalances(
            bot_name="bot-1", bot_principal="principal-1", odin_sats=5000,
            token_holdings=[
                {"ticker": "TEST", "token_id": "29m8", "balance": 1000, "value_sats": 5.0},
                {"ticker": "DOG", "token_id": "2jjj", "balance": 2000, "value_sats": 3.0},
            ],
        )
        result = runner.invoke(app, ["--bot", "bot-1", "sweep"])
        # Should sell both tokens then withdraw
        assert mock_trade.call_count == 2
        assert mock_trade.call_args_list[0] == call(
            bot_name="bot-1", action="sell", token_id="29m8", amount="all",
            verbose=False,
        )
        assert mock_trade.call_args_list[1] == call(
            bot_name="bot-1", action="sell", token_id="2jjj", amount="all",
            verbose=False,
        )
        mock_withdraw.assert_called_once_with(
            bot_name="bot-1", amount="all", verbose=False,
        )

    @patch("odin_bots.cli.withdraw.run_withdraw")
    @patch("odin_bots.cli.trade.run_trade")
    @patch("odin_bots.cli.balance.collect_balances")
    def test_sweep_all_bots(self, mock_collect, mock_trade, mock_withdraw,
                             odin_project):
        mock_collect.side_effect = [
            BotBalances(bot_name="bot-1", bot_principal="p1", odin_sats=5000,
                        token_holdings=[{"ticker": "T", "token_id": "29m8",
                                         "balance": 100, "value_sats": 1.0}]),
            BotBalances(bot_name="bot-2", bot_principal="p2", odin_sats=3000,
                        token_holdings=[]),
            BotBalances(bot_name="bot-3", bot_principal="p3", odin_sats=0,
                        token_holdings=[]),
        ]
        result = runner.invoke(app, ["--all-bots", "sweep"])
        # bot-1 has 1 token, bot-2 and bot-3 have none
        assert mock_trade.call_count == 1
        assert mock_trade.call_args == call(
            bot_name="bot-1", action="sell", token_id="29m8", amount="all",
            verbose=False,
        )
        # All 3 bots should attempt withdraw
        assert mock_withdraw.call_count == 3

    @patch("odin_bots.cli.withdraw.run_withdraw")
    @patch("odin_bots.cli.trade.run_trade")
    @patch("odin_bots.cli.balance.collect_balances")
    def test_sweep_no_holdings(self, mock_collect, mock_trade, mock_withdraw,
                                odin_project):
        mock_collect.return_value = BotBalances(
            bot_name="bot-1", bot_principal="p1", odin_sats=1000,
            token_holdings=[],
        )
        result = runner.invoke(app, ["sweep", "--bot", "bot-1"])
        mock_trade.assert_not_called()
        mock_withdraw.assert_called_once()

    @patch("odin_bots.cli.withdraw.run_withdraw")
    @patch("odin_bots.cli.trade.run_trade")
    @patch("odin_bots.cli.balance.collect_balances")
    def test_sweep_skips_zero_balance_tokens(self, mock_collect, mock_trade,
                                              mock_withdraw, odin_project):
        mock_collect.return_value = BotBalances(
            bot_name="bot-1", bot_principal="p1", odin_sats=1000,
            token_holdings=[
                {"ticker": "T1", "token_id": "aaa", "balance": 500, "value_sats": 1.0},
                {"ticker": "T2", "token_id": "bbb", "balance": 0, "value_sats": 0.0},
            ],
        )
        result = runner.invoke(app, ["sweep", "--bot", "bot-1"])
        # Only T1 sold (T2 has zero balance)
        assert mock_trade.call_count == 1
        assert mock_trade.call_args[1]["token_id"] == "aaa"
