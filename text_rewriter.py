"""
Переписывание новости через Gemini API: из английского RSS-текста делает
живой русский пост — короткими фразами, без канцелярита, с уместными эмодзи.

Полностью опционален: без GEMINI_API_KEY или при любой ошибке API
rewrite() возвращает None, и вызывающий код публикует новость как есть
(оригинальный заголовок и описание с RSS) — точно так же, как
image_generator ведёт себя при недоступном провайдере картинок.
"""
import requests

import config

PROMPT_TEMPLATE = """Перепиши эту спортивную новость для поста в Telegram-канале.

Правила:
- Пиши по-русски, живо и разговорно, как для друга, а не для отчёта.
- Никакого канцелярита и штампов.
- Короткие предложения, до 15 слов.
- Уместные эмодзи — не более 2-3 на весь пост.
- Ответь СТРОГО в этом формате, без кавычек и пояснений:
Короткий цепляющий заголовок одной строкой
<пустая строка>
Текст поста, 2-4 предложения

Заголовок источника: {title}
Описание источника: {summary}"""


def rewrite(title: str, summary: str) -> tuple[str, str] | None:
    """Возвращает (заголовок, текст поста) на русском или None, если Gemini недоступен."""
    if not config.GEMINI_API_KEY:
        return None

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{config.GEMINI_MODEL}:generateContent"
    )
    prompt = PROMPT_TEMPLATE.format(title=title, summary=summary)

    try:
        response = requests.post(
            url,
            headers={"x-goog-api-key": config.GEMINI_API_KEY},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=30,
        )
        response.raise_for_status()
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        if not text:
            return None

        head, _, body = text.partition("\n\n")
        if not body:
            # Gemini не разделил заголовок и текст пустой строкой — используем
            # исходный заголовок RSS, а весь ответ целиком как текст поста
            return title, text
        return head.strip(), body.strip()
    except Exception as e:
        print(f"Gemini не смог переписать текст: {e}")
        return None
