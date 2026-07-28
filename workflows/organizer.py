"""
整理节点 — 过滤低分条目、按 URL 去重、根据反馈修正

职责:
1. 过滤低相关性条目 (relevance_score < 0.6)
2. 按 URL 去重
3. 如果有审核反馈且 iteration > 0，调用 LLM 定向修正
4. 生成统一格式的 articles
"""

import json
from datetime import datetime, timezone

from workflows.model_client import accumulate_usage, chat_json
from workflows.saver import save_node
from workflows.state import KBState
from tests.security import filter_output


def organize_node(state: KBState) -> dict:
    """整理节点：将分析结果格式化为标准知识条目"""
    print("[Organizer] 开始整理...")

    plan = state.get("plan", {}) or {}
    relevance_threshold = float(plan.get("relevance_threshold", 0.5))

    analyses = state["analyses"]
    feedback = state.get("review_feedback", "")
    iteration = state.get("iteration", 0)
    tracker = state.get("cost_tracker", {})

    qualified = [a for a in analyses if a.get("relevance_score", 0) >= relevance_threshold]

    seen_urls: set[str] = set()
    unique: list[dict] = []
    for item in qualified:
        url = item.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique.append(item)

    if feedback and iteration > 0:
        print(f"[Organizer] 检测到审核反馈，调用 LLM 进行定向修改 (迭代 {iteration})")
        prompt = f"""你是知识库编辑。以下是审核员的反馈，请据此改进这些知识条目。

审核反馈:
{feedback}

当前条目 (JSON):
{json.dumps(unique, ensure_ascii=False, indent=2)}

请返回改进后的条目列表（JSON 数组），保持相同字段结构。"""

        try:
            improved, usage = chat_json(prompt)
            tracker = accumulate_usage(tracker, usage)
            if isinstance(improved, list):
                unique = improved
        except Exception as e:
            print(f"[Organizer] 根据反馈修正失败: {e}，使用原始数据")

    articles: list[dict] = []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for i, item in enumerate(unique):
        articles.append({
            "id": f"{today}-{i:03d}",
            "title": item.get("title", ""),
            "source": item.get("source", "unknown"),
            "url": item.get("url", ""),
            "collected_at": item.get("collected_at", ""),
            "summary": item.get("summary", ""),
            "tags": item.get("tags", []),
            "relevance_score": item.get("relevance_score", 0.5),
            "category": item.get("category", "other"),
            "key_insight": item.get("key_insight", ""),
        })

    # ★ 接入点 ⑤ · 写盘前对每条 article 做 PII 掩码
    masked_articles = []
    total_pii = 0
    for art in articles:
        for field in ("summary", "content", "title"):
            if field in art and isinstance(art[field], str):
                filtered, detections = filter_output(art[field], mask=True)
                art[field] = filtered
                total_pii += len(detections)
                if detections:
                    print(f"[Security] {art.get('id', '?')} {field} 掩码 PII：{detections}")
        masked_articles.append(art)

    if total_pii > 0:
        print(f"[Security] organize 阶段共掩码 {total_pii} 处 PII")

    print(f"[Organizer] 整理出 {len(masked_articles)} 条知识条目 (迭代 {iteration})")

    updated_state = {**state, "articles": masked_articles, "cost_tracker": tracker}
    save_result = save_node(updated_state)

    return {"articles": masked_articles, "cost_tracker": tracker, **save_result}
