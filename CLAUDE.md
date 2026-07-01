# TechRadar AI — CLAUDE.md

## Project Vision

Build a fully automated, multi-platform content system called **TechRadar AI**.
The system discovers trending tech content, rigorously filters it for quality,
and distributes polished posts across multiple channels simultaneously.

**Core principle: publish LESS but BETTER. Quality over quantity.**

---

## Output Channels

| Channel | Language | Format | Status |
|---|---|---|---|
| Telegram Channel (`@ai_tech_radar`) | Russian 🇷🇺 | Short post + image card | ✅ Live |
| Website (GitHub Pages) | English 🇬🇧 + RU descriptions | Full article page | ✅ Live |
| Reddit | English 🇬🇧 | Post to r/MachineLearning etc. | 🔜 Later |
| X (Twitter) | English 🇬🇧 | Thread (3–5 tweets) | 🔜 Later |
| LinkedIn | English 🇬🇧 | Professional post | 🔜 Later |

Website: `https://nebula387.github.io/TechRadar`

---

## Tech Stack

- **Language:** Python 3.12+
- **HTTP:** `httpx` (async)
- **Data validation:** `pydantic v2` + `pydantic-settings`
- **Database:** `SQLite` via raw `sqlite3`
- **Scheduler:** `APScheduler`
- **LLM (filter):** NVIDIA NIM (primary) → Groq (fallback) — free tier
- **LLM (generation):** OpenRouter (primary) → NVIDIA NIM (fallback) — free models
- **Image cards:** `Pillow` — 1080×1080, pixel-accurate text wrapping
- **Website:** static HTML rebuilt at deploy time from `feed.json`
- **Publishing:** Telegram Bot API
- **Config:** `.env` via `python-dotenv`
- **CI/CD:** GitHub Actions (4×/day cron + manual dispatch)

### LLM Models in Use

**NVIDIA NIM (primary for filtering and fallback for generation):**
- `meta/llama-3.3-70b-instruct` (free credits on signup at build.nvidia.com)

**Groq (fallback for filtering):**
- `qwen/qwen3.6-27b` (free tier, strict TPM limits; replaces deprecated llama-3.3-70b-versatile)

**OpenRouter (primary for content generation):**
- `google/gemma-2-9b-it:free`

**Rule:** Never use paid models. On quota exhaustion — skip, log, retry next cycle.

---

## Project Structure

```
techradar-ai/
├── app/
│   ├── collectors/
│   │   ├── base.py                  # Abstract BaseCollector
│   │   ├── github.py                # GitHub Search API
│   │   ├── github_trending.py       # Scrapes github.com/trending (BeautifulSoup4)
│   │   ├── huggingface.py
│   │   ├── producthunt.py
│   │   ├── hackernews.py
│   │   └── arxiv.py
│   │
│   ├── filter/
│   │   ├── quality_gate.py          # Stage 1: hard rules, no LLM
│   │   └── llm_judge.py             # Stage 2: BATCH LLM evaluation (1 API call)
│   │
│   ├── llm/
│   │   ├── client.py                # NVIDIA→Groq (filter), OpenRouter→NVIDIA (gen)
│   │   └── generate.py              # Telegram RU + Instagram + Website EN
│   │
│   ├── image/
│   │   └── card.py                  # Pillow 1080×1080, _wrap_pixels() for layout
│   │
│   ├── publishers/
│   │   ├── base.py
│   │   ├── telegram.py              # channel ID normalized (t.me/ → @username)
│   │   ├── instagram.py
│   │   └── website.py               # writes feed.json + images; HTML built at deploy
│   │
│   ├── database/
│   │   └── storage.py               # SQLite dedup, daily count, pending items
│   │
│   ├── scheduler/
│   │   └── scheduler.py
│   │
│   ├── models.py
│   ├── config.py
│   ├── pipeline.py                  # main flow: collect→filter→generate→publish
│   ├── main.py                      # CLI: --source, --dry-run, --schedule
│   ├── bot.py                       # Telegram approval bot + --clear-channel
│   ├── manage.py                    # DB admin: list / clear / stats
│   └── rebuild_website.py           # Regenerates all HTML from feed.json
│
├── website/
│   ├── static/
│   │   ├── css/style.css
│   │   └── js/main.js
│   └── public/                      # .gitignore: posts/, index.html (rebuilt at deploy)
│       ├── feed.json                # ✅ committed — source of truth for all posts
│       └── images/                  # ✅ committed — PNG cards
│
├── data/
│   ├── techradar.db                 # ✅ committed — dedup + daily count
│   └── images/                      # .gitignore — local working copies
│
├── test_card.py                     # Visual test: generates 3 sample cards locally
├── .env.example
├── requirements.txt
└── CLAUDE.md
```

---

## LLM Chain (Important!)

```
Filtering (llm_judge.py):
  NVIDIA NIM  ──(fail)──►  Groq

Generation (generate.py):
  OpenRouter  ──(fail)──►  NVIDIA NIM

Batch evaluation: ALL candidates sent in ONE API call
  - pipeline.py caps candidates at top 12 by stars
  - llm_judge.py splits into chunks of 10 max
  - 1 Groq call replaces up to 12 sequential calls (avoids 429 rate limits)

Retry policy (client.py):
  - 429: wait min(Retry-After, 120s), max 4 retries
  - 4xx (bad model/key): fail immediately, no retry
  - Timeout: 90s per request
```

---

## Website Architecture (Rebuild-at-Deploy)

**Key principle:** HTML is never committed to git. Only data is.

```
run-pipeline job:
  collect → filter → LLM → generate → publish
  git commit: feed.json + images/ + techradar.db

deploy-pages job:
  git checkout main
  python -m app.rebuild_website     ← regenerates ALL HTML from feed.json
  deploy to GitHub Pages
```

**Result:** Any code fix (design, layout, text) automatically applies to ALL
historical posts on the next deploy. No manual reset needed.

**`feed.json` entry structure:**
```json
{
  "title": "...",           "slug": "...",
  "url": "...",             "source_url": "...",
  "description": "...",     ← Russian (from telegram_text_ru)
  "body_en": "...",         ← English full article (for post page rebuild)
  "category": "...",        "score": 90,
  "emoji": "🚀",            "accent_color": "#6366f1",
  "source": "github_trending",
  "date": "2026-06-22",    "image_url": "...",
  "tags": [...]
}
```

---

## Content Quality Filter

### Stage 1 — Hard Pre-filter (`filter/quality_gate.py`)

- GitHub Trending: `stars_today >= 50` OR `total stars >= 500`
- HackerNews: score > 200
- ProductHunt: upvotes > 100
- Reject: description < 30 chars, title contains "tutorial" or "awesome-"
- Reject: already published (dedup via SQLite)

### Stage 2 — LLM Batch Judge (`filter/llm_judge.py`)

Single API call with all candidates → JSON array response. Score ≥ 85 to approve.
Expected rejection rate: 70–85%.

---

## Data Flow

```
[Collectors] → List[RawItem]
     ↓
[Stage 1: Hard pre-filter] → top 12 by stars
     ↓
[Stage 2: LLM batch judge — 1 API call] → score ≥ 85
     ↓
[Generate content — asyncio.gather()]
  ├── telegram_text_ru  (OpenRouter→NVIDIA)
  ├── instagram_caption (OpenRouter→NVIDIA)
  └── website_title + body_en (OpenRouter→NVIDIA)
     ↓
[Generate image card — Pillow, pixel-accurate wrapping]
     ↓
[Publish]
  ├── Telegram (Russian) — @ai_tech_radar
  └── Website — feed.json + images/ committed to git
     ↓
[SQLite: mark published, store message IDs]
```

---

## CLI Reference

```bash
# Run pipeline
python -m app.main --source github_trending
python -m app.main --source all
python -m app.main --dry-run --source github_trending   # no publish, sends preview to admin bot

# Telegram admin bot
python -m app.bot                      # start approval polling loop
python -m app.bot --test               # verify bot connection
python -m app.bot --clear-channel      # delete all messages from channel (admin only)
python -m app.bot --pending            # list pending items

# Database admin
python -m app.manage stats             # show DB stats
python -m app.manage list              # list published records
python -m app.manage clear             # delete all records (re-publish on next run)
python -m app.manage clear --date 2026-06-22   # delete specific date

# Website
python -m app.rebuild_website          # rebuild all HTML from feed.json
python test_card.py                    # generate 3 test cards to data/test_cards/
```

---

## Environment Variables

```
# Telegram
TELEGRAM_BOT_TOKEN=           # from @BotFather
TELEGRAM_CHANNEL_ID=          # @channelname or -100xxx numeric ID (NOT t.me/ URL)
TELEGRAM_ADMIN_CHAT_ID=       # your personal chat ID (from @userinfobot)
ENABLE_APPROVAL_MODE=false    # true = send preview to admin before publishing

# GitHub
GITHUB_TOKEN=                 # optional, raises API limit 60→5000 req/hr

# LLM — free only
GROQ_API_KEY=                 # console.groq.com
GROQ_MODEL=llama-3.3-70b-versatile
NVIDIA_API_KEY=               # build.nvidia.com (primary — more generous limits)
NVIDIA_MODEL=meta/llama-3.3-70b-instruct
OPENROUTER_API_KEY=           # openrouter.ai
OPENROUTER_MODEL=google/gemma-2-9b-it:free

# Quality
MIN_SCORE=85
MAX_POSTS_PER_DAY=3

# Channels
ENABLE_TELEGRAM=true
ENABLE_WEBSITE=true
ENABLE_INSTAGRAM=false
ENABLE_REDDIT=false
ENABLE_TWITTER=false
ENABLE_LINKEDIN=false

# Website
WEBSITE_OUTPUT_DIR=./website/public
WEBSITE_BASE_URL=https://nebula387.github.io/TechRadar
```

---

## GitHub Actions Workflow

**Cron:** 09:00 / 13:00 / 17:00 / 21:00 UTC

**`run-pipeline` job** (timeout: 15 min):
- Runs pipeline, commits `feed.json` + `images/` + `techradar.db`
- `cancel-in-progress: true` — kills stuck runs on new push

**`deploy-pages` job** (runs after pipeline, `if: always()`):
- Checks out latest main
- Runs `rebuild_website.py` — regenerates all HTML with latest code
- Deploys to GitHub Pages

**Manual trigger** (`workflow_dispatch`):
- `source`: which collector to run (default: `github_trending`)
- `enable_telegram`: `true`/`false` — useful for rebuilds without re-posting

---

## GitHub Secrets Required

| Secret | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `TELEGRAM_CHANNEL_ID` | Channel username e.g. `@ai_tech_radar` |
| `TELEGRAM_ADMIN_CHAT_ID` | Your personal Telegram chat ID |
| `NVIDIA_API_KEY` | NVIDIA NIM API key |
| `GROQ_API_KEY` | Groq API key |
| `OPENROUTER_API_KEY` | OpenRouter API key |

---

## Notes for Claude Code

- **Never hardcode API keys**
- **LLM calls are BATCH** — never loop `judge_item()` per item, use `judge_items()`
- **Channel ID format:** always normalize to `@username` — never use `t.me/` URLs with Bot API
- **website/public/posts/ and index.html are in .gitignore** — they're rebuilt at deploy
- **feed.json is the source of truth** — it must contain all data needed to rebuild HTML
- **On 4xx LLM errors:** fail immediately (don't retry — model won't reappear)
- **On 429:** cap wait at 120s, then failover to backup provider
- The system publishes up to **3 posts/day to the website**, but only **1 post/day to Telegram** (the top-scored item)

---

## Planned Next Steps

- RSS feed collectors (deferred)
- Reddit, Twitter/X, LinkedIn publishers (deferred)
- Instagram setup (requires Meta Developer App + Business Account)
- GitHub Pages: Settings → Pages → Source → **GitHub Actions** (must be set manually)

---

## Repository

```
git remote add origin git@github.com:nebula387/TechRadar.git
```
