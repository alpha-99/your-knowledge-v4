"""
成本守卫 — 多 Agent 预算控制与 Token 用量追踪

三重保护机制:
  1. record(): 记录每次 LLM 调用，逐笔追踪 token 用量和成本
  2. check():  检查预算状态，触发预警（warning）或超限异常（BudgetExceededError）
  3. get_report(): 生成按节点分组的成本报告，save_report() 持久化到 JSON

用途: 生产环境中作为 LangGraph 工作流的成本防火墙，防止 LLM 调用费用失控。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class BudgetExceededError(Exception):
    """预算超限异常 — 当 LLM 调用累计费用超过预设预算时抛出"""

    def __init__(self, total_cost: float, budget: float, message: str = ""):
        self.total_cost = total_cost
        self.budget = budget
        super().__init__(
            message or f"预算超限: 累计费用 ¥{total_cost:.4f} 超过预算 ¥{budget:.2f}"
        )


@dataclass
class CostRecord:
    """单次 LLM 调用成本记录"""

    timestamp: str
    node_name: str
    prompt_tokens: int
    completion_tokens: int
    cost_yuan: float
    model: str = ""


class CostGuard:
    """多 Agent 预算守卫 — 追踪 LLM 调用成本、预警并防止预算超支"""

    def __init__(
        self,
        budget_yuan: float = 1.0,
        alert_threshold: float = 0.8,
        input_price_per_million: float = 1.0,
        output_price_per_million: float = 2.0,
    ):
        self.budget_yuan = budget_yuan
        self.alert_threshold = alert_threshold
        self.input_price_per_million = input_price_per_million
        self.output_price_per_million = output_price_per_million

        self._records: list[CostRecord] = []
        self._total_prompt_tokens: int = 0
        self._total_completion_tokens: int = 0
        self._total_cost_yuan: float = 0.0

    # ------------------------------------------------------------------
    # 第一重保护: 逐笔记录
    # ------------------------------------------------------------------

    def record(
        self,
        node_name: str,
        usage: dict,
        model: str = "",
    ) -> CostRecord:
        """记录一次 LLM 调用

        Args:
            node_name: 调用节点名（如 "analyze", "review"）
            usage: {"prompt_tokens": int, "completion_tokens": int}
            model: 模型名称，默认从环境变量 LLM_MODEL 读取

        Returns:
            本次调用的 CostRecord
        """
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        cost_yuan = round(
            (prompt_tokens * self.input_price_per_million
             + completion_tokens * self.output_price_per_million)
            / 1_000_000,
            6,
        )

        if not model:
            model = os.getenv("LLM_MODEL", "")

        record = CostRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            node_name=node_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_yuan=cost_yuan,
            model=model,
        )

        self._records.append(record)
        self._total_prompt_tokens += prompt_tokens
        self._total_completion_tokens += completion_tokens
        self._total_cost_yuan = round(self._total_cost_yuan + cost_yuan, 6)

        return record

    # ------------------------------------------------------------------
    # 第二重保护: 预算检查 (预警 / 超限异常)
    # ------------------------------------------------------------------

    @property
    def total_prompt_tokens(self) -> int:
        return self._total_prompt_tokens

    @property
    def total_completion_tokens(self) -> int:
        return self._total_completion_tokens

    @property
    def total_cost_yuan(self) -> float:
        return self._total_cost_yuan

    @property
    def record_count(self) -> int:
        return len(self._records)

    def check(self) -> dict:
        """检查预算状态

        Returns:
            {"status": "ok"|"warning", "total_cost": float,
             "budget": float, "usage_ratio": float, "message": str}

        Raises:
            BudgetExceededError: 累计费用超过预算时抛出
        """
        usage_ratio = self._total_cost_yuan / self.budget_yuan if self.budget_yuan > 0 else 1.0

        if self._total_cost_yuan > self.budget_yuan:
            raise BudgetExceededError(
                total_cost=self._total_cost_yuan,
                budget=self.budget_yuan,
                message=(
                    f"预算超限! 已花费 ¥{self._total_cost_yuan:.4f} / "
                    f"¥{self.budget_yuan:.2f} ({usage_ratio:.1%})"
                ),
            )

        if usage_ratio >= self.alert_threshold:
            return {
                "status": "warning",
                "total_cost": self._total_cost_yuan,
                "budget": self.budget_yuan,
                "usage_ratio": round(usage_ratio, 4),
                "message": (
                    f"预算预警: 已使用 {usage_ratio:.1%} "
                    f"(¥{self._total_cost_yuan:.4f} / ¥{self.budget_yuan:.2f})"
                ),
            }

        return {
            "status": "ok",
            "total_cost": self._total_cost_yuan,
            "budget": self.budget_yuan,
            "usage_ratio": round(usage_ratio, 4),
            "message": (
                f"预算正常: 已使用 {usage_ratio:.1%} "
                f"(¥{self._total_cost_yuan:.4f} / ¥{self.budget_yuan:.2f})"
            ),
        }

    # ------------------------------------------------------------------
    # 第三重保护: 成本报告 (分组统计 / 持久化)
    # ------------------------------------------------------------------

    def get_report(self) -> dict:
        """生成按节点分组的成本报告

        Returns:
            {
                "summary": {总体统计},
                "by_node": {node_name: {统计信息}, ...},
                "records": [所有 CostRecord],
            }
        """
        by_node: dict[str, dict] = {}

        for rec in self._records:
            if rec.node_name not in by_node:
                by_node[rec.node_name] = {
                    "calls": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "cost_yuan": 0.0,
                }
            node = by_node[rec.node_name]
            node["calls"] += 1
            node["prompt_tokens"] += rec.prompt_tokens
            node["completion_tokens"] += rec.completion_tokens
            node["cost_yuan"] = round(node["cost_yuan"] + rec.cost_yuan, 6)

        return {
            "summary": {
                "total_calls": self.record_count,
                "total_prompt_tokens": self._total_prompt_tokens,
                "total_completion_tokens": self._total_completion_tokens,
                "total_cost_yuan": self._total_cost_yuan,
                "budget_yuan": self.budget_yuan,
                "usage_ratio": round(
                    self._total_cost_yuan / self.budget_yuan, 4
                ) if self.budget_yuan > 0 else 1.0,
            },
            "by_node": by_node,
            "records": [
                {
                    "timestamp": r.timestamp,
                    "node_name": r.node_name,
                    "prompt_tokens": r.prompt_tokens,
                    "completion_tokens": r.completion_tokens,
                    "cost_yuan": r.cost_yuan,
                    "model": r.model,
                }
                for r in self._records
            ],
        }

    def save_report(self, path: str | None = None) -> str:
        """保存成本报告到 JSON 文件

        Args:
            path: 输出路径，默认为 data/cost_report_{YYYY-MM-DD}.json

        Returns:
            实际保存的文件路径
        """
        if path is None:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            os.makedirs("data", exist_ok=True)
            path = f"data/cost_report_{date_str}.json"

        report = self.get_report()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return path


if __name__ == "__main__":
    # ------------------------------------------------------------------
    # 测试 1: 成本追踪正确性
    # ------------------------------------------------------------------
    print("=" * 60)
    print("测试 1: 成本追踪正确性")
    print("=" * 60)

    guard1 = CostGuard(budget_yuan=1.0)
    guard1.record("analyze", {"prompt_tokens": 100_000, "completion_tokens": 50_000})
    guard1.record("organize", {"prompt_tokens": 200_000, "completion_tokens": 100_000})

    expected_cost = (300_000 * 1.0 + 150_000 * 2.0) / 1_000_000  # 0.6
    assert guard1.total_prompt_tokens == 300_000, (
        f"total_prompt_tokens 应为 300000, 实际 {guard1.total_prompt_tokens}"
    )
    assert guard1.total_completion_tokens == 150_000, (
        f"total_completion_tokens 应为 150000, 实际 {guard1.total_completion_tokens}"
    )
    assert guard1.total_cost_yuan == expected_cost, (
        f"total_cost_yuan 应为 {expected_cost}, 实际 {guard1.total_cost_yuan}"
    )
    assert guard1.record_count == 2, (
        f"record_count 应为 2, 实际 {guard1.record_count}"
    )

    status1 = guard1.check()
    assert status1["status"] == "ok", f"status 应为 ok, 实际 {status1['status']}"

    print(f"  total_prompt_tokens: {guard1.total_prompt_tokens}")
    print(f"  total_completion_tokens: {guard1.total_completion_tokens}")
    print(f"  total_cost_yuan: {guard1.total_cost_yuan}")
    print(f"  check(): {status1}")
    print("  通过")

    # ------------------------------------------------------------------
    # 测试 2: 预算超限检测
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    print("测试 2: 预算超限检测 (BudgetExceededError)")
    print("=" * 60)

    guard2 = CostGuard(budget_yuan=1.0, alert_threshold=0.8)
    guard2.record("collect", {"prompt_tokens": 600_000, "completion_tokens": 0})
    guard2.record("analyze", {"prompt_tokens": 500_000, "completion_tokens": 0})

    try:
        guard2.check()
        print("  失败: 应抛出 BudgetExceededError 但没有")
        raise SystemExit(1)
    except BudgetExceededError as e:
        print(f"  正确抛出 BudgetExceededError: {e}")
        print(f"    total_cost=¥{e.total_cost:.4f}, budget=¥{e.budget:.2f}")
        print("  通过")

    # ------------------------------------------------------------------
    # 测试 3: 预警阈值触发
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    print("测试 3: 预警阈值触发 (status=warning)")
    print("=" * 60)

    guard3 = CostGuard(budget_yuan=1.0, alert_threshold=0.8)
    guard3.record("analyze", {"prompt_tokens": 500_000, "completion_tokens": 0})
    guard3.record("organize", {"prompt_tokens": 350_000, "completion_tokens": 0})

    status3 = guard3.check()
    assert status3["status"] == "warning", (
        f"status 应为 warning, 实际 {status3['status']}"
    )
    assert status3["usage_ratio"] >= 0.8, (
        f"usage_ratio 应 >= 0.8, 实际 {status3['usage_ratio']}"
    )

    print(f"  total_cost_yuan: {guard3.total_cost_yuan}")
    print(f"  check(): {status3}")
    print("  通过")

    # ------------------------------------------------------------------
    # 测试 4: get_report / save_report
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    print("测试 4: 成本报告生成与保存")
    print("=" * 60)

    report = guard3.get_report()
    assert "summary" in report
    assert "by_node" in report
    assert "records" in report
    assert "analyze" in report["by_node"]
    assert "organize" in report["by_node"]
    assert report["summary"]["total_calls"] == 2

    saved_path = guard3.save_report()
    assert os.path.exists(saved_path), f"报告文件未生成: {saved_path}"

    with open(saved_path, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded["summary"]["total_calls"] == 2

    os.remove(saved_path)
    os.rmdir("data")

    print(f"  报告已生成: {saved_path} (已清理)")
    print("  通过")

    # ------------------------------------------------------------------
    # 汇总
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    print("全部测试通过")
    print("=" * 60)
