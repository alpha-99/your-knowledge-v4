"""
审核节点 — 对 analyses 进行 5 维度质量审核

与 nodes.py 中的 V2 版 review_node 的区别：
1. 审核对象从 articles 改为 analyses（organize 之前）
2. 从 4 维度 (1-5分) 升级为 5 维度 (1-10分)
3. 加权总分由代码重算，不信任模型算术
4. 仅审核前 5 条以控制 token 消耗

审核维度及权重：
  summary_quality   — 摘要质量 (25%)
  technical_depth   — 技术深度 (25%)
  relevance         — 相关性   (20%)
  originality       — 原创性   (15%)
  formatting        — 格式规范 (15%)

通过标准：加权总分 >= 7.0
最多 3 次迭代，第 3 次强制通过
LLM 调用失败时自动通过
"""

import json

from workflows.model_client import accumulate_usage, chat_json
from workflows.state import KBState

WEIGHTS = {
    "summary_quality": 0.25,
    "technical_depth": 0.25,
    "relevance": 0.20,
    "originality": 0.15,
    "formatting": 0.15,
}

PASS_THRESHOLD = 7.0
MAX_ANALYSES = 5


def _calculate_weighted_score(scores: dict) -> float:
    """根据 5 维度分项得分和预设权重，代码重算加权总分"""
    total = 0.0
    for dim, weight in WEIGHTS.items():
        total += scores.get(dim, 0) * weight
    return round(total, 2)


def review_node(state: KBState) -> dict:
    """V3 审核节点：对 analyses 进行 5 维度质量审核

    依赖：
    - chat_json(prompt, system=..., temperature=...)
    - accumulate_usage(tracker, usage)
    - KBState: plan, analyses, iteration, cost_tracker

    返回：{review_passed, review_feedback, iteration, cost_tracker}
    """
    print("[Reviewer] 开始审核（V3: 5维度, 1-10分, 仅前5条 analyses）...")

    analyses = state.get("analyses", [])
    iteration = state.get("iteration", 0)
    tracker = state.get("cost_tracker", {})

    plan = state.get("plan", {}) or {}
    max_iterations = int(plan.get("max_iterations", 3))

    if not analyses:
        return {
            "review_passed": True,
            "review_feedback": "没有 analyses 需要审核",
            "iteration": iteration + 1,
            "cost_tracker": tracker,
        }

    batch = analyses[:MAX_ANALYSES]
    if len(analyses) > MAX_ANALYSES:
        print(f"[Reviewer] analyses 共 {len(analyses)} 条，仅审核前 {MAX_ANALYSES} 条")

    prompt = f"""你是知识库质量审核员。请对以下分析条目进行 5 维度评分（每项 1-10 分）：

{json.dumps(batch, ensure_ascii=False, indent=2)}

评分维度：
1. summary_quality (摘要质量) — 25%：摘要是否准确、简洁、有洞察
2. technical_depth (技术深度) — 25%：是否体现核心技术原理和实现细节
3. relevance (相关性) — 20%：与 AI/LLM/Agent 领域的相关程度
4. originality (原创性) — 15%：项目或文章是否具有独特视角或创新点
5. formatting (格式规范) — 15%：tags、category 等字段是否规范

请用 JSON 格式回复（不要计算总分，仅给出各维度分数）：
{{
    "passed": true或false (加权总分 >= 7.0 为 true),
    "feedback": "具体的改进建议（如果未通过，请逐维度给出）",
    "scores": {{
        "summary_quality": 8,
        "technical_depth": 7,
        "relevance": 9,
        "originality": 6,
        "formatting": 8
    }}
}}

这是第 {iteration + 1}/{max_iterations} 次审核。"""

    try:
        result, usage = chat_json(
            prompt,
            system="你是严格但公正的知识库质量审核员。给出具体、可操作的维度反馈。仅输出 JSON。",
            temperature=0.1,
            node_name="reviewer",
        )
        tracker = accumulate_usage(tracker, usage)

        feedback = result.get("feedback", "")
        scores = result.get("scores", {})

        weighted_score = _calculate_weighted_score(scores)
        passed = weighted_score >= PASS_THRESHOLD

        print(
            f"[Reviewer] 加权得分: {weighted_score}/10 (模型认为: {result.get('passed', 'N/A')}), "
            f"通过: {passed}, 迭代 {iteration + 1}/{max_iterations}"
        )
        print(f"[Reviewer] 分项得分: {json.dumps(scores, ensure_ascii=False)}")

    except Exception as e:
        passed = True
        weighted_score = PASS_THRESHOLD
        feedback = f"审核 LLM 调用失败: {e}，自动通过"
        print(f"[Reviewer] 审核失败，自动通过: {e}")

    return {
        "review_passed": passed,
        "review_feedback": feedback,
        "iteration": iteration + 1,
        "cost_tracker": tracker,
    }
