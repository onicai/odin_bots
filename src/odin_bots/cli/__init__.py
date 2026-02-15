"""
odin-bots CLI — Unified command-line interface for Odin.Fun trading
"""

import sys
from pathlib import Path
from typing import Optional

import typer

from odin_bots.config import (
    CONFIG_FILENAME,
    PEM_FILE,
    create_default_config,
    find_config,
    get_bot_names,
    get_cksigner_canister_id,
    get_network,
    load_config,
    set_network,
)

# ---------------------------------------------------------------------------
# Instructions text (shared by --help, no-args, and 'instructions' command)
# ---------------------------------------------------------------------------

# Click's \b marker prevents paragraph rewrapping in --help
HELP_TEXT = """\
Bitcoin rune trading CLI & SDK

\b
Setup (one time):
\b
  odin-bots init             Configures your project with 3 bots
                             Stored in odin-bots.toml
\b
  odin-bots wallet create    Generate wallet identity
                             Stored in .wallet/identity-private.pem
\b
How to use your bots:
  All ckBTC amounts are in sats (1 BTC = 100,000,000 sats).
\b
  Step 1. Fund your odin-bots wallet:
          odin-bots wallet receive
          Send ckBTC or BTC to the address shown.
          BTC deposits require min 10,000 sats and ~6 confirmations.
\b
  Step 2. Check your wallet balance:
          odin-bots wallet balance [--monitor]
\b
  Step 3. Fund your bots (deposits ckBTC into Odin.Fun):
          odin-bots fund <amount> --bot <name>          # in sats
          odin-bots fund <amount> --all-bots
\b
  Step 4. Buy Runes on Odin.Fun:
          odin-bots trade buy <token-id> <amount> --bot <name>   # in sats
          odin-bots trade buy <token-id> <amount> --all-bots
\b
  Step 5. Check your balances (wallet + bots):
          odin-bots wallet balance --all-bots [--monitor]
\b
  Step 6. Sell Runes on Odin.Fun:
          odin-bots trade sell <token-id> <amount> --bot <name>
          odin-bots trade sell <token-id> <amount> --all-bots
          # to sell all holdings of a token
          odin-bots trade sell <token-id> all --bot <name>
          odin-bots trade sell <token-id> all --all-bots
          # to sell all holdings of all tokens
          odin-bots trade sell all-tokens all --bot <name>
          odin-bots trade sell all-tokens all --all-bots
\b
  Step 7. Withdraw ckBTC from Odin.Fun back to wallet:
          odin-bots withdraw <amount> --bot <name>      # in sats
          odin-bots withdraw all --all-bots
\b
  Or use sweep to sell all tokens + withdraw in one command:
          odin-bots sweep --bot <name>
          odin-bots sweep --all-bots
\b
  Step 8. Send ckBTC from wallet to an external ckBTC or BTC account:
          odin-bots wallet send <amount> <address>      # in sats
          (supports both ICRC-1 and BTC addresses)
"""

INSTRUCTIONS_TEXT = """\

============================================================
How to use your bots
============================================================
All ckBTC amounts are in sats (1 BTC = 100,000,000 sats).

  Step 1. Fund your odin-bots wallet:
          odin-bots wallet receive
          Send ckBTC or BTC to the address shown.
          BTC deposits require min 10,000 sats and ~6 confirmations.

  Step 2. Check your wallet balance:
          odin-bots wallet balance [--monitor]

  Step 3. Fund your bots (deposits ckBTC into Odin.Fun):
          odin-bots fund <amount> --bot <bot-name>          # in sats
          odin-bots fund <amount> --all-bots

  Step 4. Buy Runes on Odin.Fun:
          odin-bots trade buy <token-id> <amount> --bot <bot-name>   # in sats
          odin-bots trade buy <token-id> <amount> --all-bots

  Step 5. Check your balances (wallet + bots):
          odin-bots wallet balance --all-bots [--monitor]

  Step 6. Sell Runes on Odin.Fun:
          odin-bots trade sell <token-id> <amount> --bot <bot-name>
          odin-bots trade sell <token-id> <amount> --all-bots
          # to sell all holdings of a token
          odin-bots trade sell <token-id> all --bot <bot-name>
          odin-bots trade sell <token-id> all --all-bots
          # to sell all holdings of all tokens
          odin-bots trade sell all-tokens all --bot <bot-name>
          odin-bots trade sell all-tokens all --all-bots

  Step 7. Withdraw ckBTC from Odin.Fun back to wallet:
          odin-bots withdraw <amount> --bot <bot-name>      # in sats
          odin-bots withdraw all --all-bots

  Or use sweep to sell all tokens + withdraw in one command:
          odin-bots sweep --bot <bot-name>
          odin-bots sweep --all-bots

  Step 8. Send ckBTC from wallet to an external ckBTC or BTC account:
          odin-bots wallet send <amount> <address>          # in sats
          (supports both ICRC-1 and BTC addresses)
"""

app = typer.Typer(
    name="odin-bots",
    help=HELP_TEXT,
    no_args_is_help=True,
)


# Global state
class State:
    bot_name: Optional[str] = None  # None = not specified
    all_bots: bool = False
    verbose: bool = False
    network: str = "prd"


state = State()


def _resolve_bot_names(
    bot: Optional[str] = None, all_bots: bool = False
) -> list[str]:
    """Return list of bot names from --bot or --all-bots flags.

    Merges per-command flags with global state so both placements work:
      odin-bots --all-bots fund 1000
      odin-bots fund 1000 --all-bots

    Exits with an error if neither --bot nor --all-bots is provided.
    """
    if state.all_bots or all_bots:
        return get_bot_names()
    effective_bot = bot or state.bot_name
    if effective_bot is not None:
        return [effective_bot]
    print("Please specify which bot(s) to use:\n")
    print("  --bot <name>    Target a specific bot")
    print("  --all-bots      Target all bots")
    raise typer.Exit(1)


def _resolve_network(network: Optional[str] = None) -> None:
    """Apply per-command --network, merging with global state.

    Allows --network to be placed before or after the subcommand:
      odin-bots --network testing fund 1000 --bot bot-1
      odin-bots fund 1000 --bot bot-1 --network testing
    """
    effective = network or state.network
    set_network(effective)


def _print_banner():
    """Print a command banner for visual separation."""
    cmd = "odin-bots " + " ".join(sys.argv[1:]) if sys.argv[1:] else "odin-bots"
    network = get_network()
    if network != "prd":
        cmd += f"  [network: {network}]"
    inner = f" {cmd} "
    width = max(len(inner) + 2, 55)
    border = "$" * width
    padded = f"${inner:<{width - 2}}$"
    print()
    print(border)
    print(padded)
    print(border)
    print()



def _show_balance_and_instructions(
    bot: Optional[str] = None, all_bots: bool = False
):
    """Show live balances + instructions (used by 'instructions' command)."""
    from odin_bots.cli.balance import run_all_balances

    bot_names = _resolve_bot_names(bot, all_bots)
    run_all_balances(bot_names=bot_names, verbose=state.verbose)
    print(INSTRUCTIONS_TEXT)


@app.callback()
def main_callback(
    ctx: typer.Context,
    bot: Optional[str] = typer.Option(
        None, "--bot", "-b", help="Bot name to use"
    ),
    all_bots: bool = typer.Option(
        False, "--all-bots", help="Target all bots"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show verbose output"
    ),
    network: str = typer.Option(
        "prd", "--network", help="PoAIW network of ckSigner: prd, testing, development"
    ),
):
    """Global options for all commands."""
    state.bot_name = bot  # None when --bot not passed
    state.all_bots = all_bots
    state.verbose = verbose
    state.network = network
    set_network(network)
    if ctx.invoked_subcommand is not None:
        _print_banner()


# ---------------------------------------------------------------------------
# Wallet subcommand group
# ---------------------------------------------------------------------------

from odin_bots.cli.wallet import wallet_app  # noqa: E402

app.add_typer(wallet_app, name="wallet", help="Manage wallet identity and funds")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


GITIGNORE_CONTENT = """\
# odin-bots project
.wallet/
.cache/
"""


@app.command()
def init(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing config"),
):
    """Initialize a new odin-bots project."""
    config_path = Path(CONFIG_FILENAME)

    if config_path.exists() and not force:
        print(f"{CONFIG_FILENAME} already exists. Use --force to overwrite.")
        raise typer.Exit(1)

    # Write .gitignore
    gitignore_path = Path(".gitignore")
    if not gitignore_path.exists() or force:
        gitignore_path.write_text(GITIGNORE_CONTENT)
        print("Created .gitignore")

    # Write config
    config_content = create_default_config()
    config_path.write_text(config_content)
    print(f"Created {CONFIG_FILENAME} with bots: bot-1, bot-2, bot-3")

    print()
    print("Next steps:")
    print("  1. Create your wallet identity:")
    print("     odin-bots wallet create")
    print("  2. Fund your wallet:")
    print("     odin-bots wallet receive")
    print("  3. Check your balance:")
    print("     odin-bots wallet balance")


@app.command()
def config(
    network: Optional[str] = typer.Option(
        None, "--network", help="PoAIW network of ckSigner: prd, testing, development"
    ),
):
    """Show current configuration."""
    _resolve_network(network)
    cfg = load_config()
    config_path = find_config()

    network = get_network()
    print(f"Config file:   {config_path or 'using defaults'}")
    if network != "prd":
        print(f"Network:       {network}")
    print(f"ckSigner ID:   {get_cksigner_canister_id()}")
    print(f"PEM file:      {PEM_FILE}")
    print()
    print("Bots:")
    for name in get_bot_names():
        desc = cfg["bots"][name].get("description", "")
        print(f"  {name}: {desc}")


@app.command()
def instructions(
    bot: Optional[str] = typer.Option(None, "--bot", "-b", help="Bot name to use"),
    all_bots: bool = typer.Option(False, "--all-bots", help="Show all bots"),
    network: Optional[str] = typer.Option(
        None, "--network", help="PoAIW network of ckSigner: prd, testing, development"
    ),
):
    """Show balance and usage instructions."""
    _resolve_network(network)
    _show_balance_and_instructions(bot, all_bots)


@app.command()
def fund(
    amount: int = typer.Argument(..., help="Amount in sats to send to each bot"),
    bot: Optional[str] = typer.Option(None, "--bot", "-b", help="Bot name to use"),
    all_bots: bool = typer.Option(False, "--all-bots", help="Fund all bots"),
    network: Optional[str] = typer.Option(
        None, "--network", help="PoAIW network of ckSigner: prd, testing, development"
    ),
):
    """Fund bot(s) and deposit into Odin.Fun trading accounts."""
    _resolve_network(network)
    from odin_bots.cli.fund import run_fund

    bot_names = _resolve_bot_names(bot, all_bots)
    run_fund(bot_names=bot_names, amount=amount, verbose=state.verbose)


@app.command()
def withdraw(
    amount: str = typer.Argument(
        ..., help="Amount in sats, or 'all' for entire balance"
    ),
    bot: Optional[str] = typer.Option(None, "--bot", "-b", help="Bot name to use"),
    all_bots: bool = typer.Option(False, "--all-bots", help="Withdraw from all bots"),
    network: Optional[str] = typer.Option(
        None, "--network", help="PoAIW network of ckSigner: prd, testing, development"
    ),
):
    """Withdraw from Odin.Fun back to the odin-bots wallet."""
    _resolve_network(network)
    from odin_bots.cli.withdraw import run_withdraw

    bot_names = _resolve_bot_names(bot, all_bots)
    for bot_name in bot_names:
        run_withdraw(bot_name=bot_name, amount=amount, verbose=state.verbose)


@app.command()
def trade(
    action: str = typer.Argument(..., help="Trade action: buy or sell"),
    token_id: str = typer.Argument(..., help="Token ID (e.g., 28k1)"),
    amount: str = typer.Argument(
        ..., help="Amount in sats (buy), tokens (sell), or 'all' (sell entire balance)"
    ),
    bot: Optional[str] = typer.Option(None, "--bot", "-b", help="Bot name to use"),
    all_bots: bool = typer.Option(False, "--all-bots", help="Trade with all bots"),
    network: Optional[str] = typer.Option(
        None, "--network", help="PoAIW network of ckSigner: prd, testing, development"
    ),
):
    """Buy or sell tokens on Odin.Fun."""
    _resolve_network(network)
    from odin_bots.cli.trade import run_trade

    bot_names = _resolve_bot_names(bot, all_bots)

    if token_id == "all-tokens":
        if action != "sell":
            print("Error: 'all-tokens' is only supported for sell, not buy")
            raise typer.Exit(1)
        from odin_bots.cli.balance import collect_balances
        for bot_name in bot_names:
            data = collect_balances(bot_name, verbose=state.verbose)
            if not data.token_holdings:
                print(f"{bot_name}: no token holdings to sell")
                continue
            for holding in data.token_holdings:
                if holding["balance"] > 0:
                    run_trade(
                        bot_name=bot_name, action="sell",
                        token_id=holding["token_id"], amount="all",
                        verbose=state.verbose,
                    )
    else:
        for bot_name in bot_names:
            run_trade(
                bot_name=bot_name, action=action, token_id=token_id,
                amount=amount, verbose=state.verbose,
            )


@app.command()
def sweep(
    bot: Optional[str] = typer.Option(None, "--bot", "-b", help="Bot name to use"),
    all_bots: bool = typer.Option(False, "--all-bots", help="Sweep all bots"),
    network: Optional[str] = typer.Option(
        None, "--network", help="PoAIW network of ckSigner: prd, testing, development"
    ),
):
    """Sell all tokens and withdraw all ckBTC back to the wallet."""
    _resolve_network(network)
    from odin_bots.cli.balance import collect_balances
    from odin_bots.cli.trade import run_trade
    from odin_bots.cli.withdraw import run_withdraw

    bot_names = _resolve_bot_names(bot, all_bots)

    # Phase 1: Sell all tokens for each bot
    for bot_name in bot_names:
        data = collect_balances(bot_name, verbose=state.verbose)
        if not data.token_holdings:
            print(f"{bot_name}: no token holdings to sell")
        else:
            for holding in data.token_holdings:
                if holding["balance"] > 0:
                    run_trade(
                        bot_name=bot_name, action="sell",
                        token_id=holding["token_id"], amount="all",
                        verbose=state.verbose,
                    )

    # Phase 2: Withdraw all ckBTC for each bot
    for bot_name in bot_names:
        run_withdraw(bot_name=bot_name, amount="all", verbose=state.verbose)


def main():
    """Entry point for the CLI."""
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
    app()
