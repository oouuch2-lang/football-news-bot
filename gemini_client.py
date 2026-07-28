"""
Общий низкоуровневый клиент для вызовов Gemini API — переиспользуется
text_rewriter.py (переписывание новостей) и admin_agent.py (переписка
с владельцем канала). Если ключа нет или запрос не удался — None,
вызывающий код сам решает, как деградировать (пропустить новость,
переспросить владельца и т.д.).
"""
import requests

import config


def generate(prompt: str, json_mode: bool = False) -> str | None:
    """Отправляет prompt в Gemini, возвращает текст ответа или None."""
    if not config.GEMINI_API_KEY:
        return None

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{config.GEMINI_MODEL}:generateContent"
    )
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    if json_mode:
        body["generationConfig"] = {"responseMimeType": "application/json"}

    try:
        response = requests.post(
            url,
            headers={"x-goog-api-key": config.GEMINI_API_KEY},
            json=body,
            timeout=30,
        )
        response.raise_for_status()
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        return text or None
    except Exception as e:
        print(f"Gemini API не ответил: {e}")
        return None
