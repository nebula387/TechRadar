"""Quick visual test for image card generation. Run: python test_card.py"""
from pathlib import Path
from app.image.card import generate_card

SAMPLES = [
    {
        "title": "LLM-Powered Multi-Market Stock Analysis System",
        "description": "Automated stock intelligence with real-time news, multi-source market data, decision dashboards and scheduled alerts — zero cost to run.",
        "category": "AI Model",
        "emoji": "📈",
        "accent_color": "#6366f1",
        "source": "github_trending",
        "score": 90,
        "filename": "test_card_long_title.png",
    },
    {
        "title": "Deer Flow: Multi-Agent AI Research Framework by ByteDance",
        "description": "Open-source deep research framework combining LLM agents with web search, code execution and report generation.",
        "category": "AI Agent",
        "emoji": "🦌",
        "accent_color": "#10b981",
        "source": "github_trending",
        "score": 87,
        "filename": "test_card_medium.png",
    },
    {
        "title": "WorldMonitor",
        "description": "Real-time global event monitoring with LLM summarization across news, social media and government sources.",
        "category": "Developer Tool",
        "emoji": "🌍",
        "accent_color": "#f59e0b",
        "source": "github_trending",
        "score": 85,
        "filename": "test_card_short.png",
    },
]

out_dir = Path("./data/test_cards")
out_dir.mkdir(parents=True, exist_ok=True)

for s in SAMPLES:
    path = out_dir / s["filename"]
    result = generate_card(
        title=s["title"],
        description=s["description"],
        category=s["category"],
        emoji=s["emoji"],
        accent_color=s["accent_color"],
        source=s["source"],
        score=s["score"],
        output_path=path,
    )
    if result:
        print(f"OK  {s['filename']}  ->  {result}")
    else:
        print(f"FAIL: {s['filename']}")

print(f"\nOpen folder: {out_dir.resolve()}")
