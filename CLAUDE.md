# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Telegram bot that autoposts sports news to `@xg_or_not`: pulls RSS feeds
(English-language sources), rewrites the text into casual Russian via
Gemini, generates a photorealistic branded AI image for each new item,
overlays the headline and logo, and publishes the post — no source link,
by requirement. Also rotates the channel avatar weekly and can report
weekly post stats to the owner's DM. The owner can also just chat with
the bot in DM to change channel style/tone/avatar/feed settings — see
"Owner chat control" below. Runs serverless — four independent GitHub
Actions workflows, no long-running process or host of its own.

**Posts are Russian-only, hard requirement — not "prefer Russian, fall
back to English".** If `text_rewriter.rewrite()` returns `None` (no
`GEMINI_API_KEY` or the call fails), `publish_news()` skips the item
entirely rather than posting the original English RSS text; the link
isn't added to history, so it's retried on the next scheduled run.
Practical implication: **without a working `GEMINI_API_KEY`, the bot
publishes nothing, silently, forever** — that's by design, not a bug to
"fix" by adding an English fallback back in.

This project is fully isolated from the other bots in the parent workspace
— its own history file, own `.env`, own git repo. `@xg_or_not` previously
belonged to `football-cards-bot`, which has since been deleted; see the
root workspace `CLAUDE.md` for that history.

## Commands

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in TELEGRAM_TOKEN, CHANNEL_ID, RSS_URLS
python main.py          # one run: check RSS feeds, publish anything new
python avatar_manager.py  # generate + set a new channel avatar
python stats.py           # print/DM a 7-day post count
python admin_agent.py     # one run: check owner DM for new messages, act on them
```

No test suite, linter, or build step exists in this repo yet.

## Architecture

Each module has exactly one job. `main.py`, `avatar_manager.py`,
`stats.py` and `admin_agent.py` are four independent entry points, each
its own GitHub Actions workflow — there is no in-process scheduler and no
long-running bot process; see "Owner chat control" below for how that's
reconciled with a real back-and-forth conversation.

- `config.py` — all runtime settings read from environment variables
  (Telegram token/channel, RSS feed list, which image/text provider to
  use, optional `ADMIN_CHAT_ID` for DMs). Loads `.env` via `python-dotenv`
  if present; on GitHub Actions the same variables come from repo
  Secrets/Variables instead. `RSS_URLS` and `MAX_NEWS_PER_RUN` are
  overridden by `bot_settings.load()` first if the owner changed them via
  chat — see `bot_settings.py`.
- `brand_config.py` — the brand book (colors, font, logo path, image style)
  plus `build_image_prompt()`, which turns a headline into the prompt sent
  to the image generator, and `build_avatar_prompt(extra="")`, the same
  idea for the channel avatar (shared by `avatar_manager.py`'s default
  weekly rotation and `admin_agent.py`'s chat-driven avatar preview flow).
  Both prompts explicitly tell the model *not* to render text — diffusion
  models draw text illegibly, so the headline is drawn separately
  afterward. Also explicitly demand a real photo, not an illustration —
  free image models default toward a painterly/stylized look unless told
  "НЕ рисунок, НЕ мультфильм, НЕ 3D-рендер" etc.; even with that, expect
  an occasional off-topic result (Pollinations has no seed pinning by
  default) — that's an accepted quality trade-off of a free generator,
  not something worth building a verify-and-retry loop for. `PRIMARY_COLOR`,
  `BACKGROUND_COLOR` and `IMAGE_STYLE` are overridden by `bot_settings.load()`
  first, same pattern as `config.py`.
- `bot_settings.py` — `load()`/`save()` for `data/settings.json`, the one
  file `admin_agent.py` writes to change channel behavior (colors, image
  style, text tone, RSS feeds, posts-per-run). Every key defaults to
  `None` ("owner hasn't touched this"), so as long as the owner never
  chats with the bot, every other module's `_overrides["x"] or <old
  default>` pattern is a no-op and behavior is identical to before this
  file existed.
- `gemini_client.py` — the one place that calls the Gemini
  `generateContent` endpoint (`generate(prompt, json_mode=False)`),
  shared by `text_rewriter.py` (plain text) and `admin_agent.py`
  (`json_mode=True`, structured decisions). Returns `None` on missing key
  or any request failure — callers own the degrade behavior.
- `news_parser.py` — parses the configured RSS feeds and filters out
  anything already in `data/published_history.json` (dedup by link).
  History is `{link: iso_timestamp}`; old runs may have left a plain list
  (no timestamps) — `load_history()` upconverts that transparently, treating
  those entries as timestamp-less (excluded from the weekly stats count but
  still deduped correctly). Also unescapes HTML entities feeds sometimes
  double-encode (e.g. Sky Sports serving literal `&#8217;` instead of `’`).
- `text_rewriter.py` — `rewrite(title, summary)` calls `gemini_client` to
  turn the (usually English) RSS text into a short, casual Russian post,
  folding in `bot_settings.load()["text_tone"]` as an extra instruction if
  the owner set one via chat — returns `(title, body)` or `None` if
  Gemini is unset/fails, same graceful-degrade contract as
  `image_generator`. The AI image prompt still uses the *original* title,
  not the Gemini rewrite — diffusion models follow English prompts better.
- `image_generator.py` — `generate_image(prompt, seed=None)` dispatches to
  whichever backend `config.IMAGE_PROVIDER` selects: `pollinations`
  (default, no key needed, the only one that honors `seed`), `huggingface`,
  `cloudflare`, or `none`. Any failure from the backend is caught here and
  turned into `None` — the caller never needs to handle provider-specific
  errors, a missing image is just a normal outcome. `seed` exists so
  `admin_agent.py` can regenerate a near-identical copy of a previously
  shown avatar preview without having to persist image bytes between runs.
- `image_processor.py` — `apply_branding()` draws the headline onto a
  translucent band (Pillow) using the brand font/colors, then overlays the
  logo if `assets/logo.png` exists; `apply_logo_only()` is the same minus
  the headline, used for the avatar (a news headline doesn't belong on a
  channel icon). Both font and logo are optional; missing files fall back
  to Pillow defaults rather than erroring.
- `main.py` — `publish_news()` builds the caption, gets an image (or not),
  brands it (or not), and sends `send_photo`/`send_message` accordingly.
  `main()` limits each run to `MAX_NEWS_PER_RUN` items and only records a
  link in history after a successful publish, so a failed post is retried
  on the next scheduled run rather than being silently dropped. Bot calls
  happen inside `async with Bot(...) as bot:` — see the pool-exhaustion
  note below, this isn't optional decoration.
- `avatar_manager.py` — generates an avatar-appropriate image (square,
  no headline) via `brand_config.build_avatar_prompt()`, logo-overlays it,
  and calls `set_chat_photo`. Independent weekly schedule
  (`.github/workflows/avatar.yml`), no history/dedup needed.
- `stats.py` — counts links in history with a timestamp inside the last 7
  days, DMs the owner if `ADMIN_CHAT_ID` is set, otherwise just prints
  (visible in the Actions log). Manual-trigger-only workflow.
- `admin_agent.py` — see "Owner chat control" below.

## Pitfalls already hit once — don't reintroduce them

- **`Bot(token=...)` must be used as `async with`.** A bare `Bot(...)`
  without entering its async context has connection_pool_size=1 and a
  1-second pool_timeout; sending more than one message in a row reliably
  hangs with "Pool timeout: All connections in the connection pool are
  occupied" on the second/third send. Reproduced live against the real
  channel before the fix — the first attempt silently published nothing.
- **Telegram `parse_mode="HTML"` requires escaping `&`, `<`, `>` in
  *everything* embedded in the caption.** `html.escape()` on title/summary
  before building the caption; the truncation logic (for the 1024-char
  caption limit) escapes first, then strips any trailing partial entity
  left by the cut (`&amp` without `;`) with a regex — truncating
  post-escape text naively can leave a dangling invalid entity. (Captions
  no longer include the source link at all — dropped by requirement — but
  the escaping lesson generalizes to any text field, keep it.)
- **`os.environ.get(key, default)` does not protect you on GitHub
  Actions.** An unset repository Secret/Variable referenced as
  `${{ secrets.X }}` / `${{ vars.X }}` in a workflow's `env:` block
  resolves to an *empty string*, not an absent key — so the env var
  arrives in the runner as `X=""`, present but empty. `.get(key, default)`
  only falls back when the key is missing entirely, so it silently returns
  `""` instead of `default`. Caught this live: `int(os.environ.get(
  "MAX_NEWS_PER_RUN", "3"))` crashed the very first cloud run with
  `ValueError: invalid literal for int() with base 10: ''`, and the same
  pattern in `brand_config.py` would have broken image generation the
  same way once those (never-created) repo Variables were referenced.
  Fix used throughout both files: `os.environ.get(key) or default`.

## Owner chat control — polling, not webhook, and why

The owner can DM the bot free-form requests ("сделай оформление ярче",
"смени аватарку", "постим реже") and get back 2-3 concrete options with
a working preview (for avatar changes, real generated images); replying
with a number applies the choice. This looks like it needs a live,
always-listening bot process (real inline keyboards do), but it doesn't:
`admin_agent.py` calls `Bot.get_updates(offset=...)` — a pull, not a
push — once per run, so it fits the same "wake up, do one pass, exit"
shape as every other workflow here. `.github/workflows/admin_chat.yml`
runs it every 5 minutes via `workflow_dispatch`+`schedule`, trading up to
~5 minutes of reply latency for zero hosting cost. This *is* a reversal
of an earlier decision to skip live buttons entirely (see git history) —
the owner explicitly asked for conversational control and chose polling
frequency knowingly; don't reintroduce that old "no interactivity"
stance without checking with them again.

Two things this design depends on, don't break them separately:
- **The repo must stay public.** Every-5-minutes cron on a private repo
  would burn the free Actions minutes budget fast (hourly `main.py` runs
  already use a good chunk of it); public repos have no minutes cap.
  Secrets stay hidden regardless of repo visibility — going public was
  about Actions minutes, not secret exposure.
- **`admin_agent.py` no-ops entirely if `ADMIN_CHAT_ID` is unset**, and
  ignores any message whose `chat_id` doesn't match it. This is the only
  thing standing between "owner-only control" and "first stranger who
  finds the bot's username in this public repo can repaint the channel" —
  don't relax that check.

State lives in two files `admin_agent.py` commits back to the repo (same
pattern `main.py` uses for `data/published_history.json`):
`data/admin_state.json` (`last_update_id` so old messages aren't
reprocessed, a short rolling conversation history for Gemini context, and
`pending` — the options currently on offer, if any) and `data/settings.json`
(the actual applied overrides, via `bot_settings.py`). Avatar options are
never persisted as image bytes — `pending.options[i]` stores the prompt
and a random `seed` instead, and choosing that option calls
`image_generator.generate_image(prompt, seed=seed)` again to reproduce
essentially the same picture (Pollinations honors `seed` deterministically
enough for this).

Gemini decides everything through one JSON-mode call per incoming
message (`admin_agent._decision_prompt`) — category, a reply string, and
either `options` (settings patches) or `avatar_prompts` (image prompt
variations). No hand-coded intent classifier; letting the model decide is
deliberately lazier than building one, and matches what was asked for
("веди себя как полноценная нейросеть"). Numeric replies to an open
`pending` proposal are intercepted by `_parse_choice()` *before* any
Gemini call — cheaper, and doesn't depend on the model recognizing "2" as
a selection instead of a new topic. `_parse_choice()` also bails out
(returns `None`) on anything longer than 4 words — a long message that
happens to contain "второй" (e.g. "Второй месяц веду канал, добавь
эмодзи") must not be silently treated as picking option 2 instead of
being read as a new request.

### Real Telegram buttons (inline keyboard), same polling mechanism

`/start`, "меню" or "кнопки" sends an `InlineKeyboardMarkup` with four
buttons (`_menu_keyboard()`): publish now, change avatar now, stats,
"talk to me about settings". Button taps arrive as `callback_query`
updates through the *same* `get_updates()` call as text messages
(`allowed_updates=["message", "callback_query"]`) — no separate
infrastructure needed, this is still one pull every 5 minutes.
`_handle_callback()` doesn't trigger a GitHub Actions workflow or need a
GitHub PAT; it just calls the existing entry-point functions in-process:
`main.main()` (imported as `news_main` to avoid shadowing `admin_agent`'s
own concerns), `avatar_manager.set_channel_avatar()`,
`stats.send_stats()`. `main.main()` now returns the published count
(previously `None`) so the button's confirmation message can say "0
опубликовано" honestly instead of always claiming success. Because the
publish button can now touch `data/published_history.json` from *this*
workflow too, `admin_chat.yml`'s commit step commits that file as well as
`admin_state.json`/`settings.json`, and `admin_chat.yml`'s env block was
brought to parity with `telegram_bot.yml` (`RSS_URLS`, `MAX_NEWS_PER_RUN`,
`BRAND_*`) — the publish button exercises the exact same code path as the
hourly run and needs the same inputs.

## Image/text providers deliberately NOT integrated

An earlier task briefly asked for "Agnes AI", "Goblin AI", "FreeTheAi",
"tteg" and a "Stockio REST API". Checked each: Stockio has no API at all
(site-only downloads), tteg/FreeTheAi are single-maintainer unofficial
proxies sitting in front of other platforms' APIs (fragile, possible ToS
issues, no accountability), Agnes AI/Goblin AI are small unverified
packages targeting AI coding agents specifically. None are wired in.
Only official free tiers are used: Pollinations, Hugging Face, Cloudflare
Workers AI, Gemini (Google AI Studio).
