# 🔭 TechRadar AI

> **Принцип: публикуй МЕНЬШЕ, но ЛУЧШЕ. Качество важнее количества.**

Полностью автоматизированная система контент-дистрибуции для AI и dev-инструментов.  
Собирает тренды, жёстко фильтрует их, генерирует посты через бесплатные LLM и одновременно публикует на несколько платформ.

---

## Платформы

| Канал | Язык | Формат |
|---|---|---|
| 📱 Telegram | Русский | Короткий пост + карточка-изображение |
| 📷 Instagram | Английский | Пост с карточкой + хэштеги |
| 🌐 Website (GitHub Pages) | Английский | Полная статья |
| 🟠 Reddit *(позже)* | Английский | Пост в r/MachineLearning и др. |
| 🐦 Twitter/X *(позже)* | Английский | Тред 3–5 твитов |
| 💼 LinkedIn *(позже)* | Английский | Профессиональный пост |

---

## Как это работает

```
[Коллекторы: GitHub, HN, HuggingFace, ArXiv]
        ↓
[Stage 1: Жёсткая предварительная фильтрация]
  — отбрасывает туториалы, "awesome" списки, слишком мало звёзд
        ↓
[Stage 2: LLM-судья (Groq, бесплатно)]
  — ставит оценку 0–100, одобряет только ≥ 85
  — ожидаемый процент отклонения: 70–85%
        ↓
[Генерация контента (OpenRouter, бесплатные модели)]
  — Telegram: русский пост
  — Instagram: подпись + хэштеги
  — Website: SEO-статья 300–400 слов
        ↓
[Генерация изображения 1080×1080 (Pillow)]
        ↓
[Публикация параллельно на все включённые каналы]
        ↓
[Сохранение в SQLite: дедупликация, история]
```

**Максимум 3 публикации в день.** Лучше молчать, чем публиковать шум.

---

## Быстрый старт

### 1. Клонировать репозиторий

```bash
git clone https://github.com/nebula387/TechRadar.git
cd TechRadar
```

### 2. Установить зависимости

```bash
pip install -r requirements.txt
```

### 3. Настроить переменные окружения

```bash
cp .env.example .env
# Открыть .env и заполнить ключи
```

Минимальный набор для старта:
- `TELEGRAM_BOT_TOKEN` — токен бота (получить у [@BotFather](https://t.me/botfather))
- `TELEGRAM_CHANNEL_ID` — username канала (`@mychannel`) или numeric ID
- `GROQ_API_KEY` — [console.groq.com](https://console.groq.com/) (бесплатно)
- `OPENROUTER_API_KEY` — [openrouter.ai](https://openrouter.ai/) (бесплатно)

### 4. Запустить один раз (тест)

```bash
python -m app.main --source github
```

### 5. Запустить по расписанию (daemon)

```bash
python -m app.main --schedule
```

Расписание (UTC):
- 09:00 — GitHub
- 13:00 — HuggingFace  
- 17:00 — HackerNews
- 21:00 — ArXiv

---

## Настройка GitHub Actions (автоматический запуск)

### 1. Создать публичный репозиторий на GitHub

Уже готово: `https://github.com/nebula387/TechRadar`

### 2. Добавить секреты в GitHub

Перейти: **Settings → Secrets and variables → Actions → New repository secret**

| Секрет | Описание |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен Telegram-бота |
| `TELEGRAM_CHANNEL_ID` | ID/username канала |
| `GROQ_API_KEY` | Groq API ключ |
| `OPENROUTER_API_KEY` | OpenRouter API ключ |
| `GH_TOKEN` | GitHub Personal Access Token (для повышения rate limit) |
| `INSTAGRAM_ACCESS_TOKEN` | Токен Instagram Graph API *(опционально)* |
| `INSTAGRAM_ACCOUNT_ID` | ID Instagram бизнес-аккаунта *(опционально)* |

### 3. Добавить переменные (Variables)

Перейти: **Settings → Secrets and variables → Actions → Variables tab**

| Переменная | Значение |
|---|---|
| `WEBSITE_BASE_URL` | `https://nebula387.github.io/TechRadar` |
| `ENABLE_INSTAGRAM` | `false` (включить после настройки) |

### 4. Включить GitHub Pages

Перейти: **Settings → Pages**
- Source: **GitHub Actions**

После первого запуска пайплайна сайт будет доступен по адресу:  
`https://nebula387.github.io/TechRadar`

### 5. Первый ручной запуск

Перейти: **Actions → TechRadar AI Pipeline → Run workflow**

---

## Настройка Instagram

Instagram требует Meta Developer App и бизнес-аккаунт.

1. Создать приложение на [developers.facebook.com](https://developers.facebook.com/)
2. Подключить Instagram Business Account к Facebook Page
3. Добавить продукт "Instagram Graph API"
4. Получить `INSTAGRAM_ACCOUNT_ID` (числовой ID аккаунта)
5. Получить долгосрочный `INSTAGRAM_ACCESS_TOKEN` (действителен 60 дней, нужно обновлять)
6. Установить `ENABLE_INSTAGRAM=true` в `.env` или переменных GitHub

> **Важно:** Instagram требует, чтобы изображение было доступно по публичному URL.  
> Это работает автоматически после деплоя сайта на GitHub Pages.

---

## Структура проекта

```
TechRadar/
├── app/
│   ├── collectors/        # GitHub, HN, HuggingFace, ArXiv, ProductHunt
│   ├── filter/            # Двухступенчатая фильтрация
│   │   ├── quality_gate.py   # Stage 1: жёсткие правила (без LLM)
│   │   └── llm_judge.py      # Stage 2: LLM-оценка (Groq)
│   ├── llm/               # Клиент + генерация контента
│   ├── image/             # Карточки 1080×1080 (Pillow)
│   ├── publishers/        # Telegram, Instagram, Website
│   ├── database/          # SQLite: дедупликация, история
│   ├── scheduler/         # APScheduler: 4 цикла в день
│   ├── pipeline.py        # Главный пайплайн
│   └── main.py            # CLI точка входа
├── website/
│   ├── static/            # Исходники CSS/JS
│   └── public/            # Генерируемый сайт (деплоить эту папку)
│       ├── index.html
│       ├── posts/         # Статьи
│       ├── images/        # Карточки
│       ├── css/
│       └── js/
├── tests/                 # Юнит-тесты
├── data/                  # SQLite БД + логи (gitignored частично)
├── .env.example
├── requirements.txt
└── .github/workflows/
    ├── pipeline.yml       # Основной пайплайн (cron + manual)
    └── tests.yml          # Тесты при каждом пуше
```

---

## Запуск тестов

```bash
pytest tests/ -v
```

---

## LLM модели (только бесплатные)

**Groq** (быстро, для фильтрации):
- `llama-3.3-70b-versatile` — основная

**OpenRouter** (генерация, суффикс `:free`):
- `mistralai/mistral-7b-instruct:free` — основная
- `google/gemma-2-9b-it:free` — резерв
- `meta-llama/llama-3.1-8b-instruct:free` — резерв

Правило: если квота исчерпана — пропустить публикацию, залогировать, повторить в следующем цикле.

---

## Переменные окружения

| Переменная | Описание | По умолчанию |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен бота | — |
| `TELEGRAM_CHANNEL_ID` | ID канала | — |
| `GITHUB_TOKEN` | GitHub PAT (rate limit) | — |
| `GROQ_API_KEY` | Groq API key | — |
| `GROQ_MODEL` | Groq модель | `llama-3.3-70b-versatile` |
| `OPENROUTER_API_KEY` | OpenRouter API key | — |
| `OPENROUTER_MODEL` | OpenRouter модель | `mistralai/mistral-7b-instruct:free` |
| `INSTAGRAM_ACCESS_TOKEN` | Instagram токен | — |
| `INSTAGRAM_ACCOUNT_ID` | Instagram аккаунт ID | — |
| `MIN_SCORE` | Минимальный скор для публикации | `85` |
| `MAX_POSTS_PER_DAY` | Максимум публикаций в день | `3` |
| `ENABLE_TELEGRAM` | Включить Telegram | `true` |
| `ENABLE_INSTAGRAM` | Включить Instagram | `false` |
| `ENABLE_WEBSITE` | Включить сайт | `true` |
| `WEBSITE_BASE_URL` | URL сайта | `https://nebula387.github.io/TechRadar` |
| `WEBSITE_OUTPUT_DIR` | Папка вывода сайта | `./website/public` |

---

## Добавление новых каналов позже

Для Reddit, Twitter, LinkedIn — нужно:
1. Установить `ENABLE_REDDIT=true` / `ENABLE_TWITTER=true` / `ENABLE_LINKEDIN=true` в `.env`
2. Добавить соответствующие API-ключи
3. Раскомментировать публишеры в `app/publishers/`
4. Добавить в список в `app/pipeline.py`

---

## Лицензия

MIT — свободное использование для любых целей.
