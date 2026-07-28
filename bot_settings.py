"""
Настройки, которые владелец может поменять перепиской с ботом в личке
(см. admin_agent.py) — цвета/стиль оформления, тон текста постов,
частота публикаций, список RSS-лент.

Хранятся в data/settings.json. Если файла нет (или значение внутри
пустое) — используются дефолты из config.py / brand_config.py, как и
раньше. Файл — единственный источник изменений "поверх" env-переменных,
поэтому пока владелец ничего не менял через чат, поведение бота не
отличается от того, что было до этой фичи.
"""
import json
import os

SETTINGS_FILE = "data/settings.json"

DEFAULTS = {
    "primary_color": None,
    "background_color": None,
    "image_style": None,
    "text_tone": None,
    "max_news_per_run": None,
    "rss_urls": None,
}


def load() -> dict:
    """Читает сохранённые настройки, отсутствующие ключи — None (значит "не менялось")."""
    settings = dict(DEFAULTS)
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            settings.update(json.load(f))
    return settings


def save(settings: dict) -> None:
    folder = os.path.dirname(SETTINGS_FILE)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
