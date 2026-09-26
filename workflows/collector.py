"""
采集节点 — 从 GitHub Search API 获取 AI 相关仓库

使用 urllib.request 发送请求，获取最近一周更新的高星标仓库。
网络失败时记录错误但不中断流程。
"""

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from tests.security import sanitize_input 

from workflows.state import KBState


def collect_node(state: KBState) -> dict:
    """采集节点：调用 GitHub Search API 搜索 AI/LLM/Agent 相关仓库"""
    print("[Collector] 开始采集...")

    plan = state.get("plan", {}) or {}
    per_source_limit = int(plan.get("per_source_limit", 10))

    sources: list[dict] = []

    github_token = os.getenv("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github.v3+json"}
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    one_week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    query = f"ai agent llm stars:>100 pushed:>{one_week_ago}"
    url = f"https://api.github.com/search/repositories?q={urllib.parse.quote(query)}&sort=stars&per_page={per_source_limit}"

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())

        for repo in data.get("items", []):
            sources.append({
                "source": "github",
                "title": repo["full_name"],
                "url": repo["html_url"],
                "description": repo.get("description", ""),
                "stars": repo.get("stargazers_count", 0),
                "language": repo.get("language", ""),
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })
    except Exception as e:
        print(f"[Collector] GitHub API 请求失败: {e}")
        sources.append({
            "source": "github",
            "title": "[ERROR] GitHub API 请求失败",
            "url": "",
            "description": str(e),
            "stars": 0,
            "language": "",
            "collected_at": datetime.now(timezone.utc).isoformat(),
        })

    # ★ 接入点 ④ · 出 collect 之前对每条 source 的文本字段做清洗
    cleaned_sources = []
    total_warnings = 0
    for s in sources:
        for field in ("title", "description"):
            if field in s and isinstance(s[field], str):
                cleaned, warnings = sanitize_input(s[field])
                s[field] = cleaned
                total_warnings += len(warnings)
                if warnings:
                    print(f"[Security] {s.get('url', '?')} {field} 检出注入模式：{warnings}")
        cleaned_sources.append(s)

    if total_warnings > 0:
        print(f"[Security] collect 阶段共拦截 {total_warnings} 处可疑输入")

    error_count = sum(
        1 for s in cleaned_sources
        if s.get("title", "").startswith("[ERROR]")
    )
    normal_count = len(cleaned_sources) - error_count
    print(
        f"[Collector] 采集完成 — 正常 {normal_count} 条, "
        f"错误 {error_count} 条"
    )

    return {"sources": cleaned_sources}
