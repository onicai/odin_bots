"""Tests for odin_bots.cli.balance — balance collection and display."""

from dataclasses import dataclass
from unittest.mock import MagicMock, patch, call

import pytest

from odin_bots.cli.balance import (
    BotBalances,
    _print_padded_table,
    _print_holdings_table,
    _print_wallet_info,
    collect_balances,
    run_all_balances,
)
from odin_bots.config import fmt_sats


# ---------------------------------------------------------------------------
# fmt_sats
# ---------------------------------------------------------------------------

class TestSatsStr:
    def test_with_usd_rate(self):
        result = fmt_sats(100_000_000, 100_000.0)
        assert "100,000,000 sats" in result
        assert "$100000.00" in result

    def test_without_usd_rate(self):
        result = fmt_sats(5000, None)
        assert result == "5,000 sats"

    def test_zero(self):
        result = fmt_sats(0, 100_000.0)
        assert "0 sats" in result
        assert "$0.00" in result


# ---------------------------------------------------------------------------
# _print_padded_table
# ---------------------------------------------------------------------------

class TestPrintPaddedTable:
    def test_basic_table(self, capsys):
        headers = ["Name", "Value"]
        rows = [("Alice", "100"), ("Bob", "2000")]
        _print_padded_table(headers, rows)
        output = capsys.readouterr().out
        assert "Name" in output
        assert "Value" in output
        assert "Alice" in output
        assert "Bob" in output
        assert "---" in output

    def test_auto_sizes_columns(self, capsys):
        headers = ["A", "B"]
        rows = [("very long cell", "x")]
        _print_padded_table(headers, rows)
        output = capsys.readouterr().out
        assert "very long cell" in output


# ---------------------------------------------------------------------------
# BotBalances dataclass
# ---------------------------------------------------------------------------

class TestBotBalances:
    def test_defaults(self):
        data = BotBalances(bot_name="bot-1", bot_principal="abc")
        assert data.odin_sats == 0.0
        assert data.token_holdings == []

    def test_with_holdings(self):
        holdings = [{"ticker": "ICONFUCIUS", "token_id": "29m8",
                     "balance": 1000, "value_sats": 50}]
        data = BotBalances(bot_name="bot-1", bot_principal="abc",
                           odin_sats=5000.0, token_holdings=holdings)
        assert data.odin_sats == 5000.0
        assert len(data.token_holdings) == 1


# ---------------------------------------------------------------------------
# _print_holdings_table
# ---------------------------------------------------------------------------

class TestPrintHoldingsTable:
    def test_single_bot_no_tokens(self, capsys):
        data = [BotBalances("bot-1", "abc", odin_sats=1000.0)]
        _print_holdings_table(data, btc_usd_rate=100_000.0)
        output = capsys.readouterr().out
        assert "bot-1" in output
        assert "1,000 sats" in output

    def test_single_bot_with_tokens(self, capsys):
        data = [BotBalances("bot-1", "abc", odin_sats=5000.0,
                            token_holdings=[
                                {"ticker": "TEST", "token_id": "t1",
                                 "balance": 500, "value_sats": 100}
                            ])]
        _print_holdings_table(data, btc_usd_rate=100_000.0)
        output = capsys.readouterr().out
        assert "TEST (t1)" in output
        assert "500" in output

    def test_multi_bot_shows_totals(self, capsys):
        data = [
            BotBalances("bot-1", "abc", odin_sats=3000.0,
                        token_holdings=[
                            {"ticker": "X", "token_id": "x1",
                             "balance": 100, "value_sats": 10}
                        ]),
            BotBalances("bot-2", "def", odin_sats=2000.0,
                        token_holdings=[
                            {"ticker": "X", "token_id": "x1",
                             "balance": 200, "value_sats": 20}
                        ]),
        ]
        _print_holdings_table(data, btc_usd_rate=100_000.0)
        output = capsys.readouterr().out
        assert "TOTAL" in output
        assert "5,000 sats" in output
        assert "300" in output
        assert "Total portfolio value:" in output

    def test_no_totals_for_single_bot(self, capsys):
        data = [BotBalances("bot-1", "abc", odin_sats=1000.0)]
        _print_holdings_table(data, btc_usd_rate=100_000.0)
        output = capsys.readouterr().out
        assert "TOTAL" not in output

    def test_no_usd_rate(self, capsys):
        data = [BotBalances("bot-1", "abc", odin_sats=1000.0)]
        _print_holdings_table(data, btc_usd_rate=None)
        output = capsys.readouterr().out
        assert "1,000 sats" in output
        assert "$" not in output


# ---------------------------------------------------------------------------
# _print_wallet_info
# ---------------------------------------------------------------------------

class TestPrintWalletInfo:
    @patch("odin_bots.transfers.unwrap_canister_result", return_value=0)
    @patch("odin_bots.transfers.get_withdrawal_account",
           return_value={"owner": "minter", "subaccount": []})
    @patch("odin_bots.transfers.get_btc_address", return_value="bc1qtest456")
    @patch("odin_bots.transfers.get_pending_btc", return_value=0)
    @patch("odin_bots.transfers.create_ckbtc_minter")
    @patch("odin_bots.transfers.get_balance", return_value=50000)
    @patch("odin_bots.transfers.create_icrc1_canister")
    @patch("odin_bots.cli.balance.Agent")
    @patch("odin_bots.cli.balance.Client")
    @patch("odin_bots.cli.balance.Identity")
    def test_prints_full_info(self, MockId, MockClient, MockAgent,
                               mock_create, mock_get_bal, mock_minter,
                               mock_pending, mock_btc_addr,
                               mock_withdrawal_acct, mock_unwrap,
                               odin_project, capsys):
        mock_identity = MagicMock()
        mock_identity.sender.return_value = MagicMock(
            __str__=lambda s: "ctrl-principal"
        )
        MockId.from_pem.return_value = mock_identity

        _print_wallet_info(100_000.0, verbose=True)
        output = capsys.readouterr().out
        assert "ICRC-1 ckBTC:" in output
        assert "50,000 sats" in output
        assert "Wallet principal:" in output
        assert "bc1qtest456" in output
        assert "PEM file:" in output
        assert "ckBTC minter:" in output
        assert "Incoming BTC:" in output
        assert "Outgoing BTC:" in output
        assert "fee dust" not in output

    @patch("odin_bots.transfers.unwrap_canister_result", return_value=640)
    @patch("odin_bots.transfers.get_withdrawal_account",
           return_value={"owner": "minter", "subaccount": []})
    @patch("odin_bots.transfers.get_btc_address", return_value="bc1qtest456")
    @patch("odin_bots.transfers.get_pending_btc", return_value=0)
    @patch("odin_bots.transfers.create_ckbtc_minter")
    @patch("odin_bots.transfers.get_balance", return_value=50000)
    @patch("odin_bots.transfers.create_icrc1_canister")
    @patch("odin_bots.cli.balance.Agent")
    @patch("odin_bots.cli.balance.Client")
    @patch("odin_bots.cli.balance.Identity")
    def test_shows_dust_note(self, MockId, MockClient, MockAgent,
                              mock_create, mock_get_bal, mock_minter,
                              mock_pending, mock_btc_addr,
                              mock_withdrawal_acct, mock_unwrap,
                              odin_project, capsys):
        mock_identity = MagicMock()
        mock_identity.sender.return_value = MagicMock(
            __str__=lambda s: "ctrl-principal"
        )
        MockId.from_pem.return_value = mock_identity

        _print_wallet_info(100_000.0)
        output = capsys.readouterr().out
        assert "640 sats" in output
        assert "fee dust" in output


# ---------------------------------------------------------------------------
# collect_balances
# ---------------------------------------------------------------------------

class TestCollectBalances:
    @patch("odin_bots.cli.balance.cffi_requests")
    @patch("odin_bots.cli.balance.Canister")
    @patch("odin_bots.cli.balance.Agent")
    @patch("odin_bots.cli.balance.Client")
    @patch("odin_bots.cli.balance.Identity")
    @patch("odin_bots.cli.balance.load_session")
    def test_collects_all_data(self, mock_load, MockId, MockClient,
                               MockAgent, MockCanister, mock_cffi,
                               mock_siwb_auth):
        mock_load.return_value = mock_siwb_auth

        # Mock Odin canister getBalance
        mock_odin = MagicMock()
        mock_odin.getBalance.return_value = [{"value": 5000000}]  # 5000 sats in msat
        MockCanister.return_value = mock_odin

        # Mock REST API
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {"type": "token", "ticker": "TEST", "id": "t1",
                 "balance": 100, "divisibility": 8, "price": 1000000}
            ]
        }
        mock_resp.text = '{"data": []}'
        mock_cffi.get.return_value = mock_resp

        result = collect_balances("bot-1", verbose=False)
        assert isinstance(result, BotBalances)
        assert result.bot_name == "bot-1"
        assert result.odin_sats == 5000.0
        assert len(result.token_holdings) == 1
        assert result.token_holdings[0]["ticker"] == "TEST"

    @patch("odin_bots.cli.balance.cffi_requests")
    @patch("odin_bots.cli.balance.Canister")
    @patch("odin_bots.cli.balance.Agent")
    @patch("odin_bots.cli.balance.Client")
    @patch("odin_bots.cli.balance.Identity")
    @patch("odin_bots.cli.balance.siwb_login")
    @patch("odin_bots.cli.balance.load_session", return_value=None)
    def test_falls_back_to_siwb_login(self, mock_load, mock_login,
                                       MockId, MockClient, MockAgent,
                                       MockCanister, mock_cffi,
                                       mock_siwb_auth):
        mock_login.return_value = mock_siwb_auth
        mock_odin = MagicMock()
        mock_odin.getBalance.return_value = [{"value": 0}]
        MockCanister.return_value = mock_odin
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": []}
        mock_resp.text = '{"data": []}'
        mock_cffi.get.return_value = mock_resp

        result = collect_balances("bot-1", verbose=False)
        mock_login.assert_called_once()


# ---------------------------------------------------------------------------
# run_all_balances
# ---------------------------------------------------------------------------

class TestRunAllBalances:
    def test_no_wallet(self, odin_project_no_wallet, capsys):
        run_all_balances(bot_names=["bot-1"])
        output = capsys.readouterr().out
        assert "No odin-bots wallet found" in output

    @patch("odin_bots.cli.balance._print_holdings_table")
    @patch("odin_bots.cli.balance._print_wallet_info", return_value=(50000, 0, 0, 0, 0))
    @patch("odin_bots.cli.balance.collect_balances")
    @patch("odin_bots.cli.balance._fetch_btc_usd_rate", return_value=100_000.0)
    def test_success(self, mock_rate, mock_collect, mock_wallet,
                     mock_holdings, odin_project):
        mock_collect.return_value = BotBalances("bot-1", "abc", odin_sats=1000.0)
        run_all_balances(bot_names=["bot-1"])
        mock_wallet.assert_called_once()
        mock_holdings.assert_called_once()

    @patch("odin_bots.cli.balance._print_wallet_info", return_value=(50000, 0, 0, 0, 0))
    @patch("odin_bots.cli.balance.collect_balances", side_effect=Exception("fail"))
    @patch("odin_bots.cli.balance._fetch_btc_usd_rate", return_value=100_000.0)
    def test_handles_collection_error(self, mock_rate, mock_collect,
                                       mock_wallet, odin_project, capsys):
        run_all_balances(bot_names=["bot-1"])
        output = capsys.readouterr().out
        assert "Failed to get balances" in output


