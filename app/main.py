import asyncio
import logging
import sys
import argparse
from pathlib import Path

# Ensure data/ exists for logs and DB
Path("./data").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("./data/techradar.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

COLLECTOR_MAP = {
    "github": "app.collectors.github.GitHubCollector",
    "github_trending": "app.collectors.github_trending.GitHubTrendingCollector",
    "hackernews": "app.collectors.hackernews.HackerNewsCollector",
    "huggingface": "app.collectors.huggingface.HuggingFaceCollector",
    "arxiv": "app.collectors.arxiv.ArxivCollector",
    "producthunt": "app.collectors.producthunt.ProductHuntCollector",
}


def _load_collector(dotted: str):
    module_path, class_name = dotted.rsplit(".", 1)
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)()


def main():
    parser = argparse.ArgumentParser(description="TechRadar AI — Content Pipeline")
    parser.add_argument(
        "--source",
        choices=list(COLLECTOR_MAP.keys()) + ["all"],
        default="all",
        help="Data source to collect from (default: all)",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Run as a background scheduler daemon",
    )
    args = parser.parse_args()

    if args.schedule:
        from app.scheduler.scheduler import build_scheduler
        scheduler = build_scheduler()
        scheduler.start()
        logger.info("Scheduler started — press Ctrl+C to stop")
        try:
            asyncio.get_event_loop().run_forever()
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown()
            logger.info("Scheduler stopped")
    else:
        from app.pipeline import run_pipeline
        if args.source == "all":
            collectors = [_load_collector(p) for p in COLLECTOR_MAP.values()]
        else:
            collectors = [_load_collector(COLLECTOR_MAP[args.source])]

        logger.info(f"Running pipeline with source='{args.source}'")
        asyncio.run(run_pipeline(collectors))


if __name__ == "__main__":
    main()
