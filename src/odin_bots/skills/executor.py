"""Tool executor — dispatches tool calls to underlying odin-bots functions.

Each handler captures stdout (since existing functions print their output)
and returns a structured dict.
"""

import io
import os
from contextlib import redirect_stdout
from pathlib import Path


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
# Formatting handlers
# ---------------------------------------------------------------------------

def _handle_fmt_sats(args: dict) -> dict:
    from odin_bots.config import fmt_sats, get_btc_to_usd_rate

    sats = args.get("sats")
    if sats is None:
        return {"status": "error", "error": "'sats' is required."}

    try:
        rate = get_btc_to_usd_rate()
    except Exception:
        rate = None

    return {"status": "ok", "formatted": fmt_sats(int(sats), rate)}


# ---------------------------------------------------------------------------
# Setup handlers
# ---------------------------------------------------------------------------

def _handle_setup_status(args: dict) -> dict:
    from odin_bots.config import find_config, get_pem_file

    config_path = find_config()
    pem_exists = Path(get_pem_file()).exists()
    env_exists = Path(".env").exists()
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    has_api_key = bool(api_key) and api_key != "your-api-key-here"

    return {
        "status": "ok",
        "config_exists": config_path is not None,
        "wallet_exists": pem_exists,
        "env_exists": env_exists,
        "has_api_key": has_api_key,
        "ready": all([config_path is not None, pem_exists, has_api_key]),
    }


def _handle_init(args: dict) -> dict:
    from typer.testing import CliRunner
    from odin_bots.cli import app as cli_app

    cmd = ["init"]
    if args.get("force"):
        cmd.append("--force")
    num_bots = args.get("num_bots")
    if num_bots is not None:
        cmd.extend(["--bots", str(num_bots)])

    runner = CliRunner()
    result = runner.invoke(cli_app, cmd)
    if result.exit_code != 0:
        return {"status": "error", "error": result.output.strip()}

    # Reload config so the rest of the session sees it
    from odin_bots.config import load_config
    load_config(reload=True)

    return {"status": "ok", "display": result.output.strip()}


def _handle_set_bot_count(args: dict) -> dict:
    import re
    from pathlib import Path

    from odin_bots.config import (
        CONFIG_FILENAME,
        add_bots_to_config,
        find_config,
        get_bot_names,
        load_config,
        remove_bots_from_config,
    )

    if not find_config():
        return {"status": "error", "error": "No odin-bots.toml found. Run init first."}

    num_bots = args.get("num_bots")
    if num_bots is None:
        return {"status": "error", "error": "'num_bots' is required."}
    num_bots = max(1, min(1000, int(num_bots)))
    force = args.get("force", False)

    config = load_config(reload=True)
    current_bots = get_bot_names()
    current_count = len(current_bots)

    if num_bots == current_count:
        return {
            "status": "ok",
            "message": f"Already configured with {num_bots} bot(s).",
            "bot_count": num_bots,
        }

    # --- Increasing: add new bots ---
    if num_bots > current_count:
        # Find the highest bot number to continue from
        max_num = 0
        for name in current_bots:
            m = re.search(r'(\d+)$', name)
            if m:
                max_num = max(max_num, int(m.group(1)))
        max_num = max(max_num, current_count)

        added = add_bots_to_config(max_num, max_num + (num_bots - current_count))
        load_config(reload=True)
        return {
            "status": "ok",
            "message": f"Added {len(added)} bot(s). Now at {num_bots}.",
            "bots_added": added,
            "bot_count": num_bots,
        }

    # --- Decreasing: check holdings, then remove ---
    # Sort bots by number, keep lowest, remove highest
    def _sort_key(name):
        m = re.search(r'(\d+)$', name)
        return int(m.group(1)) if m else float('inf')

    sorted_bots = sorted(current_bots, key=_sort_key)
    bots_to_keep = sorted_bots[:num_bots]
    bots_to_remove = sorted_bots[num_bots:]

    if not force:
        # Quick check: only inspect bots that have cached sessions
        # (bots without sessions were never funded)
        cache_dir = Path(".cache")
        bots_to_check = []
        for name in bots_to_remove:
            safe = name.replace("/", "_").replace("\\", "_").replace(" ", "_")
            if (cache_dir / f"session_{safe}.json").exists():
                bots_to_check.append(name)

        if bots_to_check:
            from odin_bots.cli.balance import collect_balances
            from odin_bots.cli.concurrent import run_per_bot

            results = run_per_bot(
                lambda n: collect_balances(n, verbose=False),
                bots_to_check,
            )
            holdings = []
            for bot_name, result in results:
                if isinstance(result, Exception):
                    continue
                if result.odin_sats > 0 or result.token_holdings:
                    holdings.append({
                        "bot_name": result.bot_name,
                        "odin_sats": int(result.odin_sats),
                        "token_holdings": result.token_holdings,
                    })

            if holdings:
                return {
                    "status": "blocked",
                    "reason": "bots_have_holdings",
                    "bots_to_remove": bots_to_remove,
                    "holdings": holdings,
                    "message": (
                        "Some bots have holdings. "
                        "Sweep them first or confirm removal with force=true."
                    ),
                }

    remove_bots_from_config(bots_to_remove)
    load_config(reload=True)
    return {
        "status": "ok",
        "bots_removed": bots_to_remove,
        "message": f"Removed {len(bots_to_remove)} bot(s). Now at {num_bots}.",
        "bot_count": num_bots,
    }


def _handle_wallet_create(args: dict) -> dict:
    from typer.testing import CliRunner
    from odin_bots.cli.wallet import wallet_app

    cmd = ["create"]
    if args.get("force"):
        cmd.append("--force")

    runner = CliRunner()
    result = runner.invoke(wallet_app, cmd)
    if result.exit_code != 0:
        return {"status": "error", "error": result.output.strip()}
    return {"status": "ok", "display": result.output.strip()}


# ---------------------------------------------------------------------------
# Read-only handlers
# ---------------------------------------------------------------------------

def _handle_bot_list(args: dict) -> dict:
    from odin_bots.config import find_config, get_bot_names

    if not find_config():
        return {"status": "error", "error": "No odin-bots.toml found. Run init first."}

    bot_names = get_bot_names()
    names_str = ", ".join(bot_names)
    display = f"{len(bot_names)} bot(s): {names_str}"

    return {
        "status": "ok",
        "display": display,
        "bot_names": bot_names,
        "bot_count": len(bot_names),
    }


def _handle_wallet_balance(args: dict) -> dict:
    from odin_bots.config import get_bot_names, require_wallet

    if not require_wallet():
        return {"status": "error", "error": "No wallet found. Run: odin-bots wallet create"}

    bot_name = args.get("bot_name")
    all_bots = args.get("all_bots", False)
    ckbtc_minter = args.get("ckbtc_minter", False)

    if bot_name:
        from odin_bots.cli.balance import run_all_balances
        output = _capture(run_all_balances, [bot_name],
                          ckbtc_minter=ckbtc_minter)
        return {"status": "ok", "display": output.strip()}

    if all_bots:
        from odin_bots.cli.balance import run_all_balances
        bot_names = get_bot_names()
        output = _capture(run_all_balances, bot_names,
                          ckbtc_minter=ckbtc_minter)
        return {"status": "ok", "display": output.strip()}

    # Wallet only (no bot specified)
    from odin_bots.cli.balance import run_wallet_balance
    output = _capture(run_wallet_balance, ckbtc_minter=ckbtc_minter)
    return {"status": "ok", "display": output.strip()}


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

    balance_str = fmt_sats(balance, rate)
    display = (
        f"Principal:       {principal}\n"
        f"Deposit address: {btc_address}\n"
        f"Balance:         {balance_str}\n"
        f"\n"
        f"To fund your wallet, send ckBTC to the principal or BTC to the deposit address.\n"
        f"BTC deposits require min 10,000 sats and ~6 confirmations."
    )

    return {
        "status": "ok",
        "display": display,
        "wallet_principal": principal,
        "btc_deposit_address": btc_address,
        "ckbtc_balance_sats": balance,
        "balance_display": balance_str,
    }


def _handle_wallet_info(args: dict) -> dict:
    from odin_bots.config import require_wallet

    if not require_wallet():
        return {"status": "error", "error": "No wallet found. Run: odin-bots wallet create"}

    from odin_bots.cli.balance import run_wallet_balance
    output = _capture(run_wallet_balance)
    return {"status": "ok", "display": output.strip()}


def _handle_wallet_monitor(args: dict) -> dict:
    from odin_bots.config import require_wallet

    if not require_wallet():
        return {"status": "error", "error": "No wallet found. Run: odin-bots wallet create"}

    from odin_bots.cli.balance import run_wallet_balance
    output = _capture(run_wallet_balance, ckbtc_minter=True)
    return {"status": "ok", "display": output.strip()}


def _handle_security_status(args: dict) -> dict:
    from odin_bots.config import find_config, get_cache_sessions, load_config

    config_path = find_config()

    # Check blst availability
    try:
        import blst  # noqa: F401
        blst_installed = True
    except (ImportError, ModuleNotFoundError):
        blst_installed = False

    # Check verify_certificates setting
    verify_certs = False
    if config_path:
        config = load_config()
        verify_certs = config.get("settings", {}).get(
            "verify_certificates", False
        )

    # Check session caching setting
    cache_sessions = get_cache_sessions() if config_path else True

    lines = ["Security status:"]
    # blst / certificate verification
    if blst_installed and verify_certs:
        lines.append("  IC certificate verification: enabled (blst installed)")
    elif blst_installed and not verify_certs:
        lines.append(
            "  IC certificate verification: disabled "
            "(blst installed — enable with verify_certificates = true)"
        )
    else:
        lines.append(
            "  IC certificate verification: disabled "
            "(blst not installed — use install_blst to enable)"
        )

    # Session caching
    if cache_sessions:
        lines.append(
            "  Session caching: enabled "
            "(sessions stored in .cache/ with 0600 permissions)"
        )
    else:
        lines.append(
            "  Session caching: disabled (fresh SIWB login every command)"
        )

    # Recommendations
    recs = []
    if not blst_installed:
        recs.append(
            "Install blst for IC certificate verification "
            "(protects balance checks and address lookups)"
        )
    elif not verify_certs:
        recs.append(
            "Enable verify_certificates = true in odin-bots.toml "
            "(blst is already installed)"
        )

    if recs:
        lines.append("")
        lines.append("Recommendations:")
        for r in recs:
            lines.append(f"  - {r}")

    return {
        "status": "ok",
        "display": "\n".join(lines),
        "blst_installed": blst_installed,
        "verify_certificates": verify_certs,
        "cache_sessions": cache_sessions,
    }


def _enable_verify_certificates() -> dict:
    """Enable verify_certificates = true in odin-bots.toml.

    Returns {"enabled_now": True} if it changed the setting,
    {"enabled_now": False} if already enabled or no config found.
    """
    from odin_bots.config import find_config

    config_path = find_config()
    if not config_path:
        return {"enabled_now": False}

    content = Path(config_path).read_text()
    if "verify_certificates = true" in content:
        return {"enabled_now": False}

    if "verify_certificates = false" in content:
        content = content.replace(
            "verify_certificates = false",
            "verify_certificates = true",
        )
    elif "verify_certificates" not in content:
        if "[settings]" in content:
            content = content.replace(
                "[settings]",
                "[settings]\nverify_certificates = true",
            )
        else:
            content += "\n[settings]\nverify_certificates = true\n"
    else:
        return {"enabled_now": False}

    Path(config_path).write_text(content)
    return {"enabled_now": True}


def _handle_install_blst(args: dict) -> dict:
    import platform
    import shutil
    import subprocess
    import tempfile

    # Check if already installed
    blst_already = False
    try:
        import blst  # noqa: F401
        blst_already = True
    except (ImportError, ModuleNotFoundError):
        pass

    if blst_already:
        # Still ensure verify_certificates is enabled in config
        result = _enable_verify_certificates()
        if result["enabled_now"]:
            return {
                "status": "ok",
                "display": (
                    "blst is already installed.\n"
                    "Enabled verify_certificates = true in odin-bots.toml."
                ),
            }
        return {
            "status": "ok",
            "display": (
                "blst is already installed and "
                "verify_certificates is already enabled."
            ),
        }

    # Check prerequisites
    missing = []
    if not shutil.which("git"):
        missing.append("git")
    if not shutil.which("swig"):
        missing.append("swig")

    # Check for C compiler
    has_cc = bool(
        shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    )
    if not has_cc:
        missing.append("C compiler (gcc/clang)")

    if missing:
        system = platform.system()
        lines = [
            f"Missing prerequisites: {', '.join(missing)}",
            "",
            "Install them first:",
        ]
        if system == "Darwin":
            if "C compiler" in " ".join(missing):
                lines.append("  xcode-select --install")
            if "swig" in missing:
                lines.append("  brew install swig")
        else:
            # Linux
            if shutil.which("apt-get"):
                lines.append(
                    "  sudo apt-get install build-essential swig python3-dev"
                )
            elif shutil.which("dnf"):
                lines.append(
                    "  sudo dnf install gcc gcc-c++ make swig python3-devel"
                )
            else:
                lines.append(
                    "  Install: C compiler, make, swig, python3 headers"
                )
        lines.append("")
        lines.append("Then run install_blst again.")
        return {"status": "error", "error": "\n".join(lines)}

    # Build and install blst from source
    blst_version = "v0.3.16"
    blst_commit = "e7f90de551e8df682f3cc99067d204d8b90d27ad"

    blst_dir = tempfile.mkdtemp(prefix="blst_")
    try:
        # Clone
        subprocess.run(
            ["git", "clone", "--branch", blst_version, "--depth", "1",
             "https://github.com/supranational/blst", blst_dir],
            check=True, capture_output=True, text=True,
        )

        # Verify commit hash
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=blst_dir, capture_output=True, text=True, check=True,
        )
        actual_commit = result.stdout.strip()
        if actual_commit != blst_commit:
            return {
                "status": "error",
                "error": (
                    f"Commit mismatch! Expected {blst_commit}, "
                    f"got {actual_commit}. Aborting for safety."
                ),
            }

        # Build Python bindings
        bindings_dir = os.path.join(blst_dir, "bindings", "python")
        env = os.environ.copy()
        if platform.machine().startswith("arm") or platform.machine() == "aarch64":
            env["BLST_PORTABLE"] = "1"
        subprocess.run(
            ["python3", "run.me"],
            cwd=bindings_dir, env=env,
            capture_output=True, text=True,
        )

        # Find install paths
        import sysconfig
        purelib = sysconfig.get_paths()["purelib"]
        platlib = sysconfig.get_paths()["platlib"]

        # Copy built files
        import glob as _glob
        blst_py = os.path.join(bindings_dir, "blst.py")
        if not os.path.exists(blst_py):
            return {
                "status": "error",
                "error": "Build failed — blst.py not found after build.",
            }
        shutil.copy2(blst_py, purelib)

        so_files = _glob.glob(os.path.join(bindings_dir, "_blst*.so"))
        if not so_files:
            return {
                "status": "error",
                "error": "Build failed — _blst*.so not found after build.",
            }
        for so in so_files:
            shutil.copy2(so, platlib)

    finally:
        shutil.rmtree(blst_dir, ignore_errors=True)

    # Verify installation
    try:
        # Clear any cached import failures
        import importlib
        if "blst" in __import__("sys").modules:
            del __import__("sys").modules["blst"]
        importlib.import_module("blst")
    except (ImportError, ModuleNotFoundError):
        return {
            "status": "error",
            "error": "blst was built but could not be imported. Check build output.",
        }

    # Enable verify_certificates in config
    result = _enable_verify_certificates()

    from odin_bots.config import find_config
    config_path = find_config()

    lines = ["blst installed successfully!"]
    lines.append("IC certificate verification is now available.")
    if result["enabled_now"]:
        lines.append("Enabled verify_certificates = true in odin-bots.toml.")
    elif config_path:
        lines.append("verify_certificates is already enabled in odin-bots.toml.")
    else:
        lines.append(
            "Run init first, then set verify_certificates = true "
            "in odin-bots.toml."
        )

    return {"status": "ok", "display": "\n".join(lines)}


def _handle_persona_list(args: dict) -> dict:
    from odin_bots.config import get_default_persona
    from odin_bots.persona import list_personas

    names = list_personas()
    default = get_default_persona()
    lines = ["Available personas:"]
    for name in names:
        marker = " (default)" if name == default else ""
        lines.append(f"  {name}{marker}")
    return {"status": "ok", "display": "\n".join(lines), "personas": names}


def _handle_persona_show(args: dict) -> dict:
    from odin_bots.persona import PersonaNotFoundError, load_persona

    name = args.get("name", "")
    if not name:
        return {"status": "error", "error": "Persona name is required."}

    try:
        p = load_persona(name)
    except PersonaNotFoundError:
        return {"status": "error", "error": f"Persona '{name}' not found."}

    budget = "unlimited" if p.budget_limit == 0 else f"{p.budget_limit:,} sats"
    display = (
        f"Name:        {p.name}\n"
        f"Description: {p.description}\n"
        f"Voice:       {p.voice}\n"
        f"Risk:        {p.risk}\n"
        f"Budget:      {budget}\n"
        f"Default bot: {p.bot}\n"
        f"AI backend:  {p.ai_backend}\n"
        f"AI model:    {p.ai_model}"
    )
    return {
        "status": "ok",
        "display": display,
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
    search_results = [
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
    ]

    # Build display
    lines = [f"Token search: {query}"]
    km = result["known_match"]
    if km:
        flags = []
        if km.get("bonded"):
            flags.append("bonded")
        if km.get("twitter_verified"):
            flags.append("verified")
        flags_str = ", ".join(flags) if flags else "unverified"
        lines.append(
            f"Known match: {km.get('name')} ({km.get('id')}) "
            f"— {flags_str}, {km.get('holder_count', '?')} holders"
        )
    if search_results:
        lines.append("Search results:")
        for r in search_results:
            flags = []
            if r.get("bonded"):
                flags.append("bonded")
            if r.get("twitter_verified"):
                flags.append("verified")
            safety = r.get("safety", "")
            if safety:
                flags.append(safety)
            flags_str = ", ".join(flags) if flags else "unverified"
            lines.append(
                f"  {r.get('name')} ({r.get('id')}) "
                f"— {flags_str}, {r.get('holder_count', '?')} holders"
            )
    elif not km:
        lines.append("No results found.")

    return {
        "status": "ok",
        "display": "\n".join(lines),
        "query": query,
        "known_match": km,
        "search_results": search_results,
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
    return {"status": "ok", "display": output.strip()}


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
    return {"status": "ok", "display": output.strip()}


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
    return {"status": "ok", "display": output.strip()}


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
    return {"status": "ok", "display": output.strip()}


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
        return {"status": "ok", "display": result.output.strip()}
    except typer.Exit:
        return {"status": "error", "error": "Command failed."}


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

_HANDLERS: dict[str, callable] = {
    "fmt_sats": _handle_fmt_sats,
    "setup_status": _handle_setup_status,
    "init": _handle_init,
    "set_bot_count": _handle_set_bot_count,
    "bot_list": _handle_bot_list,
    "wallet_create": _handle_wallet_create,
    "wallet_balance": _handle_wallet_balance,
    "wallet_receive": _handle_wallet_receive,
    "wallet_info": _handle_wallet_info,
    "wallet_monitor": _handle_wallet_monitor,
    "security_status": _handle_security_status,
    "install_blst": _handle_install_blst,
    "persona_list": _handle_persona_list,
    "persona_show": _handle_persona_show,
    "token_lookup": _handle_token_lookup,
    "fund": _handle_fund,
    "trade_buy": _handle_trade_buy,
    "trade_sell": _handle_trade_sell,
    "withdraw": _handle_withdraw,
    "wallet_send": _handle_wallet_send,
}
