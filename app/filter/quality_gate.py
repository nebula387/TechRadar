import logging
from app.models import RawItem, Source
from app.database.storage import Storage

logger = logging.getLogger(__name__)

# (predicate, rejection_reason)
HARD_REJECT_RULES: list[tuple] = [
    (lambda i: len(i.description) < 30, "description too short"),
    (lambda i: "tutorial" in i.title.lower(), "tutorial content"),
    (lambda i: "awesome-" in i.title.lower() or i.title.lower().startswith("awesome "), "awesome list"),
    (lambda i: "beginner" in i.title.lower(), "beginner content"),
    (lambda i: "introduction to" in i.title.lower(), "intro content"),
    (lambda i: "getting started" in i.title.lower(), "getting started guide"),
    (lambda i: "cheat sheet" in i.title.lower(), "cheat sheet"),
]

def _github_threshold(item: RawItem) -> bool:
    stars_today = (item.raw_data or {}).get("stars_today", 0)
    # Trending repo with 50+ stars today passes even with low total
    if stars_today >= 50:
        return True
    return (item.stars or 0) >= 500


SOURCE_THRESHOLDS: dict[Source, callable] = {
    Source.GITHUB: _github_threshold,
    Source.HUGGINGFACE: lambda i: (i.stars or 0) >= 100,
    Source.HACKERNEWS: lambda i: (i.stars or 0) >= 200,
    Source.PRODUCTHUNT: lambda i: (i.stars or 0) >= 100,
    Source.ARXIV: lambda i: True,
}


def passes_quality_gate(item: RawItem, storage: Storage) -> tuple[bool, str]:
    if storage.is_published(item.url):
        return False, "already published"

    for predicate, reason in HARD_REJECT_RULES:
        if predicate(item):
            return False, reason

    threshold_fn = SOURCE_THRESHOLDS.get(item.source)
    if threshold_fn and not threshold_fn(item):
        return False, f"below {item.source.value} popularity threshold"

    return True, "passed"


def filter_items(items: list[RawItem], storage: Storage) -> list[RawItem]:
    passed, rejected = [], 0
    for item in items:
        ok, reason = passes_quality_gate(item, storage)
        if ok:
            passed.append(item)
        else:
            rejected += 1
            logger.debug(f"Gate rejected '{item.title[:60]}': {reason}")

    logger.info(f"Quality gate: {len(passed)} passed / {rejected} rejected / {len(items)} total")
    return passed
