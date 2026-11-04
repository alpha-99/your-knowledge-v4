"""
RSS 多数据源采集模块 — 读取 pipeline/rss_sources.yaml 配置并抓取各 feed

实现要点:
1. 用 PyYAML 读取数据源配置，只采集 enabled: true 的源
2. 用标准库 xml.etree.ElementTree 解析 RSS 2.0 / Atom，不引入第三方依赖
3. 每个源独立容错：单个源网络/解析失败只记录日志并跳过，不中断整个采集
4. 输出与 GitHub 采集相同的 source 结构，可直接进入 analyze 节点
5. 文本字段同样经过 tests.security.sanitize_input 清洗（防注入）
"""

import os
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import yaml

from tests.security import sanitize_input

# 配置文件路径（项目根目录下的 pipeline/rss_sources.yaml）
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "pipeline" / "rss_sources.yaml"

def rss_enabled() -> bool:
    """是否启用 RSS 采集，通过环境变量 RSS_ENABLED 控制（默认开启）

    每次调用时读取，而非 import 时定死——便于测试与运行中切换。
    """
    return os.getenv("RSS_ENABLED", "1").lower() in ("1", "true", "yes", "on")

# 每个 feed 的最大抓取条数，默认取 plan 的 per_source_limit
DEFAULT_PER_FEED_LIMIT = 10


def _localname(tag: str) -> str:
    """去掉 XML 命名空间前缀，返回局部标签名

    Example:
        "{http://www.w3.org/2005/Atom}title" -> "title"
    """
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _text(element: ET.Element, name: str) -> str:
    """取子元素的文本（忽略命名空间），无则返回空串"""
    for child in element:
        if _localname(child.tag) == name and child.text:
            return child.text.strip()
    return ""


def _link_href(element: ET.Element) -> str:
    """取 Atom 条目的链接 href（优先 rel=alternate，其次第一个 link）"""
    links = [child for child in element if _localname(child.tag) == "link"]
    if not links:
        return ""
    for link in links:
        if link.get("rel") in (None, "alternate"):
            return link.get("href", "")
    return links[0].get("href", "")


def load_rss_sources(config_path: Path | None = None) -> list[dict]:
    """读取 RSS 数据源配置，返回启用的源列表

    Returns:
        list[dict]: 每个元素 {name, url, category}
    """
    path = config_path or DEFAULT_CONFIG_PATH
    if not path.exists():
        print(f"[RSSCollector] 配置文件不存在: {path}")
        return []

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    sources = []
    for item in data.get("sources", []):
        if not item.get("enabled", False):
            continue
        if not item.get("url"):
            continue
        sources.append({
            "name": item.get("name", "rss"),
            "url": item["url"],
            "category": item.get("category", "其他"),
        })
    return sources


def parse_feed(xml_bytes: bytes) -> list[dict]:
    """解析 RSS 2.0 或 Atom 的 XML 字节流，返回条目列表

    Returns:
        list[dict]: 每项 {title, url, description}
    """
    root = ET.fromstring(xml_bytes)
    items: list[dict] = []

    # RSS 2.0: <rss><channel><item>
    if _localname(root.tag) == "rss":
        entries = [
            el
            for el in root.iter()
            if _localname(el.tag) == "item"
        ]
        for entry in entries:
            title = _text(entry, "title")
            link = _text(entry, "link")
            description = _text(entry, "description") or _text(entry, "summary")
            if title and link:
                items.append({"title": title, "url": link, "description": description})

    # Atom: <feed><entry>
    elif _localname(root.tag) == "feed":
        entries = [el for el in root.iter() if _localname(el.tag) == "entry"]
        for entry in entries:
            title = _text(entry, "title")
            link = _link_href(entry)
            description = _text(entry, "summary") or _text(entry, "content")
            if title and link:
                items.append({"title": title, "url": link, "description": description})

    return items


def fetch_feed(feed: dict, per_feed_limit: int = DEFAULT_PER_FEED_LIMIT) -> tuple[list[dict], int]:
    """抓取单个 feed，返回 (条目列表, 错误码 0/1)

    单源容错：任何异常只记录日志，不抛出，避免中断整个采集。
    """
    try:
        req = urllib.request.Request(feed["url"], headers={"User-Agent": "your-knowledge/4.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
        items = parse_feed(raw)
        return items[:per_feed_limit], 0
    except Exception as e:
        print(f"[RSSCollector] 抓取失败 [{feed.get('name', '?')}] {feed['url']}: {e}")
        return [], 1


def collect_rss_sources(per_source_limit: int = DEFAULT_PER_FEED_LIMIT) -> tuple[list[dict], int]:
    """采集所有启用的 RSS 源，合并为统一 source 结构

    Args:
        per_source_limit: 每个 feed 最多抓取条数

    Returns:
        (sources, error_count):
        sources 每项: {source, title, url, description, stars, language,
                       collected_at, feed_category}
    """
    if not rss_enabled():
        print("[RSSCollector] RSS 采集已禁用 (RSS_ENABLED=0)")
        return [], 0

    feeds = load_rss_sources()
    if not feeds:
        print("[RSSCollector] 没有启用的 RSS 源")
        return [], 0

    print(f"[RSSCollector] 开始采集 {len(feeds)} 个源 (每源上限 {per_source_limit})...")

    sources: list[dict] = []
    error_count = 0
    now = datetime.now(timezone.utc).isoformat()

    for feed in feeds:
        items, err = fetch_feed(feed, per_source_limit)
        error_count += err
        for it in items:
            sources.append({
                "source": feed["name"],
                "title": it["title"],
                "url": it["url"],
                "description": it["description"],
                "stars": 0,
                "language": "",
                "collected_at": now,
                "feed_category": feed["category"],
            })

    # 对每条 source 的文本字段做清洗（防注入），与 GitHub 采集保持一致
    cleaned_sources = []
    total_warnings = 0
    for s in sources:
        for field in ("title", "description"):
            if field in s and isinstance(s[field], str):
                cleaned, warnings = sanitize_input(s[field])
                s[field] = cleaned
                total_warnings += len(warnings)
                if warnings:
                    print(f"[RSSCollector] {s.get('url', '?')} {field} 检出注入模式：{warnings}")
        cleaned_sources.append(s)

    if total_warnings > 0:
        print(f"[RSSCollector] 共拦截 {total_warnings} 处可疑输入")

    print(f"[RSSCollector] 采集完成 — {len(cleaned_sources)} 条, 失败源 {error_count} 个")
    return cleaned_sources, error_count


if __name__ == "__main__":
    sources, errs = collect_rss_sources()
    print(f"\n共 {len(sources)} 条, 失败 {errs} 个源")
    for s in sources[:10]:
        print(f"  - [{s['source']}] {s['title'][:60]}")
