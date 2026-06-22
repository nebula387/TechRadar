import json
import logging
import shutil
import html
from datetime import datetime
from pathlib import Path
from app.models import GeneratedContent
from app.publishers.base import BasePublisher
from app.config import get_settings

logger = logging.getLogger(__name__)


class WebsitePublisher(BasePublisher):
    channel_name = "website"

    @property
    def is_enabled(self) -> bool:
        return get_settings().enable_website

    async def publish(self, content: GeneratedContent) -> dict:
        s = get_settings()
        out = Path(s.website_output_dir)
        base_url = s.website_base_url.rstrip("/")

        posts_dir = out / "posts"
        images_dir = out / "images"
        css_dir = out / "css"
        js_dir = out / "js"
        for d in (posts_dir, images_dir, css_dir, js_dir):
            d.mkdir(parents=True, exist_ok=True)

        # Copy static assets from source if not already there
        self._copy_static(css_dir, js_dir)

        # Copy image card
        if content.image_path and Path(content.image_path).exists():
            dest = images_dir / f"{content.website_slug}.png"
            shutil.copy2(content.image_path, dest)

        # Write post page
        post_html = self._render_post(content, base_url)
        (posts_dir / f"{content.website_slug}.html").write_text(post_html, encoding="utf-8")

        # Update feed.json
        self._update_feed(out, content, base_url)

        # Rebuild index
        self._rebuild_index(out, base_url)

        url = f"{base_url}/posts/{content.website_slug}.html"
        logger.info(f"Website published: {url}")
        return {"url": url}

    def _copy_static(self, css_dir: Path, js_dir: Path):
        src_css = Path("website/static/css/style.css")
        src_js = Path("website/static/js/main.js")
        if src_css.exists():
            shutil.copy2(src_css, css_dir / "style.css")
        if src_js.exists():
            shutil.copy2(src_js, js_dir / "main.js")

    def _render_post(self, content: GeneratedContent, base_url: str) -> str:
        item = content.item
        esc = html.escape
        img_url = f"{base_url}/images/{content.website_slug}.png" if content.image_path else ""
        img_tag = f'<img class="post-cover" src="{esc(img_url)}" alt="{esc(content.website_title_ru or content.website_title_en)}">' if img_url else ""
        tags_html = "".join(f'<span class="tag">{esc(t)}</span>' for t in content.tags)
        body_ru = content.website_body_ru or content.website_body_en
        body_html = esc(body_ru).replace("\n\n", "</p><p>").replace("\n", "<br>")
        title_ru = content.website_title_ru or content.website_title_en
        date_str = datetime.utcnow().strftime("%d.%m.%Y")

        return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{esc(title_ru)} — TechRadar AI</title>
  <meta name="description" content="{esc(item.description[:160])}">
  <meta property="og:title" content="{esc(title_ru)}">
  <meta property="og:description" content="{esc(item.description[:200])}">
  {f'<meta property="og:image" content="{esc(img_url)}">' if img_url else ""}
  <meta name="twitter:card" content="summary_large_image">
  <link rel="stylesheet" href="{base_url}/css/style.css">
</head>
<body>
  <nav class="navbar">
    <a href="{base_url}" class="logo">&#128301; TechRadar AI</a>
    <span class="nav-tagline">Сигнал, не шум.</span>
  </nav>
  <main class="post-page">
    {img_tag}
    <div class="post-meta">
      <span class="score-badge">Рейтинг {item.score}/100</span>
      <span class="category-badge">{esc(item.category.value)}</span>
      <span class="date">{date_str}</span>
    </div>
    <h1>{esc(item.emoji)} {esc(title_ru)}</h1>
    <div class="tags">{tags_html}</div>
    <div class="post-body"><p>{body_html}</p></div>
    <div class="source-link">
      <a href="{esc(item.url)}" target="_blank" rel="noopener noreferrer">&#8594; Смотреть источник</a>
    </div>
    <div class="post-channels">
      <strong>Также опубликовано в:</strong>
      <a href="https://t.me/ai_tech_radar" target="_blank">Telegram</a>
    </div>
  </main>
  <footer><p>&#169; TechRadar AI &#8212; Работает на ИИ, отобрано по стандартам.</p></footer>
  <script src="{base_url}/js/main.js" defer></script>
</body>
</html>"""

    def _update_feed(self, out: Path, content: GeneratedContent, base_url: str):
        feed_path = out / "feed.json"
        feed: list[dict] = []
        if feed_path.exists():
            try:
                feed = json.loads(feed_path.read_text(encoding="utf-8"))
            except Exception:
                feed = []

        item = content.item
        # Russian excerpt from Telegram post (strip markdown bold markers)
        import re as _re
        tg_clean = _re.sub(r"\*+", "", content.telegram_text_ru or "").strip()
        # Remove the first line (bold title) — keep only the body sentences
        tg_lines = [l.strip() for l in tg_clean.splitlines() if l.strip()]
        excerpt_ru = " ".join(tg_lines[1:])[:220] if len(tg_lines) > 1 else tg_clean[:220]

        entry = {
            "title": content.website_title_en,
            "title_ru": content.website_title_ru,
            "url": f"{base_url}/posts/{content.website_slug}.html",
            "source_url": item.url,
            "description": excerpt_ru,
            "body_en": content.website_body_en,
            "body_ru": content.website_body_ru,
            "category": item.category.value,
            "score": item.score,
            "emoji": item.emoji,
            "accent_color": item.accent_color,
            "source": item.source.value,
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "image_url": f"{base_url}/images/{content.website_slug}.png" if content.image_path else "",
            "tags": content.tags,
            "slug": content.website_slug,
        }
        feed = [f for f in feed if f.get("slug") != content.website_slug]
        feed.insert(0, entry)
        feed_path.write_text(json.dumps(feed[:50], ensure_ascii=False, indent=2), encoding="utf-8")

    def _rebuild_index(self, out: Path, base_url: str):
        feed_path = out / "feed.json"
        cards_html = ""
        if feed_path.exists():
            try:
                feed = json.loads(feed_path.read_text(encoding="utf-8"))
                esc = html.escape
                for entry in feed[:20]:
                    img = f'<img src="{esc(entry.get("image_url",""))}" alt="" class="card-img" loading="lazy">' if entry.get("image_url") else ""
                    cards_html += f"""
    <article class="card">
      {img}
      <div class="card-content">
        <span class="card-category">{esc(entry.get("category",""))}</span>
        <h2><a href="{esc(entry.get("url","#"))}">{esc(entry.get("emoji",""))} {esc(entry.get("title",""))}</a></h2>
        <p>{esc((entry.get("description") or "")[:140])}…</p>
        <div class="card-footer">
          <span class="score">Score: {entry.get("score",0)}/100</span>
          <span class="date">{esc(entry.get("date",""))}</span>
        </div>
      </div>
    </article>"""
            except Exception:
                pass

        index_html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TechRadar AI — Сигнал, не шум.</title>
  <meta name="description" content="Лучшее в мире ИИ и инструментов разработчика. Автоматический сбор, строгая фильтрация — только то, что важно.">
  <meta property="og:title" content="TechRadar AI">
  <meta property="og:description" content="ИИ и инструменты разработчика. Сигнал, не шум.">
  <link rel="stylesheet" href="{base_url}/css/style.css">
</head>
<body>
  <nav class="navbar">
    <a href="{base_url}" class="logo">&#128301; TechRadar AI</a>
    <span class="nav-tagline">Сигнал, не шум.</span>
  </nav>
  <header class="hero">
    <h1>Лучшее в ИИ и инструментах разработчика</h1>
    <p>Автоматический сбор · Строгая фильтрация · Только то, что важно.</p>
  </header>
  <main class="grid">
    {cards_html if cards_html else '<p class="empty">Постов пока нет. Заходите позже.</p>'}
  </main>
  <footer><p>&#169; TechRadar AI &#8212; Работает на ИИ, отобрано по стандартам.</p></footer>
  <script src="{base_url}/js/main.js" defer></script>
</body>
</html>"""
        (out / "index.html").write_text(index_html, encoding="utf-8")
