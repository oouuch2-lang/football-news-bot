"""
Настройки бота. Все значения берутся из переменных окружения:
локально — из файла .env (см. .env.example), на GitHub Actions — из Secrets репозитория.
"""
import os

from dotenv import load_dotenv

load_dotenv()  # если .env есть — подхватит его; если нет (как в GitHub Actions) — просто ничего не сделает


def _require(name: str) -> str:
    """Читает обязательную переменную окружения и сразу даёт понятную ошибку, если её забыли задать."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Не задана переменная окружения {name} — добавь её в .env или в Secrets репозитория")
    return value


# --- Telegram ---
TELEGRAM_TOKEN = _require("TELEGRAM_TOKEN")
CHANNEL_ID = _require("CHANNEL_ID")  # например: @my_channel или -1001234567890

# --- RSS-ленты, перечисленные через запятую в одной переменной ---
RSS_URLS = [url.strip() for url in os.environ.get("RSS_URLS", "").split(",") if url.strip()]

# --- Сколько новостей публиковать за один запуск (чтобы не выгрузить в канал пачку сразу) ---
# os.environ.get(key) or default — а не get(key, default): GitHub Actions передаёт
# незаданную repository variable как пустую строку "", а не отсутствующий ключ,
# так что обычный default сюда не сработал бы и int("") падал бы с ошибкой.
MAX_NEWS_PER_RUN = int(os.environ.get("MAX_NEWS_PER_RUN") or "3")

# --- Генерация изображений: pollinations (бесплатно, без ключа) | huggingface | cloudflare | none ---
IMAGE_PROVIDER = (os.environ.get("IMAGE_PROVIDER") or "pollinations").lower()

HUGGINGFACE_API_KEY = os.environ.get("HUGGINGFACE_API_KEY", "")
HUGGINGFACE_MODEL = os.environ.get("HUGGINGFACE_MODEL") or "stabilityai/stable-diffusion-xl-base-1.0"

CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "")
CLOUDFLARE_MODEL = os.environ.get("CLOUDFLARE_MODEL") or "@cf/black-forest-labs/flux-1-schnell"

# --- Файл с историей опубликованных новостей (чтобы не постить одну новость дважды) ---
HISTORY_FILE = os.environ.get("HISTORY_FILE") or "data/published_history.json"

# --- Переписывание текста через Gemini API (опционально) ---
# Без ключа новости публикуются как есть (заголовок+описание с RSS, на языке источника).
# Ключ бесплатный, получить на https://aistudio.google.com/apikey.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash"

# --- Telegram-аккаунт владельца бота (для статистики и уведомлений в личку) ---
# Числовой ID, не @username. Свой ID можно узнать, написав боту @userinfobot.
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")
