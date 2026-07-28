"""
Переписка с владельцем канала в личных сообщениях боту: он пишет задачу
("сделай оформление ярче", "смени аватарку", "постим реже" и т.п.),
Gemini разбирает намерение и придумывает 2-3 конкретных варианта, бот
присылает их в чат, а после выбора владельца сам применяет изменения —
и правит data/settings.json (цвета, стиль, тон текста, частота, RSS-ленты
— см. bot_settings.py), и меняет саму аватарку канала.

Также есть меню с настоящими Telegram-кнопками (по "/start", "меню" или
"кнопки"): «Опубликовать сейчас», «Сменить аватарку», «Статистика»,
«Оформление» — те же действия, что и ручной запуск main.py/avatar_manager.py/
stats.py с вкладки Actions на GitHub, только сразу из чата.

Отдельный скрипт, запускается по расписанию (.github/workflows/admin_chat.yml)
каждые 5 минут через getUpdates (не webhook — не нужен постоянно работающий
сервер, вписывается в ту же "проснулся-сделал-уснул" модель, что и остальные
workflow'ы). Репозиторий публичный специально для этого — у GitHub Actions
на публичных репозиториях нет лимита минут в месяц.

Отвечает только владельцу (config.ADMIN_CHAT_ID) — если кто-то посторонний
напишет боту (репозиторий публичный, имя бота в коде видно всем), сообщение
просто игнорируется, без ответа.
"""
import asyncio
import json
import os
import random
import re

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

import avatar_manager
import bot_settings
import brand_config
import config
import gemini_client
import image_generator
import image_processor
import main as news_main
import stats

STATE_FILE = "data/admin_state.json"
MAX_HISTORY = 12
MENU_TRIGGERS = {"/start", "меню", "menu", "кнопки"}


def _load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"last_update_id": 0, "history": [], "pending": None}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_state(state: dict) -> None:
    folder = os.path.dirname(STATE_FILE)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _parse_choice(text: str, n_options: int) -> int | None:
    """Понимает "1", "второй", "давай третий вариант" и т.п. Индекс с 0 или None.

    Только для короткой реплики (до 4 слов) — иначе длинное сообщение вроде
    "Второй месяц веду канал, добавь эмодзи в посты" ложно матчилось бы по
    слову "Второй" и вместо новой просьбы применялся бы вариант №2."""
    text = text.strip().lower()
    if len(text.split()) > 4:
        return None
    for i, word in enumerate(("перв", "втор", "трет")):
        if i < n_options and word in text:
            return i
    match = re.search(r"\d+", text)
    if match:
        idx = int(match.group()) - 1
        if 0 <= idx < n_options:
            return idx
    return None


def _decision_prompt(user_text: str, settings: dict, history: list) -> str:
    history_text = "\n".join(
        f"{'Владелец' if h['role'] == 'user' else 'Бот'}: {h['text']}" for h in history[-8:]
    )
    history_block = f"Недавняя переписка:\n{history_text}" if history_text else ""
    current = (
        f"Цвета: основной {brand_config.PRIMARY_COLOR}, фон {brand_config.BACKGROUND_COLOR}.\n"
        f"Стиль картинок: {brand_config.IMAGE_STYLE}.\n"
        f"Тон текста постов: {settings.get('text_tone') or 'обычный живой разговорный (по умолчанию)'}.\n"
        f"Новостей за один запуск: {config.MAX_NEWS_PER_RUN}.\n"
        f"RSS-ленты: {', '.join(config.RSS_URLS)}."
    )
    return f"""Ты — ассистент, который управляет оформлением и настройками
Telegram-канала с футбольными новостями по переписке с его владельцем.

Текущие настройки канала:
{current}

{history_block}

Новое сообщение от владельца: "{user_text}"

Разберись, чего хочет владелец, и ответь СТРОГО валидным JSON без пояснений
и без markdown-разметки, по такой схеме:
{{
  "reply": "короткий дружелюбный ответ владельцу по-русски",
  "category": "style" (цвета/стиль картинок) | "avatar" (сменить аватарку) |
              "tone" (тон/стиль текста постов) | "feed" (частота публикаций
              или список RSS-лент) | "chat" (обычный разговор, не про настройки),
  "options": null или список из 2-3 объектов {{"label": "короткое описание
              варианта по-русски", "patch": {{...}}}} — patch нужен только
              для category "style"/"tone"/"feed", ключи patch: primary_color
              и background_color (HEX, для style), image_style (текстовое
              описание стиля фото, для style), text_tone (текстовая
              инструкция для style текста, для tone), rss_urls (список
              строк-ссылок) или max_news_per_run (целое число) (для feed),
  "avatar_prompts": null или список из 2-3 коротких уточнений НА РУССКОМ для
              промпта генерации картинки (только для category "avatar"),
              например "мяч в каплях дождя на газоне" — БЕЗ упоминания лиц,
              командной формы с номерами и текста на картинке.
}}

Если сообщение не про настройки канала (вопрос, реплика, разговор) — верни
category "chat", "options": null, "avatar_prompts": null, и просто ответь
по-человечески в "reply". Числа и слова вроде "1"/"второй" без контекста сюда
не попадут — такие ответы на уже предложенные варианты перехватываются раньше."""


def _menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📰 Опубликовать новости сейчас", callback_data="publish")],
        [InlineKeyboardButton("🖼 Сменить аватарку", callback_data="avatar_now")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("🎨 Оформление / тон / ленты", callback_data="style")],
    ])


async def _send_menu(bot: Bot, chat_id: int) -> None:
    await bot.send_message(chat_id=chat_id, text="Что сделать?", reply_markup=_menu_keyboard())


async def _handle_callback(bot: Bot, chat_id: int, action: str) -> None:
    """Обрабатывает нажатие кнопки меню — те же действия, что и ручной запуск
    main.py / avatar_manager.py / stats.py, только без похода на вкладку Actions."""
    if action == "publish":
        await bot.send_message(chat_id=chat_id, text="Проверяю ленты…")
        published = await news_main.main()
        text = f"Готово ✅ Опубликовано новостей: {published}." if published else "Готово, новых новостей не нашлось."
        await bot.send_message(chat_id=chat_id, text=text)
    elif action == "avatar_now":
        await bot.send_message(chat_id=chat_id, text="Генерирую новую аватарку…")
        ok = await avatar_manager.set_channel_avatar()
        text = "Готово, аватарка обновлена ✅" if ok else "Не получилось — провайдер картинок сейчас недоступен, попробуй позже."
        await bot.send_message(chat_id=chat_id, text=text)
    elif action == "stats":
        await stats.send_stats()
    elif action == "style":
        await bot.send_message(
            chat_id=chat_id,
            text="Напиши, что хочешь поменять — цвета, стиль картинок, тон текста, "
                 "частоту публикаций или RSS-ленты — и я предложу варианты.",
        )


async def _apply_avatar_choice(bot: Bot, option: dict) -> str:
    image_bytes = image_generator.generate_image(option["prompt"], seed=option["seed"])
    if not image_bytes:
        return "Не получилось перегенерировать картинку — попроси сменить аватарку ещё раз."
    try:
        image_bytes = image_processor.apply_logo_only(image_bytes)
    except Exception as e:
        print(f"Не удалось наложить логотип на аватарку: {e}")
    await bot.set_chat_photo(chat_id=config.CHANNEL_ID, photo=image_bytes)
    return "Готово, поставил новую аватарку ✅"


async def _offer_avatar_options(bot: Bot, chat_id: int, prompts: list) -> list:
    """Генерирует и присылает превью аватарок, возвращает список pending-вариантов."""
    options = []
    for i, extra in enumerate(prompts[:3], start=1):
        seed = random.randint(1, 999_999)
        prompt = brand_config.build_avatar_prompt(extra)
        image_bytes = image_generator.generate_image(prompt, seed=seed)
        if not image_bytes:
            continue
        await bot.send_photo(chat_id=chat_id, photo=image_bytes, caption=f"Вариант {i}")
        options.append({"label": str(i), "prompt": prompt, "seed": seed})
    return options


async def _handle_message(bot: Bot, chat_id: int, state: dict, settings: dict, user_text: str) -> None:
    if user_text.strip().lower() in MENU_TRIGGERS:
        state["pending"] = None
        await _send_menu(bot, chat_id)
        return

    pending = state.get("pending")

    if pending:
        idx = _parse_choice(user_text, len(pending["options"]))
        if idx is not None:
            chosen = pending["options"][idx]
            if pending["kind"] == "avatar":
                reply = await _apply_avatar_choice(bot, chosen)
            else:
                settings.update(chosen["patch"])
                bot_settings.save(settings)
                reply = f"Готово, применил: «{chosen['label']}» ✅"
            await bot.send_message(chat_id=chat_id, text=reply)
            state["pending"] = None
            return
        # сообщение не похоже на выбор варианта — считаем, что владелец
        # передумал, и разбираем его как новую свободную команду
        state["pending"] = None

    raw = gemini_client.generate(
        _decision_prompt(user_text, settings, state.get("history", [])), json_mode=True
    )
    if raw is None:
        await bot.send_message(chat_id=chat_id, text="Не расслышал — Gemini сейчас недоступен, попробуй чуть позже.")
        return
    try:
        decision = json.loads(raw)
    except json.JSONDecodeError:
        await bot.send_message(chat_id=chat_id, text="Не понял, переформулируй, пожалуйста.")
        return

    history = state.setdefault("history", [])
    history.append({"role": "user", "text": user_text})
    reply_text = decision.get("reply") or "Окей."
    category = decision.get("category")

    if category == "avatar" and decision.get("avatar_prompts"):
        await bot.send_message(chat_id=chat_id, text=reply_text)
        options = await _offer_avatar_options(bot, chat_id, decision["avatar_prompts"])
        if options:
            await bot.send_message(chat_id=chat_id, text="Какой вариант поставить? Напиши номер.")
            state["pending"] = {"kind": "avatar", "options": options}
        else:
            await bot.send_message(chat_id=chat_id, text="Не получилось сгенерировать картинки, попробуй чуть позже.")
    elif decision.get("options"):
        opts = decision["options"][:3]
        lines = [reply_text, ""] + [f"{i}. {o['label']}" for i, o in enumerate(opts, start=1)]
        await bot.send_message(chat_id=chat_id, text="\n".join(lines))
        state["pending"] = {
            "kind": "settings",
            "options": [{"label": o["label"], "patch": o.get("patch") or {}} for o in opts],
        }
    else:
        await bot.send_message(chat_id=chat_id, text=reply_text)

    history.append({"role": "bot", "text": reply_text})
    state["history"] = history[-MAX_HISTORY:]


async def run() -> None:
    if not config.ADMIN_CHAT_ID:
        print("ADMIN_CHAT_ID не задан — переписка с ботом отключена (не с кем сверить, что это владелец).")
        return

    admin_chat_id = int(config.ADMIN_CHAT_ID)
    state = _load_state()
    settings = bot_settings.load()

    async with Bot(token=config.TELEGRAM_TOKEN) as bot:
        updates = await bot.get_updates(
            offset=state["last_update_id"] + 1, timeout=0, allowed_updates=["message", "callback_query"]
        )
        for update in updates:
            state["last_update_id"] = update.update_id

            if update.callback_query:
                query = update.callback_query
                if query.message is None or query.message.chat_id != admin_chat_id:
                    continue
                try:
                    # Ответ на нажатие ("часики" исчезают) годен недолго — Telegram
                    # отклоняет answer() с "query is too old", если между нажатием и
                    # опросом (раз в 5 минут) прошло больше минуты. Само действие
                    # это не должно останавливать — query.data всё ещё рабочий,
                    # поэтому answer() — best-effort и в отдельном try, а не первым
                    # шагом внутри общего try, который раньше обрывал всё нажатие.
                    try:
                        await query.answer()
                    except Exception:
                        pass
                    await _handle_callback(bot, admin_chat_id, query.data)
                except Exception as e:
                    print(f"Не удалось обработать нажатие кнопки: {e}")
                    await bot.send_message(chat_id=admin_chat_id, text="Что-то пошло не так, попробуй ещё раз.")
                continue

            message = update.message
            if not message or not message.text or message.chat_id != admin_chat_id:
                continue
            try:
                await _handle_message(bot, admin_chat_id, state, settings, message.text)
            except Exception as e:
                print(f"Не удалось обработать сообщение владельца: {e}")
                await bot.send_message(chat_id=admin_chat_id, text="Что-то пошло не так, попробуй ещё раз.")

    _save_state(state)


if __name__ == "__main__":
    asyncio.run(run())
