"""Interactive chat command for trading personas."""

import itertools
import locale
import random
import sys
import threading
import time

from odin_bots.ai import APIKeyMissingError, create_backend
from odin_bots.memory import read_strategy, read_trades
from odin_bots.persona import Persona, PersonaNotFoundError, load_persona

# Topics and icons for IConfucius startup quotes (from IConfucius agent)
QUOTE_TOPICS = [
    {"cn": "咖啡", "icon": "☕️", "en": "Coffee"},
    {"cn": "加密货币", "icon": "📈", "en": "Cryptocurrency"},
    {"cn": "天空", "icon": "🌤️", "en": "Sky"},
    {"cn": "花朵", "icon": "🌸", "en": "Flowers"},
    {"cn": "公正之神", "icon": "⚖️", "en": "Justice"},
    {"cn": "进步的颠覆性本质", "icon": "🌱", "en": "The disruptive nature of progress"},
    {"cn": "修养", "icon": "🏋️", "en": "Discipline"},
    {"cn": "耐心", "icon": "🕰️", "en": "Patience"},
    {"cn": "和谐", "icon": "☯️", "en": "Harmony"},
    {"cn": "礼仪", "icon": "🎎", "en": "Ritual and Courtesy"},
    {"cn": "诚信", "icon": "🤝", "en": "Integrity"},
    {"cn": "学习", "icon": "📖", "en": "Lifelong Learning"},
    {"cn": "反思", "icon": "🪞", "en": "Reflection"},
    {"cn": "顺其自然", "icon": "🍃", "en": "Acceptance of Nature"},
    {"cn": "简朴", "icon": "🍂", "en": "Simplicity"},
    {"cn": "平衡", "icon": "⚖️", "en": "Balance"},
    {"cn": "信任", "icon": "🤠", "en": "Trust"},
    {"cn": "积累", "icon": "💰", "en": "Accumulation of Wealth"},
    {"cn": "投资", "icon": "💵", "en": "Investment"},
    {"cn": "风险", "icon": "⚠️", "en": "Risk"},
    {"cn": "创新", "icon": "💡", "en": "Innovation"},
    {"cn": "适应", "icon": "🌌", "en": "Adaptation"},
    {"cn": "坚韧", "icon": "🗿", "en": "Resilience"},
    {"cn": "洞察", "icon": "🔍", "en": "Insight"},
    {"cn": "目标", "icon": "🎯", "en": "Goal Setting"},
    {"cn": "自由", "icon": "🌈", "en": "Freedom"},
    {"cn": "责任", "icon": "👷", "en": "Responsibility"},
    {"cn": "时间", "icon": "⏳", "en": "Time Management"},
    {"cn": "财富", "icon": "💸", "en": "Wealth"},
    {"cn": "节制", "icon": "🏋️", "en": "Moderation"},
    {"cn": "虚拟资产", "icon": "💹", "en": "Digital Assets"},
    {"cn": "共识", "icon": "🔀", "en": "Consensus"},
    {"cn": "去中心化", "icon": "🛠️", "en": "Decentralization"},
    {"cn": "透明", "icon": "👀", "en": "Transparency"},
    {"cn": "智慧", "icon": "🤔", "en": "Wisdom"},
    {"cn": "信用", "icon": "📈", "en": "Credit"},
    {"cn": "安全", "icon": "🔒", "en": "Security"},
    {"cn": "机遇", "icon": "🍀", "en": "Opportunity"},
    {"cn": "成长", "icon": "🌱", "en": "Growth"},
    {"cn": "合作", "icon": "🤝", "en": "Collaboration"},
    {"cn": "选择", "icon": "🔀", "en": "Choice"},
    {"cn": "敬业", "icon": "💼", "en": "Professionalism"},
    {"cn": "审慎", "icon": "📊", "en": "Prudence"},
    {"cn": "理性", "icon": "🤖", "en": "Rationality"},
    {"cn": "契约", "icon": "📑", "en": "Contract"},
    {"cn": "区块链", "icon": "🛠️", "en": "Blockchain"},
    {"cn": "匿名", "icon": "🔎", "en": "Anonymity"},
    {"cn": "竞争", "icon": "🏆", "en": "Competition"},
    {"cn": "领导", "icon": "👑", "en": "Leadership"},
    {"cn": "市场", "icon": "🏢", "en": "Market"},
    {"cn": "社区", "icon": "🏞️", "en": "Community"},
    {"cn": "自我实现", "icon": "🌟", "en": "Self-Actualization"},
    {"cn": "善良", "icon": "💖", "en": "Kindness"},
    {"cn": "信念", "icon": "✨", "en": "Belief"},
    {"cn": "忠诚", "icon": "🦁", "en": "Loyalty"},
    {"cn": "美德", "icon": "🌿", "en": "Virtue"},
    {"cn": "远见", "icon": "🔮", "en": "Vision"},
    {"cn": "成就", "icon": "🌟", "en": "Achievement"},
    {"cn": "共享", "icon": "👥", "en": "Sharing"},
    {"cn": "交流", "icon": "📢", "en": "Communication"},
    {"cn": "执行力", "icon": "🔄", "en": "Execution"},
    {"cn": "算法", "icon": "🔢", "en": "Algorithm"},
    {"cn": "冷静", "icon": "🌧️", "en": "Calmness"},
    {"cn": "奋斗", "icon": "⚔️", "en": "Struggle"},
    {"cn": "信号", "icon": "📶", "en": "Signal"},
    {"cn": "贪婪", "icon": "💶", "en": "Greed"},
    {"cn": "慈善", "icon": "💜", "en": "Charity"},
    {"cn": "艺术", "icon": "🎨", "en": "Art"},
    {"cn": "科技", "icon": "📱", "en": "Technology"},
    {"cn": "策略", "icon": "🔫", "en": "Strategy"},
    {"cn": "耐力", "icon": "🌼", "en": "Endurance"},
    {"cn": "梦想", "icon": "🌟", "en": "Dreams"},
    {"cn": "节奏", "icon": "🎵", "en": "Rhythm"},
    {"cn": "健康", "icon": "🏥", "en": "Health"},
    {"cn": "家庭", "icon": "🏡", "en": "Family"},
    {"cn": "教育", "icon": "🎓", "en": "Education"},
    {"cn": "旅行", "icon": "🛰", "en": "Travel"},
    {"cn": "幸福", "icon": "🎉", "en": "Happiness"},
    {"cn": "机密", "icon": "🔒", "en": "Confidentiality"},
    {"cn": "原则", "icon": "🔄", "en": "Principles"},
    {"cn": "法律", "icon": "🏛️", "en": "Law"},
    {"cn": "效率", "icon": "⏳", "en": "Efficiency"},
    {"cn": "反脆弱", "icon": "💪", "en": "Antifragility"},
    {"cn": "道德", "icon": "📍", "en": "Morality"},
    {"cn": "灵感", "icon": "💡", "en": "Inspiration"},
    {"cn": "公平", "icon": "⚖️", "en": "Fairness"},
    {"cn": "未来", "icon": "🌟", "en": "Future"},
    {"cn": "传统", "icon": "🎐", "en": "Tradition"},
    {"cn": "关系", "icon": "👨‍👨‍👦", "en": "Relationships"},
]


class _Spinner:
    """Animated spinner for the terminal."""

    def __init__(self, message: str = ""):
        self._message = message
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self):
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        if self._thread:
            self._thread.join()
        # Clear the spinner line
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    def _spin(self):
        frames = itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")
        while not self._stop.is_set():
            sys.stdout.write(f"\r{next(frames)} {self._message}")
            sys.stdout.flush()
            time.sleep(0.08)


def _get_language_code() -> str:
    """Detect system language. Returns 'cn' for Chinese, 'en' otherwise."""
    lang = locale.getdefaultlocale()[0] or ""
    return "cn" if lang.startswith("zh") else "en"


def _format_api_error(e: Exception) -> str:
    """Return a user-friendly error message for API errors."""
    msg = str(e).lower()
    if "credit balance" in msg or "purchase credits" in msg:
        return (
            "Your Anthropic API credit balance is too low.\n"
            "Add credits at: https://console.anthropic.com/settings/plans"
        )
    if "api_key" in msg or "auth" in msg:
        return "Authentication failed. Check your ANTHROPIC_API_KEY in .env"
    if "rate" in msg and "limit" in msg:
        return "Rate limited. Please wait a moment and try again."
    if "overloaded" in msg:
        return "The API is temporarily overloaded. Please try again."
    return str(e)


def _generate_startup(backend, persona, lang: str) -> tuple[str, str]:
    """Generate greeting and goodbye in one API call.

    Uses the persona's greeting_prompt and goodbye_prompt templates.
    Returns (greeting_text, goodbye_text).
    """
    entry = random.choice(QUOTE_TOPICS)
    icon = entry["icon"]
    topic = entry[lang]

    # Build greeting prompt from persona template
    greeting_prompt = persona.greeting_prompt.format(icon=icon, topic=topic)

    # Combine greeting + goodbye into one request
    user_msg = (
        f"{greeting_prompt}\n\n"
        f"After a blank line, also add:\n"
        f"{persona.goodbye_prompt}"
    )

    messages = [{"role": "user", "content": user_msg}]
    response = backend.chat(messages, system=persona.system_prompt)

    # Split: everything before the last line is greeting, last line is goodbye
    lines = response.strip().split("\n")
    # Find the last non-empty line as goodbye
    goodbye = ""
    greeting_lines = []
    for line in reversed(lines):
        if line.strip() and not goodbye:
            goodbye = line.strip()
        else:
            greeting_lines.insert(0, line)
    greeting = "\n".join(greeting_lines).strip()

    return greeting, goodbye


def run_chat(persona_name: str, bot_name: str, verbose: bool = False) -> None:
    """Run interactive chat with a trading persona.

    Args:
        persona_name: Name of the persona to load.
        bot_name: Default bot for trading context.
        verbose: Show verbose output.
    """
    try:
        persona = load_persona(persona_name)
    except PersonaNotFoundError as e:
        print(f"Error: {e}")
        return

    try:
        backend = create_backend(persona)
    except APIKeyMissingError as e:
        print(f"\n{e}")
        return
    except Exception as e:
        print(f"\nError creating AI backend: {e}")
        return

    # Build system prompt with memory context
    system = persona.system_prompt
    strategy = read_strategy(persona_name)
    recent_trades = read_trades(persona_name, last_n=5)

    if strategy:
        system += f"\n\n## Current Strategy\n{strategy}"
    if recent_trades:
        system += f"\n\n## Recent Trades\n{recent_trades}"

    system += f"\n\nYou are trading as bot '{bot_name}'."

    # Verify API access with a startup greeting (also caches goodbye)
    lang = _get_language_code()
    try:
        with _Spinner(f"{persona.name} is thinking..."):
            greeting, goodbye = _generate_startup(backend, persona, lang)
    except Exception as e:
        print(f"\n{_format_api_error(e)}")
        return

    print(f"\n{persona.name}:\n{greeting}\n")
    print("\033[2mexit to quit · Ctrl+C to interrupt\033[0m\n")

    messages: list[dict] = []

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{persona.name}: {goodbye}")
            break

        if user_input.lower() in ("exit", "quit", "/exit", "/quit"):
            print(f"{persona.name}: {goodbye}")
            break

        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})

        try:
            response = backend.chat(messages, system=system)
        except Exception as e:
            print(f"\n{_format_api_error(e)}\n")
            messages.pop()  # Remove the failed message
            continue

        messages.append({"role": "assistant", "content": response})
        print(f"\n{persona.name}: {response}\n")
