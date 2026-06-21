"""
Rebuild all website HTML from feed.json.
Called in CI before deploy so every deploy uses the latest templates/code.

Usage: python -m app.rebuild_website
"""
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def rebuild(output_dir: str = "./website/public", base_url: str = "") -> int:
    from app.config import get_settings
    from app.publishers.website import WebsitePublisher

    s = get_settings()
    base_url = base_url or s.website_base_url.rstrip("/")
    out = Path(output_dir)
    feed_path = out / "feed.json"

    if not feed_path.exists():
        logger.warning("feed.json not found — nothing to rebuild")
        return 0

    feed: list[dict] = json.loads(feed_path.read_text(encoding="utf-8"))
    if not feed:
        logger.info("feed.json is empty — nothing to rebuild")
        return 0

    pub = WebsitePublisher()

    # Rebuild each post page from stored data
    posts_dir = out / "posts"
    images_dir = out / "images"
    css_dir = out / "css"
    js_dir = out / "js"
    for d in (posts_dir, images_dir, css_dir, js_dir):
        d.mkdir(parents=True, exist_ok=True)

    pub._copy_static(css_dir, js_dir)

    # Regenerate image cards from feed data
    from app.image.card import generate_card
    for entry in feed:
        slug = entry.get("slug", "")
        img_path = images_dir / f"{slug}.png"
        if slug and not img_path.exists() and entry.get("title"):
            card_desc = (entry.get("body_en") or entry.get("description") or "")[:160].split("\n")[0]
            generate_card(
                title=entry.get("title", ""),
                description=card_desc,
                category=entry.get("category", "Developer Tool"),
                emoji=entry.get("emoji", "🔧"),
                accent_color=entry.get("accent_color", "#6366f1"),
                source=entry.get("source", "github"),
                score=entry.get("score", 85),
                output_path=img_path,
            )

    import html as _html
    esc = _html.escape
    rebuilt = 0

    for entry in feed:
        slug = entry.get("slug", "")
        if not slug:
            continue

        img_url = entry.get("image_url", "")
        img_tag = f'<img class="post-cover" src="{esc(img_url)}" alt="{esc(entry.get("title",""))}">' if img_url else ""
        tags_html = "".join(f'<span class="tag">{esc(t)}</span>' for t in entry.get("tags", []))
        body_en = entry.get("body_en", "")
        body_html = esc(body_en).replace("\n\n", "</p><p>").replace("\n", "<br>") if body_en else f"<i>{esc(entry.get('description',''))}</i>"
        title = entry.get("title", "")
        date_str = entry.get("date", "")
        score = entry.get("score", 0)
        category = entry.get("category", "")
        source_url = entry.get("source_url", "#")
        desc_ru = entry.get("description", "")

        post_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{esc(title)} — TechRadar AI</title>
  <meta name="description" content="{esc(desc_ru[:160])}">
  <meta property="og:title" content="{esc(title)}">
  <meta property="og:description" content="{esc(desc_ru[:200])}">
  {f'<meta property="og:image" content="{esc(img_url)}">' if img_url else ""}
  <meta name="twitter:card" content="summary_large_image">
  <link rel="stylesheet" href="{base_url}/css/style.css">
</head>
<body>
  <nav class="navbar">
    <a href="{base_url}" class="logo">&#128301; TechRadar AI</a>
    <span class="nav-tagline">Signal, not noise.</span>
  </nav>
  <main class="post-page">
    {img_tag}
    <div class="post-meta">
      <span class="score-badge">Score {score}/100</span>
      <span class="category-badge">{esc(category)}</span>
      <span class="date">{esc(date_str)}</span>
    </div>
    <h1>{esc(title)}</h1>
    <div class="tags">{tags_html}</div>
    <div class="post-body"><p>{body_html}</p></div>
    <div class="source-link">
      <a href="{esc(source_url)}" target="_blank" rel="noopener noreferrer">&#8594; View Original Source</a>
    </div>
    <div class="post-channels">
      <strong>Also published on:</strong>
      <a href="https://t.me/ai_tech_radar" target="_blank">Telegram</a>
    </div>
  </main>
  <footer><p>&#169; TechRadar AI &#8212; Powered by AI, curated by standards.</p></footer>
  <script src="{base_url}/js/main.js" defer></script>
</body>
</html>"""
        (posts_dir / f"{slug}.html").write_text(post_html, encoding="utf-8")
        rebuilt += 1

    # Rebuild index
    pub._rebuild_index(out, base_url)

    logger.info(f"Rebuilt {rebuilt} post pages + index.html")
    return rebuilt


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="./website/public")
    parser.add_argument("--base-url", default="")
    args = parser.parse_args()
    n = rebuild(args.output_dir, args.base_url)
    sys.exit(0 if n >= 0 else 1)
