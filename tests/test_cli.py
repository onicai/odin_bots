"""Tests for odin_bots.cli — CLI routing, help, init, config commands."""

import os
from dataclasses import dataclass, field
from unittest.mock import patch, MagicMock, call

import pytest
from typer.testing import CliRunner

from odin_bots.cli import app, state, _resolve_bot_names, _print_banner
from odin_bots.cli.balance import BotBalances
from odin_bots.config import get_network, set_network

runner = CliRunner()

# Patch at source modules since wallet.py uses local imports
ID = "icp_identity.Identity"
AG = "icp_agent.Agent"
CL = "icp_agent.Client"
TR = "odin_bots.transfers"


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
    def teardown_method(self):
        set_network("prd")

    def test_banner_output(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.argv", ["odin-bots", "config"])
        _print_banner()
        output = capsys.readouterr().out
        assert "$" in output
        assert "odin-bots config" in output

    def test_banner_hides_prd_network(self, capsys, monkeypatch):
        set_network("prd")
        monkeypatch.setattr("sys.argv", ["odin-bots", "config"])
        _print_banner()
        output = capsys.readouterr().out
        assert "[network:" not in output

    def test_banner_shows_testing_network(self, capsys, monkeypatch):
        set_network("testing")
        monkeypatch.setattr("sys.argv", ["odin-bots", "config"])
        _print_banner()
        output = capsys.readouterr().out
        assert "[network: testing]" in output

    def test_banner_shows_development_network(self, capsys, monkeypatch):
        set_network("development")
        monkeypatch.setattr("sys.argv", ["odin-bots", "config"])
        _print_banner()
        output = capsys.readouterr().out
        assert "[network: development]" in output


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

    def test_creates_three_default_bots(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ODIN_BOTS_ROOT", str(tmp_path))
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        content = (tmp_path / "odin-bots.toml").read_text()
        assert "[bots.bot-1]" in content
        assert "[bots.bot-2]" in content
        assert "[bots.bot-3]" in content


# ---------------------------------------------------------------------------
# Config command
# ---------------------------------------------------------------------------

class TestConfigCommand:
    def teardown_method(self):
        set_network("prd")

    def test_shows_config(self, odin_project):
        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        assert "bot-1" in result.output
        assert "bot-2" in result.output

    def test_prd_hides_network(self, odin_project):
        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        assert "Network:" not in result.output

    def test_prd_shows_prd_canister_id(self, odin_project):
        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        assert "g7qkb-iiaaa-aaaar-qb3za-cai" in result.output

    def test_testing_shows_network(self, odin_project):
        result = runner.invoke(app, ["--network", "testing", "config"])
        assert result.exit_code == 0
        assert "Network:" in result.output
        assert "testing" in result.output

    def test_testing_shows_testing_canister_id(self, odin_project):
        result = runner.invoke(app, ["--network", "testing", "config"])
        assert result.exit_code == 0
        assert "ho2u6-qaaaa-aaaar-qb34q-cai" in result.output

    def test_development_shows_network(self, odin_project):
        result = runner.invoke(app, ["--network", "development", "config"])
        assert result.exit_code == 0
        assert "Network:" in result.output
        assert "development" in result.output


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


# ---------------------------------------------------------------------------
# Network option
# ---------------------------------------------------------------------------

class TestNetworkOption:
    def teardown_method(self):
        set_network("prd")

    def test_default_network_is_prd(self, odin_project):
        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        assert get_network() == "prd"

    def test_network_before_command(self, odin_project):
        result = runner.invoke(app, ["--network", "testing", "config"])
        assert result.exit_code == 0
        assert get_network() == "testing"

    def test_network_after_command(self, odin_project):
        result = runner.invoke(app, ["config", "--network", "testing"])
        assert result.exit_code == 0
        assert "testing" in result.output

    @patch("odin_bots.cli.fund.run_fund")
    def test_network_with_fund(self, mock_run_fund, odin_project):
        result = runner.invoke(app, [
            "--network", "testing", "--bot", "bot-1", "fund", "5000",
        ])
        assert get_network() == "testing"
        mock_run_fund.assert_called_once()

    def test_invalid_network(self, odin_project):
        result = runner.invoke(app, ["--network", "staging", "config"])
        # set_network raises ValueError, Typer catches it
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Option placement flexibility (--network, --bot, --all-bots anywhere)
# ---------------------------------------------------------------------------

class TestOptionPlacement:
    """Verify --network, --bot, and --all-bots work before and after commands."""

    def teardown_method(self):
        set_network("prd")

    # --network placement with config

    def test_network_before_config(self, odin_project):
        result = runner.invoke(app, ["--network", "testing", "config"])
        assert result.exit_code == 0
        assert "ho2u6-qaaaa-aaaar-qb34q-cai" in result.output

    def test_network_after_config(self, odin_project):
        result = runner.invoke(app, ["config", "--network", "testing"])
        assert result.exit_code == 0
        assert "ho2u6-qaaaa-aaaar-qb34q-cai" in result.output

    # --network placement with wallet balance

    @patch("odin_bots.cli.balance.run_all_balances")
    def test_network_before_wallet_balance(self, mock_run, odin_project):
        result = runner.invoke(app, [
            "--network", "testing", "wallet", "balance", "--bot", "bot-1",
        ])
        assert result.exit_code == 0
        assert get_network() == "testing"

    @patch("odin_bots.cli.balance.run_all_balances")
    def test_network_after_wallet_balance(self, mock_run, odin_project):
        result = runner.invoke(app, [
            "wallet", "balance", "--bot", "bot-1", "--network", "testing",
        ])
        assert result.exit_code == 0
        assert get_network() == "testing"

    # --network placement with wallet info

    @patch(f"{TR}.unwrap_canister_result", return_value=0)
    @patch(f"{TR}.get_withdrawal_account",
           return_value={"owner": "minter", "subaccount": []})
    @patch(f"{TR}.get_btc_address", return_value="bc1qtest123")
    @patch(f"{TR}.get_pending_btc", return_value=0)
    @patch(f"{TR}.create_ckbtc_minter")
    @patch(f"{TR}.get_balance", return_value=25000)
    @patch(f"{TR}.create_icrc1_canister")
    @patch(AG)
    @patch(CL)
    @patch(ID)
    def test_network_before_wallet_info(self, MockIdentity, MockClient,
                                         MockAgent, mock_create, mock_get_bal,
                                         mock_minter, mock_pending,
                                         mock_btc_addr, mock_withdrawal_acct,
                                         mock_unwrap, odin_project):
        mock_id = MagicMock()
        mock_id.sender.return_value = MagicMock(
            __str__=lambda s: "test-principal"
        )
        MockIdentity.from_pem.return_value = mock_id
        MockIdentity.return_value = MagicMock()

        result = runner.invoke(app, [
            "--network", "testing", "wallet", "info",
        ])
        assert result.exit_code == 0
        assert get_network() == "testing"

    @patch(f"{TR}.unwrap_canister_result", return_value=0)
    @patch(f"{TR}.get_withdrawal_account",
           return_value={"owner": "minter", "subaccount": []})
    @patch(f"{TR}.get_btc_address", return_value="bc1qtest123")
    @patch(f"{TR}.get_pending_btc", return_value=0)
    @patch(f"{TR}.create_ckbtc_minter")
    @patch(f"{TR}.get_balance", return_value=25000)
    @patch(f"{TR}.create_icrc1_canister")
    @patch(AG)
    @patch(CL)
    @patch(ID)
    def test_network_after_wallet_info(self, MockIdentity, MockClient,
                                        MockAgent, mock_create, mock_get_bal,
                                        mock_minter, mock_pending,
                                        mock_btc_addr, mock_withdrawal_acct,
                                        mock_unwrap, odin_project):
        mock_id = MagicMock()
        mock_id.sender.return_value = MagicMock(
            __str__=lambda s: "test-principal"
        )
        MockIdentity.from_pem.return_value = mock_id
        MockIdentity.return_value = MagicMock()

        result = runner.invoke(app, [
            "wallet", "info", "--network", "testing",
        ])
        assert result.exit_code == 0
        assert get_network() == "testing"

    # --network placement with wallet receive

    @patch("odin_bots.cli.balance.get_btc_to_usd_rate", return_value=100_000.0)
    @patch(f"{TR}.get_balance", return_value=10000)
    @patch(f"{TR}.get_btc_address", return_value="bc1qtestaddr123")
    @patch(f"{TR}.create_icrc1_canister")
    @patch(f"{TR}.create_ckbtc_minter")
    @patch(AG)
    @patch(CL)
    @patch(ID)
    def test_network_before_wallet_receive(self, MockIdentity, MockClient,
                                            MockAgent, mock_minter,
                                            mock_ckbtc, mock_btc_addr,
                                            mock_get_bal, mock_rate,
                                            odin_project):
        mock_id = MagicMock()
        mock_id.sender.return_value = MagicMock(
            __str__=lambda s: "test-principal"
        )
        MockIdentity.from_pem.return_value = mock_id
        MockIdentity.return_value = MagicMock()

        result = runner.invoke(app, [
            "--network", "testing", "wallet", "receive",
        ])
        assert result.exit_code == 0
        assert get_network() == "testing"

    @patch("odin_bots.cli.balance.get_btc_to_usd_rate", return_value=100_000.0)
    @patch(f"{TR}.get_balance", return_value=10000)
    @patch(f"{TR}.get_btc_address", return_value="bc1qtestaddr123")
    @patch(f"{TR}.create_icrc1_canister")
    @patch(f"{TR}.create_ckbtc_minter")
    @patch(AG)
    @patch(CL)
    @patch(ID)
    def test_network_after_wallet_receive(self, MockIdentity, MockClient,
                                           MockAgent, mock_minter,
                                           mock_ckbtc, mock_btc_addr,
                                           mock_get_bal, mock_rate,
                                           odin_project):
        mock_id = MagicMock()
        mock_id.sender.return_value = MagicMock(
            __str__=lambda s: "test-principal"
        )
        MockIdentity.from_pem.return_value = mock_id
        MockIdentity.return_value = MagicMock()

        result = runner.invoke(app, [
            "wallet", "receive", "--network", "testing",
        ])
        assert result.exit_code == 0
        assert get_network() == "testing"

    # --network placement with wallet send

    @patch(f"{TR}.unwrap_canister_result", side_effect=lambda x: x)
    @patch(f"{TR}.transfer", return_value={"Ok": 42})
    @patch(f"{TR}.get_balance")
    @patch(f"{TR}.create_icrc1_canister")
    @patch(AG)
    @patch(CL)
    @patch(ID)
    def test_network_before_wallet_send(self, MockIdentity, MockClient,
                                         MockAgent, mock_create, mock_get_bal,
                                         mock_transfer, mock_unwrap,
                                         odin_project):
        mock_id = MagicMock()
        mock_id.sender.return_value = MagicMock(
            __str__=lambda s: "ctrl-principal"
        )
        MockIdentity.from_pem.return_value = mock_id
        MockIdentity.return_value = MagicMock()
        mock_get_bal.side_effect = [5000, 3990]

        result = runner.invoke(app, [
            "--network", "testing", "wallet", "send", "1000", "dest-principal",
        ])
        assert result.exit_code == 0
        assert get_network() == "testing"

    @patch(f"{TR}.unwrap_canister_result", side_effect=lambda x: x)
    @patch(f"{TR}.transfer", return_value={"Ok": 42})
    @patch(f"{TR}.get_balance")
    @patch(f"{TR}.create_icrc1_canister")
    @patch(AG)
    @patch(CL)
    @patch(ID)
    def test_network_after_wallet_send(self, MockIdentity, MockClient,
                                        MockAgent, mock_create, mock_get_bal,
                                        mock_transfer, mock_unwrap,
                                        odin_project):
        mock_id = MagicMock()
        mock_id.sender.return_value = MagicMock(
            __str__=lambda s: "ctrl-principal"
        )
        MockIdentity.from_pem.return_value = mock_id
        MockIdentity.return_value = MagicMock()
        mock_get_bal.side_effect = [5000, 3990]

        result = runner.invoke(app, [
            "wallet", "send", "1000", "dest-principal", "--network", "testing",
        ])
        assert result.exit_code == 0
        assert get_network() == "testing"

    # --network placement with instructions

    @patch("odin_bots.cli.balance.run_all_balances")
    def test_network_before_instructions(self, mock_run, odin_project):
        result = runner.invoke(app, [
            "--network", "testing", "--bot", "bot-1", "instructions",
        ])
        assert result.exit_code == 0
        assert get_network() == "testing"

    @patch("odin_bots.cli.balance.run_all_balances")
    def test_network_after_instructions(self, mock_run, odin_project):
        result = runner.invoke(app, [
            "instructions", "--bot", "bot-1", "--network", "testing",
        ])
        assert result.exit_code == 0
        assert get_network() == "testing"

    # --network placement with fund

    @patch("odin_bots.cli.fund.run_fund")
    def test_network_before_fund(self, mock_run, odin_project):
        result = runner.invoke(app, [
            "--network", "testing", "--bot", "bot-1", "fund", "5000",
        ])
        assert result.exit_code == 0

    @patch("odin_bots.cli.fund.run_fund")
    def test_network_after_fund(self, mock_run, odin_project):
        result = runner.invoke(app, [
            "--bot", "bot-1", "fund", "5000", "--network", "testing",
        ])
        assert result.exit_code == 0

    # --network placement with withdraw

    @patch("odin_bots.cli.withdraw.run_withdraw")
    def test_network_before_withdraw(self, mock_run, odin_project):
        result = runner.invoke(app, [
            "--network", "testing", "--bot", "bot-1", "withdraw", "1000",
        ])
        assert result.exit_code == 0

    @patch("odin_bots.cli.withdraw.run_withdraw")
    def test_network_after_withdraw(self, mock_run, odin_project):
        result = runner.invoke(app, [
            "--bot", "bot-1", "withdraw", "1000", "--network", "testing",
        ])
        assert result.exit_code == 0

    # --network placement with trade

    @patch("odin_bots.cli.trade.run_trade")
    def test_network_before_trade(self, mock_run, odin_project):
        result = runner.invoke(app, [
            "--network", "testing", "--bot", "bot-1", "trade", "buy", "29m8", "1000",
        ])
        assert result.exit_code == 0

    @patch("odin_bots.cli.trade.run_trade")
    def test_network_after_trade(self, mock_run, odin_project):
        result = runner.invoke(app, [
            "--bot", "bot-1", "trade", "buy", "29m8", "1000", "--network", "testing",
        ])
        assert result.exit_code == 0

    # --network placement with sweep

    @patch("odin_bots.cli.withdraw.run_withdraw")
    @patch("odin_bots.cli.trade.run_trade")
    @patch("odin_bots.cli.balance.collect_balances")
    def test_network_before_sweep(self, mock_collect, mock_trade, mock_withdraw,
                                   odin_project):
        mock_collect.return_value = BotBalances(
            bot_name="bot-1", bot_principal="p1", odin_sats=0, token_holdings=[],
        )
        result = runner.invoke(app, [
            "--network", "testing", "--bot", "bot-1", "sweep",
        ])
        assert result.exit_code == 0

    @patch("odin_bots.cli.withdraw.run_withdraw")
    @patch("odin_bots.cli.trade.run_trade")
    @patch("odin_bots.cli.balance.collect_balances")
    def test_network_after_sweep(self, mock_collect, mock_trade, mock_withdraw,
                                  odin_project):
        mock_collect.return_value = BotBalances(
            bot_name="bot-1", bot_principal="p1", odin_sats=0, token_holdings=[],
        )
        result = runner.invoke(app, [
            "--bot", "bot-1", "sweep", "--network", "testing",
        ])
        assert result.exit_code == 0

    # --bot placement with --network

    @patch("odin_bots.cli.fund.run_fund")
    def test_bot_before_network_before_command(self, mock_run, odin_project):
        result = runner.invoke(app, [
            "--bot", "bot-2", "--network", "testing", "fund", "5000",
        ])
        args = mock_run.call_args
        assert args.kwargs["bot_names"] == ["bot-2"]

    @patch("odin_bots.cli.fund.run_fund")
    def test_network_before_bot_before_command(self, mock_run, odin_project):
        result = runner.invoke(app, [
            "--network", "testing", "--bot", "bot-2", "fund", "5000",
        ])
        args = mock_run.call_args
        assert args.kwargs["bot_names"] == ["bot-2"]

    @patch("odin_bots.cli.fund.run_fund")
    def test_bot_after_command_network_after_command(self, mock_run, odin_project):
        result = runner.invoke(app, [
            "fund", "5000", "--bot", "bot-2", "--network", "testing",
        ])
        assert result.exit_code == 0
        args = mock_run.call_args
        assert args.kwargs["bot_names"] == ["bot-2"]

    # --all-bots placement with --network

    @patch("odin_bots.cli.balance.run_all_balances")
    def test_all_bots_before_network_wallet_balance(self, mock_run, odin_project):
        result = runner.invoke(app, [
            "--all-bots", "wallet", "balance", "--network", "testing",
        ])
        assert result.exit_code == 0
        args = mock_run.call_args
        assert set(args.kwargs["bot_names"]) == {"bot-1", "bot-2", "bot-3"}

    @patch("odin_bots.cli.balance.run_all_balances")
    def test_network_before_all_bots_before_wallet_balance(self, mock_run, odin_project):
        result = runner.invoke(app, [
            "--network", "testing", "--all-bots", "wallet", "balance",
        ])
        assert result.exit_code == 0
        args = mock_run.call_args
        assert set(args.kwargs["bot_names"]) == {"bot-1", "bot-2", "bot-3"}

    @patch("odin_bots.cli.balance.run_all_balances")
    def test_wallet_balance_all_bots_network_at_command(self, mock_run, odin_project):
        result = runner.invoke(app, [
            "wallet", "balance", "--all-bots", "--network", "testing",
        ])
        assert result.exit_code == 0
        args = mock_run.call_args
        assert set(args.kwargs["bot_names"]) == {"bot-1", "bot-2", "bot-3"}
