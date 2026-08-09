#!/usr/bin/env python3
"""每日推送入口脚本 — 加载今日文章、过滤低质量内容后推送到各渠道。"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from distribution.publisher import PublishResult, publish_daily_digest

logger = logging.getLogger(__name__)

MIN_RELEVANCE_SCORE = 0.6
KNOWLEDGE_DIR = "knowledge/articles"


def _load_articles(date: str | None = None) -> list[dict[str, Any]]:
    """加载指定日期的全部文章。

    Args:
        date: ISO 格式日期字符串，None 表示今天（UTC）。

    Returns:
        文章 dict 列表。
    """
    if date is None:
        date = datetime.now(timezone.utc).date().isoformat()

    dir_path = Path(KNOWLEDGE_DIR)
    pattern = f"{date}-*.json"
    article_files = sorted(dir_path.glob(pattern))

    articles: list[dict[str, Any]] = []
    for fp in article_files:
        try:
            article = json.loads(fp.read_text(encoding="utf-8"))
            articles.append(article)
        except (json.JSONDecodeError, OSError):
            logger.warning("跳过损坏的文章文件: %s", fp)
    return articles


def _filter_articles(
    articles: list[dict[str, Any]],
    min_score: float = MIN_RELEVANCE_SCORE,
) -> list[dict[str, Any]]:
    """过滤低质量文章，仅保留 relevance_score >= min_score 的条目。

    Args:
        articles: 原始文章列表。
        min_score: 最低相关度阈值。

    Returns:
        过滤后的文章列表。
    """
    return [
        a for a in articles
        if float(a.get("relevance_score", 0)) >= min_score
    ]


def _print_summary(results: list[PublishResult]) -> None:
    """打印推送结果汇总。

    Args:
        results: publish_daily_digest() 返回的 PublishResult 列表。
    """
    channels: dict[str, list[PublishResult]] = {}
    for r in results:
        channels.setdefault(r.channel, []).append(r)

    total_ok = 0
    total_fail = 0
    for channel, channel_results in channels.items():
        ok = sum(1 for r in channel_results if r.success)
        fail = len(channel_results) - ok
        total_ok += ok
        total_fail += fail
        print(f"  [{channel}] 成功 {ok}, 失败 {fail}")
        for r in channel_results:
            if not r.success:
                print(f"    FAIL: {r.error}")

    print(f"\n推送结果汇总: 成功 {total_ok}, 失败 {total_fail}")


async def main() -> None:
    """每日推送主流程：加载 → 过滤 → 推送 → 汇总。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    today = datetime.now(timezone.utc).date().isoformat()
    articles = _load_articles(today)
    print(f"[{today}] 加载文章: {len(articles)} 篇")

    if not articles:
        print(f"警告: [{today}] 今日无文章，跳过推送")
        return

    high_quality = _filter_articles(articles)
    filtered_count = len(articles) - len(high_quality)
    if filtered_count > 0:
        print(
            f"已过滤 {filtered_count} 篇低质量文章 "
            f"(relevance_score < {MIN_RELEVANCE_SCORE})"
        )

    if not high_quality:
        print(
            f"警告: [{today}] 过滤后无高质量文章 "
            f"(relevance_score >= {MIN_RELEVANCE_SCORE})，跳过推送"
        )
        return

    print(f"准备推送 {len(high_quality)} 篇高质量文章...")
    results = await publish_daily_digest(
        knowledge_dir=KNOWLEDGE_DIR, date=today, channels=['feishu']
    )
    _print_summary(results)


if __name__ == "__main__":
    asyncio.run(main())
