[![cicd](https://github.com/onicai/odin_bots/actions/workflows/cicd.yml/badge.svg)](https://github.com/onicai/odin_bots/actions/workflows/cicd.yml)

<p align="center">
  <img src="brand/logo/transparent_with_tagline_SMALL.png" alt="ODIN-BOTS" width="400">
</p>

---

```
pip install odin-bots
```

Note: On macOS Apple Silicon, install `automake` and `libtool` before running `pip install`:
```
brew install automake libtool
```

# Setup (one time):

    odin-bots init             Configures your project with 3 bots
                               Stored in odin-bots.toml

    odin-bots wallet create    Generate wallet identity
                               Stored in .wallet/identity-private.pem

# How to use your bots:

    Step 1. Fund your odin-bots wallet:
            odin-bots wallet receive
            Send ckBTC or BTC to the address shown.

    Step 2. Fund your bots (deposits ckBTC into Odin.Fun):
            odin-bots --bot <name> fund <amount>      # in sats
            odin-bots --all-bots fund <amount>

    Step 3. Buy Runes on Odin.Fun:
            odin-bots --bot <name> trade buy <token-id> <amount>
            odin-bots --all-bots trade buy <token-id> <amount>

    Step 4. Sell Runes on Odin.Fun:
            odin-bots --bot <name> trade sell <token-id> <amount>
            odin-bots --all-bots trade sell <token-id> <amount>
            # to sell all holdings of a token
            odin-bots --bot <name> trade sell <token-id> all
            odin-bots --all-bots trade sell <token-id> all
            # to sell all holdings of all tokens
            odin-bots --bot <name> trade sell all-tokens all
            odin-bots --all-bots trade sell all-tokens all

    Step 5. Withdraw ckBTC from Odin.Fun back to wallet:
            odin-bots --bot <name> withdraw <amount>
            odin-bots --all-bots withdraw <amount>
            # to sweep all ckBTC back into the wallet
            odin-bots --all-bots withdraw all

    Or use sweep to sell all tokens + withdraw in one command:
            odin-bots --bot <name> sweep
            odin-bots --all-bots sweep

    Step 6. Send ckBTC from wallet to an external ckBTC or BTC account:
            odin-bots wallet send <amount> <address>
            (supports both ICRC-1 and BTC addresses)

## Configuration

`odin-bots.toml` (created by `odin-bots init`):

```toml
[settings]

[bots.bot-1]
description = "Bot 1"

[bots.bot-2]
description = "Bot 2"

[bots.bot-3]
description = "Bot 3"
```

Each bot gets its own trading identity on Odin.Fun. Add or remove `[bots.*]` sections as needed.

## Project Layout

```
my-bots/
├── .gitignore             # ignores .wallet/, .cache/
├── odin-bots.toml         # bot config
├── .wallet/               # identity key (BACK UP!)
│   └── identity-private.pem
└── .cache/                # delegated identities (auto-created)
    ├── session_bot-1.json # no backup needed — regenerated
    ├── session_bot-2.json # when expired (24h lifetime)
    └── session_bot-3.json
```

## Open Source & Verifiable

odin-bots is powered by the onicai ckSigner canister: [`g7qkb-iiaaa-aaaar-qb3za-cai`](https://dashboard.internetcomputer.org/canister/g7qkb-iiaaa-aaaar-qb3za-cai)

The canister code is fully open source with a reproducible build, available at [github.com/onicai/PoAIW](https://github.com/onicai/PoAIW) -> ckSigner branch.

## How It Works

See [README-how-it-works.md](README-how-it-works.md) for technical details.

## Security

See [README-security.md](README-security.md) for security considerations and best practices.

## Contribute

To contribute, see [README-contribute.md](README-contribute.md).

## Status & Disclaimer

This project is in **alpha**. APIs may change without notice.

The software and hosted services are provided "as is", without warranty of any kind. Use at your own risk. The authors and onicai are not liable for any losses — including but not limited to loss of funds, keys, or data — incurred through use of this software or the hosted canister services. No guarantee of availability, correctness, or security is made. You are solely responsible for evaluating the suitability of these services for your use case and for complying with all applicable laws and regulations in your jurisdiction.

## Reference

The Bitcoin rune trading platform is [Odin Fun](https://odin.fun/)

## Supported Platforms

| Platform | Python 3.11 | Python 3.12 | Python 3.13 |
| --- | --- | --- | --- |
| Ubuntu (x86-64) | yes | yes | yes |
| macOS Apple Silicon | yes | yes | yes |
| macOS Intel | yes | yes | yes |
| Windows (x86-64) | yes | yes | yes |

## License

MIT
