"""
odin_bots.cli.wallet — Wallet identity and fund management

Commands:
    wallet create              Generate Ed25519 identity
    wallet info                Show wallet address and balance
    wallet receive             Show how to fund the wallet (ckBTC or BTC)
    wallet send <amt> <addr>   Send ckBTC to a principal or BTC to a Bitcoin address
"""

import os
import stat
import sys
from pathlib import Path
from typing import Optional

import typer

from odin_bots.config import PEM_FILE, _project_root, get_verify_certificates

wallet_app = typer.Typer(no_args_is_help=True, result_callback=lambda *a, **kw: _print_backup_warning())

WALLET_DIR = ".wallet"

PEM_BACKUP_WARNING = """\

IMPORTANT: Back up .wallet/identity-private.pem securely!
  - If lost, you lose access to your wallet and all funds in it.
  - If leaked, anyone can control your wallet.
  - Treat it like an SSH private key or a Bitcoin seed phrase."""

CERT_VERIFY_WARNING = """
WARNING: IC certificate verification is disabled. See README-security.md for details."""


def _print_backup_warning():
    """Print PEM backup warning after every wallet command."""
    if _pem_path().exists():
        print(PEM_BACKUP_WARNING)
    if not get_verify_certificates():
        print(CERT_VERIFY_WARNING)


def _wallet_dir() -> Path:
    """Return the .wallet/ directory path."""
    return Path(_project_root()) / WALLET_DIR


def _pem_path() -> Path:
    """Return the full path to identity-private.pem."""
    return Path(_project_root()) / PEM_FILE


WITHDRAWALS_FILE = ".wallet/btc_withdrawals.json"

MEMPOOL_TX_URL = "https://mempool.space/tx/"


def _withdrawals_path() -> Path:
    """Return the path to the withdrawals tracking file."""
    return Path(_project_root()) / WITHDRAWALS_FILE


def save_withdrawal_status(block_index: int, btc_address: str, amount: int):
    """Append a BTC withdrawal to the tracking list."""
    import json
    path = _withdrawals_path()
    path.parent.mkdir(exist_ok=True)
    withdrawals = load_withdrawal_statuses()
    withdrawals.append({
        "block_index": block_index,
        "btc_address": btc_address,
        "amount": amount,
    })
    path.write_text(json.dumps(withdrawals))


def load_withdrawal_statuses() -> list:
    """Load all tracked BTC withdrawals."""
    import json
    path = _withdrawals_path()
    if not path.exists():
        # Migrate from old single-withdrawal file
        old_path = Path(_project_root()) / ".wallet/last_btc_withdrawal.json"
        if old_path.exists():
            try:
                data = json.loads(old_path.read_text())
                if isinstance(data, dict):
                    return [data]
                return data if isinstance(data, list) else []
            except Exception:
                return []
        return []
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []


def remove_withdrawal(block_index: int):
    """Remove a confirmed withdrawal from the tracking list."""
    import json
    path = _withdrawals_path()
    withdrawals = load_withdrawal_statuses()
    withdrawals = [w for w in withdrawals if w.get("block_index") != block_index]
    if withdrawals:
        path.write_text(json.dumps(withdrawals))
    elif path.exists():
        path.unlink()
        # Clean up old file too
        old_path = Path(_project_root()) / ".wallet/last_btc_withdrawal.json"
        if old_path.exists():
            old_path.unlink()


def _load_identity():
    """Load the wallet identity from PEM file.

    Returns the Identity object, or exits with an error.
    """
    from icp_identity import Identity

    pem = _pem_path()
    if not pem.exists():
        print(f"Wallet not found at {pem}")
        print("Create it with: odin-bots wallet create")
        raise typer.Exit(1)

    return Identity.from_pem(pem.read_bytes())


@wallet_app.command()
def create(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing wallet"),
):
    """Generate a new Ed25519 wallet identity."""
    from icp_identity import Identity

    pem = _pem_path()
    if pem.exists() and not force:
        print(f"Wallet already exists at {pem}")
        print("Use --force to overwrite (WARNING: this will change your wallet address!)")
        raise typer.Exit(1)

    # Generate Ed25519 keypair
    identity = Identity(type="ed25519")
    pem_bytes = identity.to_pem()

    # Create .wallet/ directory
    wallet_dir = _wallet_dir()
    wallet_dir.mkdir(exist_ok=True)

    # Atomic-create with 0600 from the start (no race window with world-readable perms)
    fd = os.open(pem, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "wb") as f:
        f.write(pem_bytes)

    print(f"Wallet created: {pem}")
    print()
    print("  External wallet -> odin-bots wallet")
    print("                       |-- fund -> bot-1 -> Odin.Fun trading")
    print("                       |-- fund -> bot-2 -> Odin.Fun trading")
    print("                       +-- fund -> bot-3 -> Odin.Fun trading")
    print()
    print("  Send ckBTC/BTC to your odin-bots wallet address,")
    print("  then use 'odin-bots fund' to distribute to your bots.")
    print()
    print("Next step:")
    print("  odin-bots wallet receive")


@wallet_app.command()
def balance(
    token_id: str = typer.Option("29m8", "--token", "-t", help="Token ID to check"),
    bot: Optional[str] = typer.Option(None, "--bot", "-b", help="Bot name to use"),
    all_bots: bool = typer.Option(False, "--all-bots", help="Show all bots"),
):
    """Show ckBTC and Odin token balance."""
    from odin_bots.cli import _resolve_bot_names, state
    from odin_bots.cli.balance import run_all_balances

    bot_names = _resolve_bot_names(bot, all_bots)
    run_all_balances(bot_names=bot_names, token_id=token_id,
                     verbose=state.verbose)


@wallet_app.command()
def info():
    """Show wallet address and ckBTC balance."""
    from odin_bots.config import get_btc_to_usd_rate

    _load_identity()  # Ensure wallet exists

    try:
        btc_usd_rate = get_btc_to_usd_rate()
    except Exception:
        btc_usd_rate = None

    from odin_bots.cli.balance import _print_wallet_info
    _print_wallet_info(btc_usd_rate)


@wallet_app.command()
def receive():
    """Show wallet address for funding with ckBTC or BTC."""
    from icp_agent import Agent, Client
    from icp_identity import Identity

    from odin_bots.config import fmt_sats, get_btc_to_usd_rate
    from odin_bots.transfers import (
        IC_HOST,
        create_ckbtc_minter,
        create_icrc1_canister,
        get_balance,
        get_btc_address,
    )

    identity = _load_identity()
    wallet_principal = str(identity.sender())

    # Get wallet BTC deposit address and balance
    client = Client(url=IC_HOST)
    anon_agent = Agent(Identity(anonymous=True), client)
    minter = create_ckbtc_minter(anon_agent)
    btc_address = get_btc_address(minter, wallet_principal)

    icrc1_canister__anon = create_icrc1_canister(anon_agent)
    balance = get_balance(icrc1_canister__anon, wallet_principal)

    try:
        btc_usd_rate = get_btc_to_usd_rate()
    except Exception:
        btc_usd_rate = None

    print()
    print("=" * 60)
    print("Fund your odin-bots wallet")
    print("=" * 60)
    print()
    print("Option 1: Send BTC from any Bitcoin wallet")
    print(f"  {btc_address}")
    print("  Min deposit: 10,000 sats.")
    print("  Requires ~6 confirmations (~1 hour).")
    print("  Run 'odin-bots --bot <name> balance' to trigger conversion.")
    print()
    print("Option 2: Send ckBTC from any ICP wallet")
    print(f"  {wallet_principal}")
    print("  Send from NNS, Plug, Oisy, or any ICP wallet.")
    print()
    print(f"Wallet balance: {fmt_sats(balance, btc_usd_rate)}")
    print()
    print("After funding, distribute to your bots:")
    print("  odin-bots --bot bot-1 fund 5000  # fund specific bot")
    print("  odin-bots --all-bots fund 5000   # fund all bots")


@wallet_app.command()
def send(
    amount: str = typer.Argument(..., help="Amount in sats, or 'all' for entire balance"),
    address: str = typer.Argument(..., help="Destination: IC principal or Bitcoin address (bc1...)"),
):
    """Send ckBTC to a principal or BTC to a Bitcoin address."""
    from icp_agent import Agent, Client
    from icp_identity import Identity

    from odin_bots.transfers import (
        CKBTC_FEE,
        IC_HOST,
        create_icrc1_canister,
        create_ckbtc_minter,
        get_balance,
        get_withdrawal_account,
        estimate_withdrawal_fee,
        retrieve_btc_withdrawal,
        transfer,
        unwrap_canister_result,
    )

    # Detect address type
    is_btc_address = address.startswith("bc1")

    # Load wallet identity (PEM)
    identity = _load_identity()
    wallet_principal = str(identity.sender())

    client = Client(url=IC_HOST)
    anon_agent = Agent(Identity(anonymous=True), client)
    auth_agent = Agent(identity, client)

    icrc1_canister__anon = create_icrc1_canister(anon_agent)
    icrc1_canister__wallet = create_icrc1_canister(auth_agent)

    from odin_bots.config import fmt_sats, get_btc_to_usd_rate
    try:
        btc_usd_rate = get_btc_to_usd_rate()
    except Exception:
        btc_usd_rate = None

    wallet_balance = get_balance(icrc1_canister__anon, wallet_principal)
    print(f"Wallet balance: {fmt_sats(wallet_balance, btc_usd_rate)}")

    if is_btc_address:
        # BTC withdrawal via ckBTC minter
        _send_btc(
            amount, address, wallet_principal, wallet_balance,
            auth_agent, anon_agent, icrc1_canister__anon, icrc1_canister__wallet,
            create_ckbtc_minter, get_withdrawal_account,
            estimate_withdrawal_fee, retrieve_btc_withdrawal,
            transfer, get_balance, unwrap_canister_result, CKBTC_FEE,
            btc_usd_rate,
        )
    else:
        # ckBTC transfer to IC principal
        _send_ckbtc(
            amount, address, wallet_principal, wallet_balance,
            icrc1_canister__anon, icrc1_canister__wallet,
            transfer, get_balance, CKBTC_FEE,
            btc_usd_rate,
        )


def _send_ckbtc(
    amount, to_principal, wallet_principal, wallet_balance,
    icrc1_canister__anon, icrc1_canister__wallet,
    transfer, get_balance, ckbtc_fee,
    btc_usd_rate=None,
):
    """Send ckBTC to an IC principal via ICRC-1 transfer."""
    from odin_bots.config import fmt_sats

    # Determine amount
    if amount.lower() == "all":
        if wallet_balance <= ckbtc_fee:
            print(f"Insufficient balance. Have {fmt_sats(wallet_balance, btc_usd_rate)}, fee is {fmt_sats(ckbtc_fee, btc_usd_rate)}.")
            raise typer.Exit(1)
        send_amount = wallet_balance - ckbtc_fee
        print(f"Sending all: {fmt_sats(send_amount, btc_usd_rate)} (balance {fmt_sats(wallet_balance, btc_usd_rate)} - fee {ckbtc_fee})")
    else:
        send_amount = int(amount)

    if send_amount <= 0:
        print("Nothing to send.")
        raise typer.Exit(1)

    total_needed = send_amount + ckbtc_fee
    if wallet_balance < total_needed:
        print(f"Insufficient balance. Need {fmt_sats(total_needed, btc_usd_rate)}, have {fmt_sats(wallet_balance, btc_usd_rate)}.")
        raise typer.Exit(1)

    # Execute transfer
    print(f"Sending {fmt_sats(send_amount, btc_usd_rate)} to {to_principal}...")
    try:
        result = transfer(icrc1_canister__wallet, to_principal, send_amount)

        if isinstance(result, dict) and "Err" in result:
            print(f"Transfer failed: {result['Err']}")
            raise typer.Exit(1)

        tx_index = result.get("Ok", result) if isinstance(result, dict) else result
        print(f"Transfer succeeded! Block index: {tx_index}")

    except typer.Exit:
        raise
    except Exception as e:
        print(f"Transfer failed: {e}")
        raise typer.Exit(1)

    # Verify
    wallet_balance_after = get_balance(icrc1_canister__anon, wallet_principal)
    print(f"Wallet balance: {fmt_sats(wallet_balance_after, btc_usd_rate)} (was {fmt_sats(wallet_balance, btc_usd_rate)})")


def _send_btc(
    amount, btc_address, wallet_principal, wallet_balance,
    auth_agent, anon_agent, icrc1_canister__anon, icrc1_canister__wallet,
    create_ckbtc_minter, get_withdrawal_account,
    estimate_withdrawal_fee, retrieve_btc_withdrawal,
    transfer, get_balance, unwrap_canister_result, ckbtc_fee,
    btc_usd_rate=None,
):
    """Withdraw BTC to a Bitcoin address via ckBTC minter."""
    from odin_bots.config import fmt_sats, get_verify_certificates

    # Estimate withdrawal fee
    minter = create_ckbtc_minter(auth_agent)

    print("Estimating withdrawal fee...")
    try:
        fee_info = estimate_withdrawal_fee(minter)
        minter_fee = fee_info.get("minter_fee", 0)
        bitcoin_fee = fee_info.get("bitcoin_fee", 0)
        total_fee = minter_fee + bitcoin_fee
        print(f"  Minter fee: {fmt_sats(minter_fee, btc_usd_rate)}")
        print(f"  Bitcoin fee: {fmt_sats(bitcoin_fee, btc_usd_rate)}")
        print(f"  Total fee: {fmt_sats(total_fee, btc_usd_rate)}")
    except Exception as e:
        print(f"Could not estimate fee: {e}")
        print("Proceeding with default estimate...")
        total_fee = 0

    # Step 1: Get withdrawal account and check existing balance
    print("Getting withdrawal account...")
    withdrawal_account = get_withdrawal_account(minter)
    withdrawal_owner = withdrawal_account.get("owner")
    withdrawal_subaccount = withdrawal_account.get("subaccount", [])

    existing_balance = unwrap_canister_result(
        icrc1_canister__anon.icrc1_balance_of({
            "owner": withdrawal_owner,
            "subaccount": withdrawal_subaccount,
        }, verify_certificate=get_verify_certificates())
    )
    if existing_balance > 0:
        print(f"  Existing balance in withdrawal account: {fmt_sats(existing_balance, btc_usd_rate)}")

    # Determine amount (wallet + existing withdrawal account balance)
    available = wallet_balance + existing_balance
    if amount.lower() == "all":
        # ckbtc_fee only charged when we actually transfer to the withdrawal account
        send_amount = available - total_fee
        if existing_balance < available:
            send_amount -= ckbtc_fee  # need a transfer, so deduct transfer fee
        if send_amount <= 0:
            print(f"Insufficient balance. Have {fmt_sats(available, btc_usd_rate)}, fees are {fmt_sats(ckbtc_fee + total_fee, btc_usd_rate)}.")
            raise typer.Exit(1)
        print(f"Withdrawing all: {fmt_sats(send_amount, btc_usd_rate)}")
    else:
        send_amount = int(amount)

    if send_amount <= 0:
        print("Nothing to send.")
        raise typer.Exit(1)

    # Check minimum BTC withdrawal amount (ckBTC minter enforces this)
    from odin_bots.config import MIN_BTC_WITHDRAWAL_SATS
    if send_amount < MIN_BTC_WITHDRAWAL_SATS:
        print(f"BTC withdrawal amount too low: {fmt_sats(send_amount, btc_usd_rate)}.")
        print(f"Minimum BTC withdrawal via ckBTC minter: {fmt_sats(MIN_BTC_WITHDRAWAL_SATS, btc_usd_rate)}.")
        print(f"To send smaller amounts, use ckBTC transfer to an IC principal instead.")
        raise typer.Exit(1)

    # How much more needs to go into the withdrawal account?
    needed_in_account = send_amount + total_fee
    transfer_amount = max(0, needed_in_account - existing_balance)

    # Check wallet has enough for the transfer (+ ckbtc transfer fee if needed)
    wallet_needed = transfer_amount + (ckbtc_fee if transfer_amount > 0 else 0)
    if wallet_balance < wallet_needed:
        print(f"Insufficient wallet balance. Need {fmt_sats(wallet_needed, btc_usd_rate)}, have {fmt_sats(wallet_balance, btc_usd_rate)}.")
        raise typer.Exit(1)

    if transfer_amount == 0:
        print(f"Withdrawal account already has enough ({fmt_sats(existing_balance, btc_usd_rate)}), skipping transfer.")
    else:
        print(f"Transferring {fmt_sats(transfer_amount, btc_usd_rate)} to minter withdrawal account...")
        try:
            to_account = {"owner": withdrawal_owner, "subaccount": withdrawal_subaccount}
            result_raw = icrc1_canister__wallet.icrc1_transfer(
                {
                    "to": to_account,
                    "amount": transfer_amount,
                    "fee": [],
                    "memo": [],
                    "from_subaccount": [],
                    "created_at_time": [],
                },
                verify_certificate=get_verify_certificates(),
            )
            result = unwrap_canister_result(result_raw)
            if isinstance(result, dict) and "Err" in result:
                print(f"Transfer to withdrawal account failed: {result['Err']}")
                raise typer.Exit(1)
            print(f"  Transfer block index: {result.get('Ok', result) if isinstance(result, dict) else result}")
        except typer.Exit:
            raise
        except Exception as e:
            print(f"Transfer to withdrawal account failed: {e}")
            raise typer.Exit(1)

    # Step 3: Call retrieve_btc
    print(f"Initiating BTC withdrawal of {fmt_sats(send_amount, btc_usd_rate)} to {btc_address}...")
    try:
        result = retrieve_btc_withdrawal(minter, btc_address, send_amount)

        if isinstance(result, dict) and "Err" in result:
            err = result["Err"]
            if "AmountTooLow" in err:
                print(f"Amount too low. Minimum: {fmt_sats(err['AmountTooLow'], btc_usd_rate)}")
            elif "InsufficientFunds" in err:
                print(f"Insufficient funds in withdrawal account: {err['InsufficientFunds']}")
            elif "MalformedAddress" in err:
                print(f"Invalid Bitcoin address: {err['MalformedAddress']}")
            else:
                print(f"Withdrawal failed: {err}")
            raise typer.Exit(1)

        block_index = result.get("Ok", result) if isinstance(result, dict) else result
        if isinstance(block_index, dict):
            block_index = block_index.get("block_index", block_index)
        print(f"BTC withdrawal initiated! Block index: {block_index}")
        print("BTC will arrive after the transaction is confirmed on the Bitcoin network.")
        print("Check progress with: odin-bots wallet info")

        # Save for status tracking
        if isinstance(block_index, int):
            save_withdrawal_status(block_index, btc_address, send_amount)

    except typer.Exit:
        raise
    except Exception as e:
        print(f"Withdrawal failed: {e}")
        raise typer.Exit(1)

    # Verify remaining balance
    wallet_balance_after = get_balance(icrc1_canister__anon, wallet_principal)
    print(f"Wallet balance: {fmt_sats(wallet_balance_after, btc_usd_rate)} (was {fmt_sats(wallet_balance, btc_usd_rate)})")
