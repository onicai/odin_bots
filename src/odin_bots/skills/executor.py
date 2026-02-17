"""Tool executor — dispatches tool calls to underlying odin-bots functions.

Each handler captures stdout (since existing functions print their output)
and returns a structured dict.
"""

import io
from contextlib import redirect_stdout


def _capture(fn, *args, **kwargs) -> str:
    """Call fn and capture its stdout output as a string."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        fn(*args, **kwargs)
    return buf.getvalue()


def execute_tool(name: str, args: dict) -> dict:
    """Execute a tool by name with the given arguments.

    Returns:
        {"status": "ok", ...} on success,
        {"status": "error", "error": "message"} on failure.
    """
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"status": "error", "error": f"Unknown tool: {name}"}
    try:
        return handler(args)
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# Read-only handlers
# ---------------------------------------------------------------------------

def _handle_wallet_balance(args: dict) -> dict:
    from odin_bots.config import get_bot_names, require_wallet

    if not require_wallet():
        return {"status": "error", "error": "No wallet found. Run: odin-bots wallet create"}

    bot_name = args.get("bot_name")
    all_bots = args.get("all_bots", False)

    if bot_name:
        from odin_bots.cli.balance import collect_balances, run_wallet_balance
        wallet_output = _capture(run_wallet_balance)
        data = collect_balances(bot_name)
        return {
            "status": "ok",
            "wallet": wallet_output.strip(),
            "bot_name": data.bot_name,
            "bot_principal": data.bot_principal,
            "odin_sats": int(data.odin_sats),
            "token_holdings": data.token_holdings,
        }

    if all_bots:
        from odin_bots.cli.balance import run_all_balances
        bot_names = get_bot_names()
        output = _capture(run_all_balances, bot_names)
        return {"status": "ok", "output": output.strip()}

    # Wallet only (no bot specified)
    from odin_bots.cli.balance import run_wallet_balance
    output = _capture(run_wallet_balance)
    return {"status": "ok", "output": output.strip()}


def _handle_wallet_receive(args: dict) -> dict:
    from odin_bots.config import require_wallet

    if not require_wallet():
        return {"status": "error", "error": "No wallet found. Run: odin-bots wallet create"}

    from icp_agent import Agent, Client
    from icp_identity import Identity

    from odin_bots.config import IC_HOST, fmt_sats, get_btc_to_usd_rate, get_pem_file
    from odin_bots.transfers import (
        create_ckbtc_minter,
        create_icrc1_canister,
        get_balance,
        get_btc_address,
    )

    pem_path = get_pem_file()
    with open(pem_path, "r") as f:
        pem_content = f.read()
    identity = Identity.from_pem(pem_content)
    principal = str(identity.sender())

    client = Client(url=IC_HOST)
    anon_agent = Agent(Identity(anonymous=True), client)
    minter = create_ckbtc_minter(anon_agent)
    btc_address = get_btc_address(minter, principal)

    icrc1 = create_icrc1_canister(anon_agent)
    balance = get_balance(icrc1, principal)

    try:
        rate = get_btc_to_usd_rate()
    except Exception:
        rate = None

    return {
        "status": "ok",
        "wallet_principal": principal,
        "btc_deposit_address": btc_address,
        "ckbtc_balance_sats": balance,
        "balance_display": fmt_sats(balance, rate),
    }


def _handle_wallet_info(args: dict) -> dict:
    from odin_bots.config import require_wallet

    if not require_wallet():
        return {"status": "error", "error": "No wallet found. Run: odin-bots wallet create"}

    from odin_bots.cli.balance import run_wallet_balance
    output = _capture(run_wallet_balance)
    return {"status": "ok", "output": output.strip()}


def _handle_persona_list(args: dict) -> dict:
    from odin_bots.persona import list_personas
    names = list_personas()
    return {"status": "ok", "personas": names}


def _handle_persona_show(args: dict) -> dict:
    from odin_bots.persona import PersonaNotFoundError, load_persona

    name = args.get("name", "")
    if not name:
        return {"status": "error", "error": "Persona name is required."}

    try:
        p = load_persona(name)
    except PersonaNotFoundError:
        return {"status": "error", "error": f"Persona '{name}' not found."}

    return {
        "status": "ok",
        "name": p.name,
        "description": p.description,
        "voice": p.voice,
        "risk": p.risk,
        "budget_limit": p.budget_limit,
        "bot": p.bot,
        "ai_backend": p.ai_backend,
        "ai_model": p.ai_model,
    }


def _handle_token_lookup(args: dict) -> dict:
    from odin_bots.tokens import search_token

    query = args.get("query", "")
    if not query:
        return {"status": "error", "error": "Query is required."}

    result = search_token(query)
    return {
        "status": "ok",
        "query": query,
        "known_match": result["known_match"],
        "search_results": [
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "ticker": r.get("ticker"),
                "bonded": r.get("bonded"),
                "twitter_verified": r.get("twitter_verified"),
                "holder_count": r.get("holder_count"),
                "volume": r.get("volume"),
                "safety": r.get("safety"),
            }
            for r in result["search_results"]
        ],
    }


# ---------------------------------------------------------------------------
# State-changing handlers
# ---------------------------------------------------------------------------

def _handle_fund(args: dict) -> dict:
    from odin_bots.config import require_wallet

    if not require_wallet():
        return {"status": "error", "error": "No wallet found. Run: odin-bots wallet create"}

    amount = args.get("amount")
    bot_name = args.get("bot_name")
    if not amount or not bot_name:
        return {"status": "error", "error": "Both 'amount' and 'bot_name' are required."}

    from odin_bots.cli.fund import run_fund
    output = _capture(run_fund, [bot_name], int(amount))
    return {"status": "ok", "output": output.strip()}


def _handle_trade_buy(args: dict) -> dict:
    from odin_bots.config import require_wallet

    if not require_wallet():
        return {"status": "error", "error": "No wallet found. Run: odin-bots wallet create"}

    token_id = args.get("token_id")
    amount = args.get("amount")
    bot_name = args.get("bot_name")
    if not all([token_id, amount, bot_name]):
        return {"status": "error", "error": "'token_id', 'amount', and 'bot_name' are required."}

    from odin_bots.cli.trade import run_trade
    output = _capture(run_trade, bot_name, "buy", token_id, str(amount))
    return {"status": "ok", "output": output.strip()}


def _handle_trade_sell(args: dict) -> dict:
    from odin_bots.config import require_wallet

    if not require_wallet():
        return {"status": "error", "error": "No wallet found. Run: odin-bots wallet create"}

    token_id = args.get("token_id")
    amount = args.get("amount")
    bot_name = args.get("bot_name")
    if not all([token_id, amount, bot_name]):
        return {"status": "error", "error": "'token_id', 'amount', and 'bot_name' are required."}

    from odin_bots.cli.trade import run_trade
    output = _capture(run_trade, bot_name, "sell", token_id, str(amount))
    return {"status": "ok", "output": output.strip()}


def _handle_withdraw(args: dict) -> dict:
    from odin_bots.config import require_wallet

    if not require_wallet():
        return {"status": "error", "error": "No wallet found. Run: odin-bots wallet create"}

    amount = args.get("amount")
    bot_name = args.get("bot_name")
    if not amount or not bot_name:
        return {"status": "error", "error": "Both 'amount' and 'bot_name' are required."}

    from odin_bots.cli.withdraw import run_withdraw
    output = _capture(run_withdraw, bot_name, str(amount))
    return {"status": "ok", "output": output.strip()}


def _handle_wallet_send(args: dict) -> dict:
    from odin_bots.config import require_wallet

    if not require_wallet():
        return {"status": "error", "error": "No wallet found. Run: odin-bots wallet create"}

    amount = args.get("amount")
    address = args.get("address")
    if not amount or not address:
        return {"status": "error", "error": "Both 'amount' and 'address' are required."}

    # wallet send uses typer.Exit for errors, so we need to catch it
    import typer

    try:
        from odin_bots.cli.wallet import send
        # Invoke via the underlying Click command
        from typer.testing import CliRunner
        from odin_bots.cli.wallet import wallet_app

        runner = CliRunner()
        result = runner.invoke(wallet_app, ["send", str(amount), address])
        if result.exit_code != 0:
            return {"status": "error", "error": result.output.strip()}
        return {"status": "ok", "output": result.output.strip()}
    except typer.Exit:
        return {"status": "error", "error": "Command failed."}


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

_HANDLERS: dict[str, callable] = {
    "wallet_balance": _handle_wallet_balance,
    "wallet_receive": _handle_wallet_receive,
    "wallet_info": _handle_wallet_info,
    "persona_list": _handle_persona_list,
    "persona_show": _handle_persona_show,
    "token_lookup": _handle_token_lookup,
    "fund": _handle_fund,
    "trade_buy": _handle_trade_buy,
    "trade_sell": _handle_trade_sell,
    "withdraw": _handle_withdraw,
    "wallet_send": _handle_wallet_send,
}
