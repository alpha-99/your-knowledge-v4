"""
规划节点 — 根据目标采集量制定采集策略

三档策略自动切换：
- lite      (target < 10):        少量快速采集，适合日常概览
- standard  (10 <= target < 20):  常规采集，兼顾质量与效率
- full      (target >= 20):       全面采集，最大覆盖度

每档策略包含 per_source_limit、relevance_threshold、max_iterations
以及 rationale 字段说明选择理由。
"""

import os

from workflows.state import KBState

TIER_CONFIGS = {
    "lite": {
        "tier": "lite",
        "per_source_limit": 5,
        "relevance_threshold": 0.8,
        "max_iterations": 1,
        "rationale": "目标采集量较小 (<10)，采用轻量策略：限制每个数据源抓取 5 条、提高相关性门槛至 0.7、审核迭代 1 次，优先保证效率与精准度。",
    },
    "standard": {
        "tier": "standard",
        "per_source_limit": 10,
        "relevance_threshold": 0.7,
        "max_iterations": 2,
        "rationale": "目标采集量适中 (10-19)，采用标准策略：每个数据源抓取 10 条、相关性门槛 0.5、审核迭代 2 次，在效率与质量之间取得平衡。",
    },
    "full": {
        "tier": "full",
        "per_source_limit": 20,
        "relevance_threshold": 0.5,
        "max_iterations": 3,
        "rationale": "目标采集量较大 (>=20)，采用全覆盖策略：每个数据源抓取 20 条、放宽相关性门槛至 0.4、审核迭代 3 次，最大化覆盖广度并确保输出质量。",
    },
}

DEFAULT_TARGET_COUNT = 10

_ENV_KEY = "PLANNER_TARGET_COUNT"


def plan_strategy(target_count: int | None = None) -> dict:
    """根据目标采集量返回采集策略 dict

    Args:
        target_count: 目标采集条目数，None 时从环境变量 PLANNER_TARGET_COUNT 读取

    Returns:
        dict: 包含 tier, per_source_limit, relevance_threshold, max_iterations, rationale
    """
    if target_count is None:
        env_val = os.getenv(_ENV_KEY, str(DEFAULT_TARGET_COUNT))
        try:
            target_count = int(env_val)
        except (TypeError, ValueError):
            target_count = DEFAULT_TARGET_COUNT

    if target_count < 10:
        return dict(TIER_CONFIGS["lite"])
    elif target_count < 20:
        return dict(TIER_CONFIGS["standard"])
    else:
        return dict(TIER_CONFIGS["full"])


def planner_node(state: KBState) -> dict:
    """LangGraph 规划节点：读取 plan 中的 target_count，调用 plan_strategy 生成策略

    作为工作流的入口节点，planner_node 在执行任何采集/分析之前确定策略参数。
    后继节点（collect、analyze、review 等）可通过 state["plan"] 读取策略配置。

    Args:
        state: KBState，可包含 plan.target_count 指定目标量

    Returns:
        dict: {"plan": {tier, per_source_limit, relevance_threshold, max_iterations, rationale}}
    """
    existing_plan = state.get("plan", {})
    target_count = existing_plan.get("target_count", None) if existing_plan else None

    strategy = plan_strategy(target_count)
    print(
        f"[Planner] target_count={target_count}, "
        f"tier={strategy['tier']}, "
        f"per_source_limit={strategy['per_source_limit']}, "
        f"relevance_threshold={strategy['relevance_threshold']}, "
        f"max_iterations={strategy['max_iterations']}"
    )

    return {"plan": strategy}
