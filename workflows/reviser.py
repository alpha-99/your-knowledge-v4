"""
修订节点 — 将审核反馈注入 prompt 调用 LLM 修改 analyses

与 organize_node 中的内联修正逻辑不同，revise_node 是独立的修订步骤，
专门负责根据 review_feedback 定向修改 analyses 列表。
"""

import json

from workflows.model_client import accumulate_usage, chat_json
from workflows.state import KBState


def revise_node(state: KBState) -> dict:
    """修订节点：读取 analyses 和 review_feedback，调用 LLM 返回改进后的 analyses

    依赖：
    - chat_json(prompt, system=..., temperature=...)
    - accumulate_usage(tracker, usage)
    - KBState: analyses, review_feedback, cost_tracker

    返回：{"analyses": improved, "cost_tracker": tracker}
    当 analyses 或 review_feedback 为空时返回 {}。
    """
    print("[Reviser] 开始修订（根据审核反馈修正 analyses）...")

    analyses = state.get("analyses", [])
    feedback = state.get("review_feedback", "")
    tracker = state.get("cost_tracker", {})

    if not analyses or not feedback:
        print("[Reviser] analyses 或 feedback 为空，跳过修订")
        return {}

    prompt = f"""你是知识库编辑。以下是审核员的反馈，请据此改进这些分析条目。

审核反馈:
{feedback}

当前分析条目 (JSON):
{json.dumps(analyses, ensure_ascii=False, indent=2)}

请根据反馈逐条修正，返回改进后的完整分析条目列表（JSON 数组），保持相同字段结构。"""

    try:
        improved, usage = chat_json(
            prompt,
            system="你是专业的知识库编辑，擅长根据审核反馈精准修正技术条目。仅输出 JSON 数组。",
            temperature=0.4,
            node_name="reviser",
        )
        tracker = accumulate_usage(tracker, usage)

        if not isinstance(improved, list):
            print(f"[Reviser] LLM 返回非列表结果，类型: {type(improved).__name__}，保留原始 analyses")
            return {"cost_tracker": tracker}

        print(f"[Reviser] 完成修订，共 {len(improved)} 条 analyses")
    except Exception as e:
        print(f"[Reviser] 修订 LLM 调用失败: {e}，保留原始 analyses")
        return {"cost_tracker": tracker}

    return {"analyses": improved, "cost_tracker": tracker}
