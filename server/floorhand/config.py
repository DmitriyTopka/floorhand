"""Settings read from the environment (.env on the server)."""
import os
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(Path(__file__).resolve().parent.parent / ".env")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
DRAFTS = os.environ.get("DRAFTS", "llm")  # llm | template
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
SHOP_NAME = os.environ.get("SHOP_NAME", "TechnoTochka demo shop")
DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
CATALOG_PATH = Path(os.environ.get("CATALOG_PATH", "./catalog/catalog.json"))
# Shop rules copied from the shop's public pages (delivery, payment, warranty). Optional.
POLICY_PATH = Path(os.environ.get("POLICY_PATH", str(CATALOG_PATH.parent / "shop_policy.md")))
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")


def llm_enabled() -> bool:
    return DRAFTS == "llm" and bool(ANTHROPIC_API_KEY)

# Public demo: whoever pairs the glasses sees only the questions they sent
# themselves, so judges trying the bot never see each other's messages.
DEMO_ISOLATION = os.environ.get("DEMO_ISOLATION", "1") == "1"

# Local development only: no Telegram calls, plus a /dev/customer endpoint that
# plays a customer. Never set on the public server.
DEV_FAKE_TELEGRAM = os.environ.get("DEV_FAKE_TELEGRAM", "0") == "1"

# Shop mode (DEMO_ISOLATION=0): only these Telegram chat ids may pair glasses.
OWNER_CHAT_IDS = {int(x) for x in os.environ.get("OWNER_CHAT_IDS", "").split(",") if x.strip()}
