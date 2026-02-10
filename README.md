# odin-bots

Your trading bot for Bitcoin Runes on [Odin.fun](https://odin.fun).

## Quick Start

```bash
pip install odin-bots

mkdir my-bots && cd my-bots
odin-bots init
odin-bots wallet create
# Fund your wallet from Unisat, Sparrow, Electrum, BlueWallet, Oisy, NNS, Plug, etc.
odin-bots wallet receive
```

After funding your wallet:

```bash
# Deposit and trade with the default bot ("bot-1")
odin-bots deposit 5000
odin-bots trade buy 29m8 1000

# Or specify a bot by name
odin-bots --bot bot-2 deposit 5000
odin-bots --bot bot-2 trade buy 29m8 1000
```

## Commands

```bash
# Setup
odin-bots init                               # Initialize project
odin-bots wallet create                      # Generate wallet identity
odin-bots wallet receive                     # Show how to fund the wallet
odin-bots wallet info                        # Show wallet address and balance
odin-bots wallet send <sats|all> <address>   # Send funds to an address

# Trading (operates on default bot, or use --bot <name>)
odin-bots balances                           # Show balances
odin-bots deposit <sats>                     # Deposit ckBTC into Odin
odin-bots withdraw <sats|all>                # Withdraw from Odin to ckBTC
odin-bots trade buy <token> <sats>           # Buy tokens
odin-bots trade sell <token> <amount>        # Sell tokens

# Multi-bot (--bot works with all commands)
odin-bots --bot bot-2 balances
odin-bots --bot bot-2 deposit 5000
odin-bots --bot bot-2 trade buy 29m8 1000
```

## Configuration

`odin-bots.toml` (created by `odin-bots init`):

```toml
[settings]
default_bot = "bot-1"

[bots.bot-1]
description = "Bot 1"

[bots.bot-2]
description = "Bot 2"

[bots.bot-3]
description = "Bot 3"
```

Each bot gets its own wallet and trading identity. Add or remove `[bots.*]` sections as needed.

## Project Layout

```
my-bots/
├── .gitignore             # ignores .wallet/, .cache/
├── odin-bots.toml         # bot config
├── .wallet/               # identity key (BACK UP!)
│   └── identity-private.pem
└── .cache/                # session cache (auto-created)
```

## Open Source & Verifiable

odin-bots is powered by the onicai ckSigner canister: [`g7qkb-iiaaa-aaaar-qb3za-cai`](https://dashboard.internetcomputer.org/canister/g7qkb-iiaaa-aaaar-qb3za-cai)

The canister code is fully open source with a reproducible build, available at [github.com/onicai/ChainFusionAI](https://github.com/onicai/ChainFusionAI).

## How It Works

See [README-how-it-works.md](README-how-it-works.md) for technical details.

## Contribute

To contribute, see [README-contribute.md](README-contribute.md).

## Status & Disclaimer

This project is in **alpha**. APIs may change without notice.

The software and hosted services are provided "as is", without warranty of any kind. Use at your own risk. The authors and onicai are not liable for any losses — including but not limited to loss of funds, keys, or data — incurred through use of this software or the hosted canister services. No guarantee of availability, correctness, or security is made. You are solely responsible for evaluating the suitability of these services for your use case and for complying with all applicable laws and regulations in your jurisdiction.

## License

MIT
# odin_bots
