import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


def build_scheduler() -> AsyncIOScheduler:
    from app.pipeline import run_pipeline
    from app.collectors.github import GitHubCollector
    from app.collectors.github_trending import GitHubTrendingCollector
    from app.collectors.huggingface import HuggingFaceCollector
    from app.collectors.hackernews import HackerNewsCollector
    from app.collectors.arxiv import ArxivCollector

    scheduler = AsyncIOScheduler(timezone="UTC")

    jobs = [
        # GitHub Trending (daily) runs first — freshest signal
        ("09:00 GitHub Trending", CronTrigger(hour=9, minute=0), [GitHubTrendingCollector(), GitHubCollector()], "github_cycle"),
        ("13:00 HuggingFace", CronTrigger(hour=13, minute=0), [HuggingFaceCollector()], "hf_cycle"),
        ("17:00 HackerNews", CronTrigger(hour=17, minute=0), [HackerNewsCollector()], "hn_cycle"),
        ("21:00 ArXiv", CronTrigger(hour=21, minute=0), [ArxivCollector()], "arxiv_cycle"),
    ]

    for name, trigger, cols, job_id in jobs:
        def make_job(collectors):
            return lambda: asyncio.create_task(run_pipeline(collectors))

        scheduler.add_job(
            make_job(cols),
            trigger=trigger,
            id=job_id,
            name=name,
            replace_existing=True,
        )
        logger.info(f"Scheduled: {name}")

    return scheduler
