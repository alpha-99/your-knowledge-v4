"""
知识条目路径工具 — 按天分文件夹的统一约定

目录结构：

    knowledge/articles/
    ├── index.json                 # 全局索引（始终在根目录）
    └── 2026-11-04/
        ├── 2026-11-04-000.json
        └── 2026-11-04-001.json

条目 id 形如 ``2026-11-04-000``，日期子目录名取自 id 的前 10 个字符，
因此「同一 id → 同一路径」天然幂等，重复运行不会产生重复文件。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Iterable

DATE_FMT = "%Y-%m-%d"


def date_subdir(article_id: str) -> str:
    """从条目 id 提取日期子目录名（id 形如 2026-11-04-000）

    id 前 10 个字符不是合法日期时，回退到当前 UTC 日期，
    保证任何情况下都能落盘且路径可预期。
    """
    head = article_id[:10]
    try:
        time.strptime(head, DATE_FMT)
        return head
    except ValueError:
        return time.strftime(DATE_FMT, time.gmtime())


def is_valid_date(text: str) -> bool:
    """判断字符串是否为 YYYY-MM-DD 格式的合法日期"""
    try:
        time.strptime(text, DATE_FMT)
        return True
    except ValueError:
        return False


def iter_article_files(articles_dir: str | Path, date: str | None = None) -> list[Path]:
    """列出指定日期的全部条目文件（按文件名排序）

    优先读新结构 ``{articles_dir}/{date}/*.json``；
    子目录不存在时回退到旧的扁平结构 ``{articles_dir}/{date}-*.json``，
    便于尚未迁移的历史环境继续工作。

    Args:
        articles_dir: knowledge/articles 目录路径。
        date: ISO 日期字符串；None 时返回全部条目（含扁平残留）。
    """
    root = Path(articles_dir)
    if date is None:
        # 根目录残留的扁平条目（未迁移的历史文件）+ 所有日期子目录条目
        # index.json 位于根目录且 id 不是日期前缀，天然被过滤
        flat = [
            p for p in root.glob("*.json")
            if p.stem != "index" and is_valid_date(p.stem[:10])
        ]
        nested = [p for p in root.rglob("*.json") if p.parent != root]
        return sorted(flat + nested)

    day_dir = root / date
    if day_dir.is_dir():
        return sorted(day_dir.glob("*.json"))

    return sorted(root.glob(f"{date}-*.json"))


def article_files_by_date(articles_dir: str | Path) -> Iterable[tuple[str, list[Path]]]:
    """按日期分组返回条目文件，便于需要遍历所有日期的调用方使用"""
    root = Path(articles_dir)
    grouped: dict[str, list[Path]] = {}
    for sub in sorted(p for p in root.iterdir() if p.is_dir() and is_valid_date(p.name)):
        grouped[sub.name] = sorted(sub.glob("*.json"))
    return grouped.items()