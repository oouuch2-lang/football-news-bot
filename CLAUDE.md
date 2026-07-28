# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Telegram bot that autoposts sports news to `@xg_or_not`: pulls RSS feeds
(English-language sources), rewrites the text into casual Russian via
Gemini, generates a photorealistic branded AI image for each new item,
overlays the headline and logo, and publishes the post — no source link,
by requirement. Also rotates the channel avatar weekly and can report
weekly post stats to the owner's DM. Runs serverless — three independent
GitHub Actions workflows, no long-running process or host of its own.

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
```

No test suite, linter, or build step exists in this repo yet.

## Architecture

Each module has exactly one job. `main.py`, `avatar_manager.py` and
`stats.py` are three independent entry points, each its own GitHub Actions
workflow — there is no in-process scheduler and no live bot process; see
"No live Telegram buttons" below for why.

- `config.py` — all runtime settings read from environment variables
  (Telegram token/channel, RSS feed list, which image/text provider to
  use, optional `ADMIN_CHAT_ID` for DMs). Loads `.env` via `python-dotenv`
  if present; on GitHub Actions the same variables come from repo
  Secrets/Variables instead.
- `brand_config.py` — the brand book (colors, font, logo path, image style)
  plus `build_image_prompt()`, which turns a headline into the prompt sent
  to the image generator. The prompt explicitly tells the model *not* to
  render text — diffusion models draw text illegibly, so the headline is
  drawn separately afterward. Also explicitly demands a real photo, not an
  illustration — free image models default toward a painterly/stylized
  look unless told "НЕ рисунок, НЕ мультфильм, НЕ 3D-рендер" etc.; even
  with that, expect an occasional off-topic result (Pollinations has no
  seed pinning) — that's an accepted quality trade-off of a free
  generator, not something worth building a verify-and-retry loop for.
- `news_parser.py` — parses the configured RSS feeds and filters out
  anything already in `data/published_history.json` (dedup by link).
  History is `{link: iso_timestamp}`; old runs may have left a plain list
  (no timestamps) — `load_history()` upconverts that transparently, treating
  those entries as timestamp-less (excluded from the weekly stats count but
  still deduped correctly). Also unescapes HTML entities feeds sometimes
  double-encode (e.g. Sky Sports serving literal `&#8217;` instead of `’`).
- `text_rewriter.py` — `rewrite(title, summary)` optionally calls the
  Gemini API to turn the (usually English) RSS text into a short, casual
  Russian post — returns `(title, body)` or `None` if `GEMINI_API_KEY` is
  unset or the call fails, same graceful-degrade contract as
  `image_generator`. The AI image prompt still uses the *original* title,
  not the Gemini rewrite — diffusion models follow English prompts better.
- `image_generator.py` — `generate_image(prompt)` dispatches to whichever
  backend `config.IMAGE_PROVIDER` selects: `pollinations` (default, no key
  needed), `huggingface`, `cloudflare`, or `none`. Any failure from the
  backend is caught here and turned into `None` — the caller never needs to
  handle provider-specific errors, a missing image is just a normal outcome.
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
  no headline), logo-overlays it, and calls `set_chat_photo`. Independent
  weekly schedule (`.github/workflows/avatar.yml`), no history/dedup needed.
- `stats.py` — counts links in history with a timestamp inside the last 7
  days, DMs the owner if `ADMIN_CHAT_ID` is set, otherwise just prints
  (visible in the Actions log). Manual-trigger-only workflow.

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

## No live Telegram buttons — architecture constraint, not an oversight

A Telegram inline keyboard needs a process that's alive and polling/
listening for callback updates in real time. This bot's whole design is
the opposite: a script that runs for a minute or two on a schedule and
exits. The two don't compose without paying for (or babysitting) an
always-on host. Chosen resolution: GitHub Actions `workflow_dispatch`
("Run workflow" button on the Actions tab) stands in for what would have
been in-chat buttons — see the table in `README.md`. Don't add
`bot_handlers.py`/long-polling back in without re-deciding this trade-off
with the user first.

## Image/text providers deliberately NOT integrated

An earlier task briefly asked for "Agnes AI", "Goblin AI", "FreeTheAi",
"tteg" and a "Stockio REST API". Checked each: Stockio has no API at all
(site-only downloads), tteg/FreeTheAi are single-maintainer unofficial
proxies sitting in front of other platforms' APIs (fragile, possible ToS
issues, no accountability), Agnes AI/Goblin AI are small unverified
packages targeting AI coding agents specifically. None are wired in.
Only official free tiers are used: Pollinations, Hugging Face, Cloudflare
Workers AI, Gemini (Google AI Studio).
