"""
Переписывание новости через Gemini API: из английского RSS-текста делает
живой русский пост — короткими фразами, без канцелярита, с уместными эмодзи.

Полностью опционален: без GEMINI_API_KEY или при любой ошибке API
rewrite() возвращает None, и вызывающий код публикует новость как есть
(оригинальный заголовок и описание с RSS) — точно так же, как
image_generator ведёт себя при недоступном провайдере картинок.
"""
import bot_settings
import gemini_client

PROMPT_TEMPLATE = """Перепиши эту спортивную новость для поста в Telegram-канале.

Правила:
- Пиши по-русски, живо и разговорно, как для друга, а не для отчёта.
- Никакого канцелярита и штампов.
- Короткие предложения, до 15 слов.
- Уместные эмодзи — не более 2-3 на весь пост.
{extra_rule}- Ответь СТРОГО в этом формате, без кавычек и пояснений:
Короткий цепляющий заголовок одной строкой
<пустая строка>
Текст поста, 2-4 предложения

Заголовок источника: {title}
Описание источника: {summary}"""


def rewrite(title: str, summary: str) -> tuple[str, str] | None:
    """Возвращает (заголовок, текст поста) на русском или None, если Gemini недоступен."""
    tone = bot_settings.load().get("text_tone")
    extra_rule = f"- Дополнительное пожелание по стилю: {tone}\n" if tone else ""
    prompt = PROMPT_TEMPLATE.format(title=title, summary=summary, extra_rule=extra_rule)

    text = gemini_client.generate(prompt)
    if not text:
        return None

    head, _, body = text.partition("\n\n")
    if not body:
        # Gemini не разделил заголовок и текст пустой строкой — используем
        # исходный заголовок RSS, а весь ответ целиком как текст поста
        return title, text
    return head.strip(), body.strip()
