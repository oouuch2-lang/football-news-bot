"""
Парсинг RSS-лент и хранение истории уже опубликованных новостей,
чтобы одна и та же новость не улетела в канал дважды.
"""
import html
import json
import os
import re

import feedparser

import config


def load_history() -> dict:
    """Читает историю опубликованных ссылок: {ссылка: время публикации в UTC}.
    Если файла ещё нет — история пустая."""
    if not os.path.exists(config.HISTORY_FILE):
        return {}
    with open(config.HISTORY_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        # старый формат (просто список ссылок, без времени) — читаем как есть,
        # дату публикации для них мы не знаем, в статистику они не попадут
        return {link: None for link in data}
    return data


def save_history(history: dict) -> None:
    """Сохраняет историю на диск (создаёт папку data/, если её ещё нет)."""
    folder = os.path.dirname(config.HISTORY_FILE)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(config.HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(history.items())), f, ensure_ascii=False, indent=2)


def get_fresh_news() -> list:
    """
    Обходит все RSS-ленты из config.RSS_URLS и возвращает новости,
    которых ещё не было в истории публикаций. Каждая новость — словарь
    с полями title, summary, link.
    """
    history = load_history()
    fresh = []

    for url in config.RSS_URLS:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            link = entry.get("link", "")
            title = html.unescape(entry.get("title", "")).strip()
            if not link or not title or link in history:
                continue
            fresh.append({
                "title": title,
                "summary": _clean_summary(entry.get("summary", "")),
                "link": link,
            })

    return fresh


def _clean_summary(raw_summary: str) -> str:
    """Убирает HTML-теги и разэкранирует HTML-сущности в описании новости.

    Некоторые ленты (например, Sky Sports) отдают текст, где апостроф уже
    закодирован как &#8217; — без html.unescape он попадёт в пост как есть
    ("day&#8217;s racing" вместо "day's racing").
    """
    text = re.sub(r"<[^>]+>", "", raw_summary)
    return html.unescape(text).strip()
