"""
保存节点 — 将 articles 写入 knowledge/articles/{date}/ 子目录

1. 每篇文章写入 knowledge/articles/{date}/{id}.json（按天分文件夹）
2. 同步更新 knowledge/articles/index.json 索引文件
3. 输出本次运行总成本
"""

import json
import os

from workflows.article_paths import date_subdir
from workflows.state import KBState


def save_node(state: KBState) -> dict:
    """保存节点：将通过审核的知识条目写入 JSON 文件"""
    print("[Saver] 开始保存...")

    articles = state.get("articles", [])
    tracker = state.get("cost_tracker", {})

    if not articles:
        print("[Saver] 没有条目需要保存")
        return {}

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    articles_dir = os.path.join(base_dir, "knowledge", "articles")
    os.makedirs(articles_dir, exist_ok=True)

    saved_files: list[str] = []
    for article in articles:
        day_dir = os.path.join(articles_dir, date_subdir(article["id"]))
        os.makedirs(day_dir, exist_ok=True)
        filename = f"{article['id']}.json"
        filepath = os.path.join(day_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(article, f, ensure_ascii=False, indent=2)
        saved_files.append(filename)

    index_path = os.path.join(articles_dir, "index.json")
    index: list[dict] = []
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            try:
                index = json.load(f)
            except json.JSONDecodeError:
                index = []

    existing_ids = {entry["id"] for entry in index}
    for article in articles:
        if article["id"] not in existing_ids:
            rel_dir = os.path.relpath(
                os.path.join(articles_dir, date_subdir(article["id"])), base_dir
            )
            index.append({
                "id": article["id"],
                "title": article["title"],
                "category": article.get("category", "other"),
                "relevance_score": article.get("relevance_score", 0.5),
                # 相对仓库根的路径，消费者据此直读，不必再拼目录
                "path": f"{rel_dir.replace(os.sep, '/')}/{article['id']}.json",
            })

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"[Saver] 保存 {len(saved_files)} 篇文章到 {articles_dir}")
    print(f"[Saver] 本次运行总成本: ¥{tracker.get('total_cost_yuan', 0)}")
    return {}
