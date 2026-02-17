"""Tool definitions for odin-bots agent skills.

Each tool has:
- name, description, input_schema: Standard Anthropic tool format
- requires_confirmation: True for state-changing tools (buy, sell, fund, etc.)
- category: "read" or "write"
"""

TOOLS: list[dict] = [
    # ------------------------------------------------------------------
    # Read-only tools (no confirmation needed)
    # ------------------------------------------------------------------
    {
        "name": "wallet_balance",
        "description": (
            "Check wallet ckBTC balance and bot holdings on Odin.fun. "
            "Returns wallet balance, bot balances, and token holdings."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "bot_name": {
                    "type": "string",
                    "description": (
                        "Specific bot to check (e.g. 'bot-1'). "
                        "Omit to check wallet only."
                    ),
                },
                "all_bots": {
                    "type": "boolean",
                    "description": "Check all configured bots.",
                    "default": False,
                },
            },
            "required": [],
        },
        "requires_confirmation": False,
        "category": "read",
    },
    {
        "name": "wallet_receive",
        "description": (
            "Show the Bitcoin deposit address for funding the odin-bots wallet. "
            "Users send BTC to this address to get ckBTC."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "requires_confirmation": False,
        "category": "read",
    },
    {
        "name": "wallet_info",
        "description": (
            "Show wallet principal identity and ckBTC balance."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "requires_confirmation": False,
        "category": "read",
    },
    {
        "name": "persona_list",
        "description": "List all available trading personas.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "requires_confirmation": False,
        "category": "read",
    },
    {
        "name": "persona_show",
        "description": (
            "Show details of a specific trading persona "
            "(name, voice, risk level, AI backend)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Persona name (e.g. 'iconfucius').",
                },
            },
            "required": ["name"],
        },
        "requires_confirmation": False,
        "category": "read",
    },
    {
        "name": "token_lookup",
        "description": (
            "Search for a token by name, ticker, or ID. "
            "Returns token details with safety indicators "
            "(bonded status, verification, holder count). "
            "Use this to find the correct token ID before trading."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Token name, ticker, or ID to search for "
                        "(e.g. 'IConfucius', 'ODINDOG', '29m8')."
                    ),
                },
            },
            "required": ["query"],
        },
        "requires_confirmation": False,
        "category": "read",
    },
    # ------------------------------------------------------------------
    # State-changing tools (confirmation required)
    # ------------------------------------------------------------------
    {
        "name": "fund",
        "description": (
            "Deposit ckBTC from wallet into a bot's Odin.fun trading account. "
            "Minimum deposit: 5,000 sats."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {
                    "type": "integer",
                    "description": "Amount in sats to deposit.",
                },
                "bot_name": {
                    "type": "string",
                    "description": "Bot name to fund (e.g. 'bot-1').",
                },
            },
            "required": ["amount", "bot_name"],
        },
        "requires_confirmation": True,
        "category": "write",
    },
    {
        "name": "trade_buy",
        "description": (
            "Buy tokens on Odin.fun using BTC from a bot's trading account. "
            "Minimum trade: 500 sats."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "token_id": {
                    "type": "string",
                    "description": "Token ID to buy (e.g. '29m8').",
                },
                "amount": {
                    "type": "integer",
                    "description": "Amount in sats to spend.",
                },
                "bot_name": {
                    "type": "string",
                    "description": "Bot name to trade with (e.g. 'bot-1').",
                },
            },
            "required": ["token_id", "amount", "bot_name"],
        },
        "requires_confirmation": True,
        "category": "write",
    },
    {
        "name": "trade_sell",
        "description": (
            "Sell tokens on Odin.fun. Use amount 'all' to sell entire position. "
            "Minimum trade value: 500 sats."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "token_id": {
                    "type": "string",
                    "description": "Token ID to sell (e.g. '29m8').",
                },
                "amount": {
                    "type": "string",
                    "description": (
                        "Amount of tokens to sell, or 'all' for entire position."
                    ),
                },
                "bot_name": {
                    "type": "string",
                    "description": "Bot name to trade with (e.g. 'bot-1').",
                },
            },
            "required": ["token_id", "amount", "bot_name"],
        },
        "requires_confirmation": True,
        "category": "write",
    },
    {
        "name": "withdraw",
        "description": (
            "Withdraw BTC from a bot's Odin.fun account back to the odin-bots wallet."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {
                    "type": "string",
                    "description": (
                        "Amount in sats to withdraw, or 'all' for entire balance."
                    ),
                },
                "bot_name": {
                    "type": "string",
                    "description": "Bot name to withdraw from (e.g. 'bot-1').",
                },
            },
            "required": ["amount", "bot_name"],
        },
        "requires_confirmation": True,
        "category": "write",
    },
    {
        "name": "wallet_send",
        "description": (
            "Send ckBTC from the odin-bots wallet to an external Bitcoin address."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {
                    "type": "string",
                    "description": (
                        "Amount in sats to send, or 'all' for entire balance."
                    ),
                },
                "address": {
                    "type": "string",
                    "description": "Destination Bitcoin address.",
                },
            },
            "required": ["amount", "address"],
        },
        "requires_confirmation": True,
        "category": "write",
    },
]


def get_tools_for_anthropic() -> list[dict]:
    """Return tool definitions in Anthropic API format.

    Strips internal metadata (requires_confirmation, category) so the
    list can be passed directly to messages.create(tools=...).
    """
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["input_schema"],
        }
        for t in TOOLS
    ]


def get_tool_metadata(name: str) -> dict | None:
    """Return the full tool dict (including metadata) by name.

    Returns None if the tool name is not found.
    """
    for t in TOOLS:
        if t["name"] == name:
            return t
    return None
