"""
LangGraph 工作流编排 — 知识库采集→分析→整理→审核→保存 流水线

核心设计：
  collect → analyze → organize → review ─(通过)→ save → END
                                      │
                                      ├── (未通过, iter < 3)  → revise → review (循环)
                                      │
                                      └── (未通过, iter >= 3) → human_flag → END

  plan → sources → analyses → review ─[pass]→ organize → END
                                  ↓
                                revise → review（循环）
                                  ↓[>max]
                                human_flag → END                                    
"""

import sys

from langgraph.graph import END, StateGraph

from workflows.human_flag import human_flag_node
from workflows.analyzer import analyze_node
from workflows.collector import collect_node
from workflows.organizer import organize_node
from workflows.planner import planner_node
from workflows.reviewer import review_node
from workflows.reviser import revise_node
from workflows.state import KBState
from tests.cost_guard import BudgetExceededError
from workflows.model_client import get_cost_guard


def route_after_review(state: KBState) -> str:
    """审核节点后的 3 路条件路由

    读 state["plan"]["max_iterations"]，不再硬编码 3
    根据 review_passed 和 iteration 决定下一步:
      - 通过                      → organize (最终整理后进入 save)
      - 不通过 且 iteration < 3   → revise  (调用 LLM 修正后重新审核)
      - 不通过 且 iteration >= 3  → human_flag (标记人工处理)
    """
    plan = state.get("plan", {}) or {}
    max_iter = int(plan.get("max_iterations", 3))


    if state["review_passed"]:
        return "organize"

    if state.get("iteration", 0) < max_iter:
        return "revise"

    return "human_flag"


def build_graph() -> StateGraph:
    """构建并返回编译后的 LangGraph 工作流

    Returns:
        编译后的 StateGraph 实例 (CompiledGraph)
    """
    graph = StateGraph(KBState)

    graph.add_node("plan", planner_node)
    graph.add_node("collect", collect_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("review", review_node)
    graph.add_node("revise", revise_node)
    graph.add_node("organize", organize_node)
    graph.add_node("human_flag", human_flag_node)

    # 【新增】plan → collect 边
    graph.add_edge("plan", "collect")
    graph.add_edge("collect", "analyze")
    graph.add_edge("analyze", "review")

    graph.add_conditional_edges(
        "review",
        route_after_review,
        {
            "organize": "organize",
            "revise": "revise",
            "human_flag": "human_flag",
        },
    )

    graph.add_edge("revise", "review")

    # 两个终点
    graph.add_edge("organize", END)
    graph.add_edge("human_flag", END)

    # 【修改】入口从 "collect" 改为 "plan"
    graph.set_entry_point("plan")

    return graph.compile()


if __name__ == "__main__":
    app = build_graph()

    initial_state: KBState = {
        "sources": [],
        "analyses": [],
        "articles": [],
        "review_feedback": "",
        "review_passed": False,
        "iteration": 0,
        "cost_tracker": {},
    }

    print("=" * 60)
    print("LangGraph 知识库工作流 启动")
    print("=" * 60)

    try:
        for step in app.stream(initial_state):
            node_name = list(step.keys())[0]
            node_output = step[node_name]

            print(f"\n--- [{node_name}] 节点输出 ---")

            if node_name == "collect":
                count = len(node_output.get("sources", []))
                print(f"  采集数据: {count} 条")

            elif node_name == "analyze":
                count = len(node_output.get("analyses", []))
                print(f"  分析条目: {count} 条")

            elif node_name == "organize":
                articles = node_output.get("articles", [])
                print(f"  整理条目: {len(articles)} 条")
                for art in articles[:3]:
                    print(f"    - {art['id']}: {art['title'][:50]}")

            elif node_name == "review":
                passed = node_output.get("review_passed", False)
                iteration = node_output.get("iteration", 0)
                feedback = node_output.get("review_feedback", "")
                print(f"  审核通过: {passed}")
                print(f"  当前迭代: {iteration}/3")
                if feedback:
                    print(f"  反馈: {feedback[:100]}")

            elif node_name == "revise":
                analyses = node_output.get("analyses", [])
                print(f"  修订 analyses: {len(analyses)} 条（将重新进入审核）")

            elif node_name == "human_flag":
                print(f"  [需人工处理] 自动修订已达上限")

            elif node_name == "save":
                print(f"  已保存到 knowledge/articles/")

    except BudgetExceededError as e:
        guard = get_cost_guard()
        print(f"\n[FATAL] 预算熔断触发：成本已超出预算！当前: ¥{e.total_cost:.4f}, 预算: ¥{e.budget:.2f}")
        report = guard.get_report()
        print(f"[CostGuard] 总调用 {report['summary']['total_calls']} 次 · 总成本 ¥{report['summary']['total_cost_yuan']}")
        print(f"[CostGuard] 按节点：{report['by_node']}")
        guard.save_report()
        sys.exit(0)

    print("\n" + "=" * 60)
    print("工作流执行完成")
    print("=" * 60)

    # ★ 接入点 ③ · 收尾打报告 · 落盘到 knowledge/cost-report.json
    guard = get_cost_guard()
    report = guard.get_report()
    print(f"\n[CostGuard] 总调用 {report['summary']['total_calls']} 次 · 总成本 ¥{report['summary']['total_cost_yuan']}")
    print(f"[CostGuard] 按节点：{report['by_node']}")
    guard.save_report()
