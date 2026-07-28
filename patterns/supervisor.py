"""
Supervisor 模式 — 主管调度 + 审核循环

Supervisor 是经典的 Multi-Agent 设计模式：
1. Worker Agent: 接收任务，输出结构化 JSON 分析报告
2. Supervisor Agent: 对 Worker 输出进行三维质量审核
3. 审核循环: 不通过则带反馈重做（最多 N 轮）

适用场景: 需要输出质量保证的复杂分析任务。
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from workflows.model_client import chat_json, accumulate_usage


# ---------------------------------------------------------------------------
# Worker Agent — 执行任务并输出 JSON 分析报告
# ---------------------------------------------------------------------------

WORKER_SYSTEM = """你是一个专业的技术分析 Worker Agent。
根据任务描述，输出结构化的 JSON 分析报告，字段要求:

- title: 报告标题
- summary: 核心摘要（2-3 句话）
- analysis: 详细分析内容
- key_points: 关键要点列表（至少 3 条）
- recommendations: 建议或结论

只输出合法 JSON，不要包裹在 markdown 代码块中。"""


def _worker(task: str, feedback: str | None = None) -> tuple[dict, dict]:
    """Worker 执行任务并返回 JSON 分析报告

    Args:
        task: 任务描述
        feedback: 前次审核反馈（重做时拼接进 prompt）

    Returns:
        (analysis_dict, usage_dict)
    """
    prompt = f"任务: {task}\n\n请输出 JSON 格式的分析报告。"
    if feedback:
        prompt += f"\n\n【上次审核反馈 — 请据此改进】\n{feedback}"

    result, usage = chat_json(prompt, system=WORKER_SYSTEM)
    return result, usage


# ---------------------------------------------------------------------------
# Supervisor Agent — 质量审核
# ---------------------------------------------------------------------------

SUPERVISOR_SYSTEM = """你是一个严格的质量审核 Supervisor Agent。
请从三个维度评估 Worker 的分析报告，各 1-10 分:

- accuracy: 内容是否准确、事实可靠
- depth: 分析是否深入、有洞见
- format: JSON 结构是否规范、字段是否完整

输出 JSON:
{"accuracy": int, "depth": int, "format": int, "score": int, "feedback": str}

score 取三维度平均分（四舍五入取整），feedback 必须具体、可操作。"""


def _evaluate(report: dict) -> tuple[dict, dict]:
    """Supervisor 对 Worker 输出进行质量评估

    Returns:
        (evaluation_dict, usage_dict)
        包含 accuracy, depth, format, score, feedback, passed
    """
    prompt = (
        "请评估以下 Worker 的分析报告:\n\n"
        f"{json.dumps(report, ensure_ascii=False, indent=2)}"
    )
    result, usage = chat_json(prompt, system=SUPERVISOR_SYSTEM, temperature=0)

    score_raw = result.get("score")
    if score_raw is None:
        score_raw = round(
            (result.get("accuracy", 0) + result.get("depth", 0) + result.get("format", 0)) / 3
        )
    result["score"] = int(score_raw)
    result["passed"] = result["score"] >= 7
    return result, usage


# ---------------------------------------------------------------------------
# 审核循环核心
# ---------------------------------------------------------------------------

def supervisor(task: str, max_retries: int = 3) -> dict:
    """Supervisor 监督模式主函数

    工作流:
    1. Worker 生成分析报告
    2. Supervisor 三维评分（accuracy / depth / format）
    3. 通过（score >= 7）→ 返回结果
    4. 不通过 → 带 feedback 重做 Worker
    5. 超过 max_retries 仍不通过 → 强制返回 + warning

    Args:
        task: 任务描述
        max_retries: 最大重试次数（默认 3，即最多 1 次初始 + 3 次重试 = 4 轮）

    Returns:
        dict: {
            "task": str,
            "output": dict,          # 最终分析报告
            "attempts": int,         # 实际尝试轮次
            "final_score": int,      # 最终评分 (1-10)
            "passed": bool,          # 是否通过审核
            "cost_tracker": dict,    # 累计 token 用量
            "warning": str | None,   # 警告信息（超出重试时）
        }
    """
    attempts = 0
    cost_tracker: dict = {}
    current_feedback: str | None = None
    worker_output: dict = {}
    avg_score = 0

    total_rounds = 1 + max_retries  # 初始 1 次 + max_retries 次重试

    for attempt in range(1, total_rounds + 1):
        attempts = attempt
        print(f"\n{'─' * 50}")
        print(f"[Supervisor] 第 {attempt} / {total_rounds} 轮")

        # --- Worker 阶段 ---
        worker_output, usage = _worker(task, current_feedback)
        cost_tracker = accumulate_usage(cost_tracker, usage)
        print(f"[Worker] 报告生成完成 — 标题: {worker_output.get('title', '?')}")

        # --- 审核阶段 ---
        eval_result, usage = _evaluate(worker_output)
        cost_tracker = accumulate_usage(cost_tracker, usage)

        accuracy = eval_result.get("accuracy", 0)
        depth = eval_result.get("depth", 0)
        fmt = eval_result.get("format", 0)
        avg_score = eval_result.get("score", 0)
        passed = eval_result.get("passed", False)
        feedback = eval_result.get("feedback", "")

        print(
            f"[Supervisor] 评分: accuracy={accuracy} depth={depth} format={fmt} "
            f"=> score={avg_score} {'✓ 通过' if passed else '✗ 未通过'}"
        )

        if passed:
            print(f"[Supervisor] 审核通过 — 共 {attempt} 轮")
            return {
                "task": task,
                "output": worker_output,
                "attempts": attempts,
                "final_score": avg_score,
                "passed": True,
                "cost_tracker": cost_tracker,
                "warning": None,
            }

        # --- 准备重试 ---
        current_feedback = feedback
        print(f"[Supervisor] 反馈: {feedback}")

        if attempt >= total_rounds:
            break

    # 超出最大重试 — 强制返回
    print(f"[Supervisor] ⚠ 已达最大重试次数（{max_retries}），强制返回")
    return {
        "task": task,
        "output": worker_output,
        "attempts": attempts,
        "final_score": avg_score,
        "passed": False,
        "cost_tracker": cost_tracker,
        "warning": (
            f"达到最大重试次数 {max_retries}，"
            f"未能通过审核（最终评分: {avg_score}/10）"
        ),
    }


# ---------------------------------------------------------------------------
# 命令行测试入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    task = (
        " ".join(sys.argv[1:])
        if len(sys.argv) > 1
        else "分析 DeepSeek-V3 的技术架构和核心创新点"
    )
    print(f"任务: {task}\n")

    result = supervisor(task, max_retries=3)

    print("\n" + "=" * 60)
    print("最终结果")
    print("=" * 60)
    print(f"通过: {'是' if result['passed'] else '否'}")
    print(f"尝试次数: {result['attempts']}")
    print(f"最终评分: {result['final_score']}/10")
    if result.get("warning"):
        print(f"警告: {result['warning']}")
    print(f"Token 用量: {json.dumps(result['cost_tracker'], ensure_ascii=False)}")
    print(f"\n分析报告:\n{json.dumps(result['output'], ensure_ascii=False, indent=2)}")
