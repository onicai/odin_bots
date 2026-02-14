"""
odin_bots.cli.balance — Check bot balances on ckBTC ledger and odin.fun

Usage:
  odin-bots --bot <name> balance
  odin-bots --all-bots balance
  python -m odin_bots.cli.balance

Uses cached JWT session if available.
Falls back to full SIWB login if no valid session exists.

Checks:
  1. Odin.fun BTC balance via canister getBalance query
  2. Odin.fun balances via REST API
"""

from dataclasses import dataclass, field

import requests
from curl_cffi import requests as cffi_requests
from icp_agent import Agent, Client
from icp_canister import Canister
from icp_identity import Identity
from icp_principal import Principal

from odin_bots.config import (
    CKBTC_LEDGER_CANISTER_ID,
    IC_HOST,
    ODIN_API_URL,
    ODIN_TRADING_CANISTER_ID,
    fmt_sats,
    get_bot_names,
    get_btc_to_usd_rate,
    get_pem_file,
    get_verify_certificates,
    log,
    require_wallet,
    set_verbose,
)
from odin_bots.siwb import siwb_login, load_session, save_session

from odin_bots.candid import ODIN_TRADING_CANDID


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class BotBalances:
    """Structured balance data for a single bot."""
    bot_name: str
    bot_principal: str
    odin_sats: float = 0.0
    token_holdings: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def collect_balances(bot_name: str, token_id: str = "29m8",
                     verbose: bool = False) -> BotBalances:
    """Authenticate and collect all balance data for a single bot.

    Args:
        bot_name: Name of the bot to check balances for.
        token_id: Token ID to check holdings for.
        verbose: If True, print Steps 1-3 debug output.

    Returns:
        BotBalances with all collected data.
    """
    set_verbose(verbose)

    try:
        btc_usd_rate = get_btc_to_usd_rate()
    except Exception:
        btc_usd_rate = None

    # -------------------------------------------------------------------
    # Step 1: Load cached session or SIWB login
    # -------------------------------------------------------------------
    log("=" * 60)
    log(f"Step 1: Authenticate (bot={bot_name})")
    log("=" * 60)
    auth = load_session(bot_name=bot_name, verbose=verbose)
    if not auth:
        log("No valid cached session, performing full SIWB login...")
        auth = siwb_login(bot_name=bot_name, verbose=verbose)
    bot_principal_text = auth["bot_principal_text"]
    jwt_token = auth["jwt_token"]

    # Create anonymous agent for query calls
    client = Client(url=IC_HOST)
    anon_agent = Agent(Identity(anonymous=True), client)

    # -------------------------------------------------------------------
    # Step 2: Odin.Fun trading balance
    # -------------------------------------------------------------------
    log("\n" + "=" * 60)
    log("Step 2: Odin.Fun Trading Balance")
    log("=" * 60)

    odin = Canister(
        agent=anon_agent,
        canister_id=ODIN_TRADING_CANISTER_ID,
        candid_str=ODIN_TRADING_CANDID,
    )

    odin_balance_raw = odin.getBalance(bot_principal_text, "btc", "btc",
                                       verify_certificate=get_verify_certificates())
    if isinstance(odin_balance_raw, list) and len(odin_balance_raw) > 0:
        item = odin_balance_raw[0]
        odin_balance = item["value"] if isinstance(item, dict) and "value" in item else item
    else:
        odin_balance = odin_balance_raw

    odin_sats = odin_balance / 1000 if isinstance(odin_balance, (int, float)) else 0
    log(f"Odin.Fun trading canister ({ODIN_TRADING_CANISTER_ID}):")
    log(f"  Odin.Fun Balance: {fmt_sats(int(odin_sats), btc_usd_rate)}")

    # -------------------------------------------------------------------
    # Step 3: REST API balances -> token holdings
    # -------------------------------------------------------------------
    log("\n" + "=" * 60)
    log("Step 3: REST API Balances")
    log("=" * 60)

    url = f"{ODIN_API_URL}/user/{bot_principal_text}/balances"
    log(f"GET {url}")
    resp = cffi_requests.get(
        url,
        impersonate="chrome",
        headers={
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/json",
        },
    )
    log(f"Status: {resp.status_code}")
    log(f"Response: {resp.text[:1000]}")

    # Parse token holdings
    token_holdings = []
    try:
        api_data = resp.json()
        balances = api_data.get("data", [])
        tokens = [b for b in balances if b.get("type") == "token"]
        for t in tokens:
            ticker = t.get("ticker", t.get("id", "?"))
            token_id = t.get("id", "?")
            balance = t.get("balance", 0)
            divisibility = t.get("divisibility", 8)
            price = t.get("price", 0)
            value_microsats = (balance * price) / (10 ** divisibility)
            value_sats = value_microsats / 1_000_000
            token_holdings.append({
                "ticker": ticker,
                "token_id": token_id,
                "balance": balance,
                "value_sats": value_sats,
            })
    except Exception:
        pass

    return BotBalances(
        bot_name=bot_name,
        bot_principal=bot_principal_text,
        odin_sats=odin_sats,
        token_holdings=token_holdings,
    )


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _fetch_btc_usd_rate() -> float | None:
    """Fetch BTC/USD rate. Returns None on failure."""
    try:
        return get_btc_to_usd_rate()
    except Exception as e:
        print(f"BTC/USD rate: Could not fetch ({e})")
        return None



def _print_padded_table(headers, rows):
    """Print a table with auto-sized columns."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print("-" * (sum(widths) + 2 * (len(widths) - 1)))
    for row in rows:
        print(fmt.format(*row))


def _print_wallet_info(btc_usd_rate: float | None, verbose: bool = False) -> int:
    """Print full wallet info: ckBTC balance, pending BTC, addresses, PEM path.

    Auto-triggers BTC→ckBTC conversion when pending deposits are detected.

    Returns:
        Total wallet sats (ckBTC balance + pending BTC).
    """
    from odin_bots.transfers import (
        check_btc_deposits,
        create_ckbtc_minter,
        create_icrc1_canister,
        get_balance,
        get_btc_address,
        get_pending_btc,
        get_withdrawal_account,
        unwrap_canister_result,
    )

    pem_path = get_pem_file()
    with open(pem_path, "r") as f:
        pem_content = f.read()
    identity = Identity.from_pem(pem_content)
    principal = str(identity.sender())

    client = Client(url=IC_HOST)
    anon_agent = Agent(Identity(anonymous=True), client)

    # ckBTC balance
    icrc1_canister__anon = create_icrc1_canister(anon_agent)
    balance = get_balance(icrc1_canister__anon, principal)
    print()
    print("=" * 60)
    print("Wallet")
    print("=" * 60)
    print(f"\nICRC-1 ckBTC: {fmt_sats(balance, btc_usd_rate)}")

    # ckBTC minter section
    minter_anon = create_ckbtc_minter(anon_agent)
    pending = get_pending_btc(minter_anon, principal)

    withdrawal_balance = 0
    try:
        auth_agent_minter = Agent(identity, client)
        minter_auth = create_ckbtc_minter(auth_agent_minter)
        wa = get_withdrawal_account(minter_auth)
        withdrawal_balance = unwrap_canister_result(
            icrc1_canister__anon.icrc1_balance_of({
                "owner": wa["owner"],
                "subaccount": wa.get("subaccount", []),
            }, verify_certificate=get_verify_certificates())
        )
    except Exception:
        pass

    # BTC withdrawal status tracking
    from odin_bots.cli.wallet import (
        MEMPOOL_TX_URL, MEMPOOL_ADDRESS_URL,
        load_withdrawal_statuses, remove_withdrawal,
    )
    withdrawals = load_withdrawal_statuses()
    active_withdrawals = []
    for ws in withdrawals:
        try:
            auth_agent_status = Agent(identity, client)
            minter_status = create_ckbtc_minter(auth_agent_status)
            status_result = unwrap_canister_result(
                minter_status.retrieve_btc_status_v2(
                    {"block_index": ws["block_index"]},
                    verify_certificate=get_verify_certificates(),
                )
            )
            if isinstance(status_result, dict):
                status_key = next(iter(status_result))
                status_val = status_result[status_key]
                txid_hex = None
                if isinstance(status_val, dict) and "txid" in status_val:
                    txid_hex = status_val["txid"][::-1].hex()
                if status_key == "Confirmed":
                    remove_withdrawal(ws["block_index"])
                else:
                    active_withdrawals.append({
                        **ws, "status": status_key, "txid": txid_hex,
                    })
        except Exception:
            pass

    # Fetch deposit address (needed for mempool check and display)
    btc_address = get_btc_address(minter_anon, principal)

    print()
    print("ckBTC minter:")

    # Query mempool.space for BTC on the deposit address
    address_btc = 0
    try:
        import requests as _requests
        addr_resp = _requests.get(
            f"https://mempool.space/api/address/{btc_address}", timeout=10
        )
        addr_data = addr_resp.json()
        chain = addr_data.get("chain_stats", {})
        mempool = addr_data.get("mempool_stats", {})
        address_btc = (
            chain.get("funded_txo_sum", 0) - chain.get("spent_txo_sum", 0)
            + mempool.get("funded_txo_sum", 0) - mempool.get("spent_txo_sum", 0)
        )
    except Exception:
        pass

    # Incoming BTC (deposits pending conversion to ckBTC)
    # Always call update_balance to discover new deposits
    try:
        result = check_btc_deposits(
            create_ckbtc_minter(Agent(identity, client)), principal
        )
        if isinstance(result, dict) and "Ok" in result:
            minted = result["Ok"]
            if isinstance(minted, list):
                total_minted = sum(u.get("amount", 0) for u in minted)
                print(f"  \u2022 Incoming BTC: converted {fmt_sats(total_minted, btc_usd_rate)} to ckBTC!")
                balance = get_balance(icrc1_canister__anon, principal)
                print(f"    Updated ckBTC balance: {fmt_sats(balance, btc_usd_rate)}")
            else:
                print(f"  \u2022 Incoming BTC: {fmt_sats(pending, btc_usd_rate)}")
        elif isinstance(result, dict) and "Err" in result:
            err = result["Err"]
            if isinstance(err, dict) and "NoNewUtxos" in err:
                nfo = err["NoNewUtxos"]
                required = nfo.get("required_confirmations", "?")
                current = nfo.get("current_confirmations")
                incoming = address_btc if address_btc > 0 else pending
                if current is not None and len(current) > 0:
                    print(f"  \u2022 Incoming BTC: {fmt_sats(incoming, btc_usd_rate)} (waiting for confirmations: {current[0]}/{required})")
                    print(f"    {MEMPOOL_ADDRESS_URL}{btc_address}")
                else:
                    print(f"  \u2022 Incoming BTC: {fmt_sats(incoming, btc_usd_rate)}")
            else:
                print(f"  \u2022 Incoming BTC: {fmt_sats(pending, btc_usd_rate)}")
        else:
            print(f"  \u2022 Incoming BTC: {fmt_sats(pending, btc_usd_rate)}")
    except Exception:
        print(f"  \u2022 Incoming BTC: {fmt_sats(pending, btc_usd_rate)}")

    # Show unconfirmed mempool transactions (not yet seen by minter)
    if pending == 0 and address_btc > 0:
        mempool_unconfirmed = mempool.get("funded_txo_sum", 0)
        if mempool_unconfirmed > 0:
            print(f"    Unconfirmed in mempool: {fmt_sats(mempool_unconfirmed, btc_usd_rate)}")
            print(f"    {MEMPOOL_ADDRESS_URL}{btc_address}")

    # Outgoing BTC (ckBTC in minter account for BTC sends)
    outgoing_line = f"  \u2022 Outgoing BTC: {fmt_sats(withdrawal_balance, btc_usd_rate)}"
    if withdrawal_balance > 0 and not active_withdrawals:
        outgoing_line += " (fee dust — recovered on next send)"
    print(outgoing_line)
    for aw in active_withdrawals:
        amt = aw.get("amount", 0)
        addr = aw.get("btc_address", "?")
        status_line = f"    Sending BTC: {aw['status']}"
        if amt:
            status_line += f" \u2014 {fmt_sats(amt, btc_usd_rate)} to {addr}"
        print(status_line)
        if aw.get("txid"):
            print(f"      Transaction: {MEMPOOL_TX_URL}{aw['txid']}")
            # Fetch confirmation count from mempool.space
            try:
                import requests as _requests
                tx_resp = _requests.get(
                    f"https://mempool.space/api/tx/{aw['txid']}", timeout=10
                )
                tx_data = tx_resp.json().get("status", {})
                if tx_data.get("confirmed"):
                    tip_resp = _requests.get(
                        "https://mempool.space/api/blocks/tip/height", timeout=10
                    )
                    tip_height = tip_resp.json()
                    confs = tip_height - tx_data["block_height"] + 1
                    print(f"      Status: {confs} confirmations")
                else:
                    print("      Status: unconfirmed")
            except Exception:
                pass

    if verbose:
        # Addresses
        print()
        print(f"Wallet principal: {principal}")
        print(f"Wallet BTC deposit address: {btc_address} (min deposit: {fmt_sats(10_000, btc_usd_rate)})")

        print()
        print(f"PEM file: {pem_path}\n")

    return balance, pending, withdrawal_balance


def _print_holdings_table(all_data: list, btc_usd_rate: float | None,
                          wallet_balance_sats: int = 0,
                          wallet_pending_sats: int = 0,
                          wallet_withdrawal_sats: int = 0):
    """Print the Bot Holdings at Odin.Fun table."""
    # Collect all unique token tickers across all bots
    all_tickers = []
    ticker_to_id = {}
    seen = set()
    for d in all_data:
        for t in d.token_holdings:
            if t["ticker"] not in seen:
                all_tickers.append(t["ticker"])
                ticker_to_id[t["ticker"]] = t.get("token_id", "")
                seen.add(t["ticker"])

    token_headers = [
        f"{ticker} ({ticker_to_id[ticker]})" if ticker_to_id.get(ticker) else ticker
        for ticker in all_tickers
    ]
    headers = ["Bot", "ckBTC"] + token_headers
    rows = []
    total_odin_sats = 0
    total_token_balances = {ticker: 0 for ticker in all_tickers}
    total_token_value_sats = {ticker: 0.0 for ticker in all_tickers}

    for d in all_data:
        total_odin_sats += int(d.odin_sats)
        # Build a lookup for this bot's tokens
        token_map = {t["ticker"]: t for t in d.token_holdings}
        row = [
            d.bot_name,
            fmt_sats(int(d.odin_sats), btc_usd_rate),
        ]
        for ticker in all_tickers:
            if ticker in token_map:
                t = token_map[ticker]
                total_token_balances[ticker] += t["balance"]
                total_token_value_sats[ticker] += t.get("value_sats", 0)
                if btc_usd_rate and t.get("value_sats", 0):
                    usd = (t["value_sats"] / 100_000_000) * btc_usd_rate
                    row.append(f"{t['balance']:,} (${usd:.2f})")
                else:
                    row.append(f"{t['balance']:,}")
            else:
                row.append("0")
        rows.append(tuple(row))

    # Totals row
    if len(all_data) > 1:
        total_row = ["TOTAL", fmt_sats(total_odin_sats, btc_usd_rate)]
        total_usd = (total_odin_sats / 100_000_000) * btc_usd_rate if btc_usd_rate else 0
        for ticker in all_tickers:
            bal = total_token_balances[ticker]
            vs = total_token_value_sats[ticker]
            if btc_usd_rate and vs:
                usd = (vs / 100_000_000) * btc_usd_rate
                total_usd += usd
                total_row.append(f"{bal:,} (${usd:.2f})")
            else:
                total_row.append(f"{bal:,}")
        rows.append(tuple(total_row))

    print()
    _print_padded_table(headers, rows)

    if btc_usd_rate:
        wallet_total_sats = wallet_balance_sats + wallet_pending_sats + wallet_withdrawal_sats
        wallet_usd = (wallet_total_sats / 100_000_000) * btc_usd_rate
        total_usd = (total_odin_sats / 100_000_000) * btc_usd_rate + wallet_usd
        for ticker in all_tickers:
            vs = total_token_value_sats[ticker]
            if vs:
                total_usd += (vs / 100_000_000) * btc_usd_rate
        notes = []
        if wallet_pending_sats > 0:
            pending_usd = (wallet_pending_sats / 100_000_000) * btc_usd_rate
            notes.append(f"${pending_usd:,.2f} BTC pending conversion")
        if wallet_withdrawal_sats > 0:
            withdrawal_usd = (wallet_withdrawal_sats / 100_000_000) * btc_usd_rate
            notes.append(f"${withdrawal_usd:,.2f} in BTC withdrawal account")
        note_str = f" (includes {', '.join(notes)})" if notes else ""
        print(f"\nTotal portfolio value: ${total_usd:,.2f}{note_str}")


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def run_wallet_balance():
    """Show wallet info only (no bot login required)."""
    if not require_wallet():
        return
    btc_usd_rate = _fetch_btc_usd_rate()
    _print_wallet_info(btc_usd_rate)


def run_all_balances(bot_names: list, token_id: str = "29m8",
                     verbose: bool = False):
    """Run the balances check for one or more bots with condensed tables.

    Args:
        bot_names: List of bot names to check.
        token_id: Token ID to check holdings for.
        verbose: If True, print Steps 1-3 debug output per bot.
    """
    if not require_wallet():
        return
    btc_usd_rate = _fetch_btc_usd_rate()
    wallet_balance, wallet_pending, wallet_withdrawal = _print_wallet_info(btc_usd_rate)

    print()
    print("=" * 60)
    print("Bot Holdings at Odin.Fun")
    print("=" * 60)

    all_data = []
    for bot_name in bot_names:
        try:
            print(f"Gathering data for bot: {bot_name}...")
            data = collect_balances(bot_name, token_id, verbose=verbose)
            all_data.append(data)
        except Exception as e:
            print(f"  Failed to get balances for bot '{bot_name}': {e}")
    if not all_data:
        return
    _print_holdings_table(all_data, btc_usd_rate, wallet_balance, wallet_pending, wallet_withdrawal)


def main():
    """CLI entry point for standalone usage."""
    run_all_balances(bot_names=get_bot_names())


if __name__ == "__main__":
    main()
