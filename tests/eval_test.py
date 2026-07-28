"""
评估测试 — AI 知识库输出质量评估

包含:
  - EVAL_CASES: 正面 / 负面 / 边界三类测试用例
  - 本地结构验证测试（不调用 LLM）
  - 范围断言驱动的 LLM 评估测试
  - LLM-as-Judge 打分测试（标记为 slow）

  -m "not slow" 可跳过所有 LLM 测试，只跑本地验证
"""

import warnings
import os

from dotenv import load_dotenv

load_dotenv()

try:
    from pytest import PytestUnknownMarkWarning
except ImportError:
    PytestUnknownMarkWarning = Warning  # type: ignore[assignment]

warnings.filterwarnings("ignore", category=PytestUnknownMarkWarning)

import pytest

from workflows.model_client import chat_json


# ============================================================
# 评估用例定义
# ============================================================

EVAL_CASES = [
    {
        "name": "positive_tech_article",
        "input": (
            "大型语言模型（LLM）的最新进展：基于 Transformer 架构的 GPT-4、Claude 3 和 "
            "Gemini 模型在代码生成、推理能力和多模态理解方面取得了显著突破。检索增强生成（RAG）"
            "和 Agent 框架（如 LangGraph、AutoGen、CrewAI）正在推动 AI 应用从单一问答向"
            "多步骤自主任务执行演进。"
        ),
        "expected": {
            "summary_min_len": 30,
            "keywords_min_count": 3,
            "relevance_min": 5,
        },
    },
    {
        "name": "negative_irrelevant",
        "input": (
            "今天天气真好，适合出去散步游玩放松心情。晚上去了一家新开的餐厅，品尝了美味的"
            "意大利面。周末打算和朋友一起去爬山，顺便野餐。"
        ),
        "expected": {
            "relevance_max": 3,
            "should_be_low_quality": True,
        },
    },
    {
        "name": "boundary_short_input",
        "input": "AI",
        "expected": {
            "no_crash": True,
            "summary_exists": True,
        },
    },
]

ANALYSIS_SYSTEM_PROMPT = (
    "你是一个严格的技术内容审核者。分析输入内容是否为 AI/技术相关文章，"
    "给出 1-10 分相关度评分、摘要、关键词和分类。只输出 JSON，不要有其他文字。"
)


# ============================================================
# 辅助函数
# ============================================================

def analyze_content(content: str) -> dict:
    """调用 LLM 分析输入内容，返回结构化结果。

    Returns:
        包含 is_tech_relevant, relevance_score, summary, keywords, category 的 dict，
        额外附带 _usage 用量信息。
    """
    prompt = f"""分析以下内容是否为 AI/技术相关文章，并评分（1-10 分）。

内容: "{content}"

返回 JSON（不要有其他文字）:
{{
    "is_tech_relevant": true/false,
    "relevance_score": 1-10,
    "summary": "简要摘要（中文）",
    "keywords": ["关键词1", "关键词2"],
    "category": "技术分类"
}}"""
    result, usage = chat_json(prompt, system=ANALYSIS_SYSTEM_PROMPT)
    result["_usage"] = usage
    return result


def llm_judge(original_input: str, analysis_result: dict) -> tuple[int, str]:
    """LLM-as-Judge: 让 LLM 对分析结果质量打分（1-10）。

    Returns:
        (quality_score: int, reason: str)
    """
    prompt = f"""评估以下分析结果的质量。

原始输入: "{original_input}"

分析结果:
- 是否相关: {analysis_result.get('is_tech_relevant')}
- 相关度评分: {analysis_result.get('relevance_score')}
- 摘要: {analysis_result.get('summary')}
- 关键词: {analysis_result.get('keywords')}
- 分类: {analysis_result.get('category')}

请从 1-10 分评估该分析结果的质量:
- 8-10: 准确、全面、摘要精炼
- 5-7:  基本正确，但有小瑕疵
- 1-4:  明显错误或不完整

返回 JSON（不要有其他文字）:
{{
    "quality_score": 1-10,
    "reason": "评分理由（中文）"
}}"""
    result, _ = chat_json(prompt, system="你是一个严谨的评估裁判。只输出 JSON。")
    return result.get("quality_score", 0), result.get("reason", "")


def _require_api_key():
    """如果 LLM_API_KEY 未设置则跳过测试"""
    if not os.getenv("LLM_API_KEY"):
        pytest.skip("LLM_API_KEY 未设置，跳过 LLM 相关测试")


# ============================================================
# 测试: 本地结构验证（不调用 LLM）
# ============================================================

class TestEvalCasesStructure:
    """验证 EVAL_CASES 的结构合法性 — 纯本地测试，不调用 LLM"""

    def test_eval_cases_is_list(self):
        """EVAL_CASES 应为非空列表"""
        assert isinstance(EVAL_CASES, list)
        assert len(EVAL_CASES) >= 3

    def test_each_case_has_required_fields(self):
        """每个用例必须包含 name, input, expected"""
        required = {"name", "input", "expected"}
        for i, case in enumerate(EVAL_CASES):
            missing = required - set(case.keys())
            assert not missing, f"用例 [{i}] 缺少字段: {missing}"

    def test_names_are_unique(self):
        """所有用例的 name 必须唯一"""
        names = [c["name"] for c in EVAL_CASES]
        assert len(names) == len(set(names)), f"存在重复的 name: {names}"

    def test_inputs_are_nonempty_strings(self):
        """所有 input 应为非空字符串"""
        for case in EVAL_CASES:
            assert isinstance(case["input"], str), (
                f"{case['name']}: input 不是字符串"
            )
            assert len(case["input"]) >= 1, f"{case['name']}: input 为空"

    def test_expected_is_dict(self):
        """expected 字段应为 dict"""
        for case in EVAL_CASES:
            assert isinstance(case["expected"], dict), (
                f"{case['name']}: expected 应为 dict"
            )

    def test_positive_case_has_relevance_min(self):
        """正面案例 expected 应包含 relevance_min 阈值"""
        pos = EVAL_CASES[0]
        assert "relevance_min" in pos["expected"]

    def test_negative_case_has_relevance_max(self):
        """负面案例 expected 应包含 relevance_max 阈值"""
        neg = EVAL_CASES[1]
        assert "relevance_max" in neg["expected"]

    def test_boundary_case_has_no_crash(self):
        """边界案例 expected 应包含 no_crash 标记"""
        bnd = EVAL_CASES[2]
        assert "no_crash" in bnd["expected"]


# ============================================================
# 测试: 范围断言评估（调用 LLM，标记 slow）
# ============================================================

class TestContentAnalysis:
    """调用 LLM 分析内容，使用范围断言验证输出质量"""

    @pytest.fixture(autouse=True)
    def _check_api_key(self):
        _require_api_key()

    @pytest.mark.slow
    def test_positive_article_analysis(self):
        """正面案例: 技术文章应有摘要、关键词和高相关度评分"""
        case = EVAL_CASES[0]
        expected = case["expected"]
        result = analyze_content(case["input"])

        # 范围断言: 摘要长度
        summary = result.get("summary", "")
        assert len(summary) >= expected["summary_min_len"], (
            f"摘要过短 ({len(summary)} < {expected['summary_min_len']}): {summary}"
        )

        # 范围断言: 关键词数量
        keywords = result.get("keywords", [])
        assert len(keywords) >= expected["keywords_min_count"], (
            f"关键词不足 ({len(keywords)} < {expected['keywords_min_count']}): {keywords}"
        )

        # 范围断言: 相关度评分
        score = result.get("relevance_score", 0)
        assert score >= expected["relevance_min"], (
            f"相关度过低 ({score} < {expected['relevance_min']})"
        )

    @pytest.mark.slow
    def test_negative_irrelevant_analysis(self):
        """负面案例: 无关内容应被标记为低相关"""
        case = EVAL_CASES[1]
        expected = case["expected"]
        result = analyze_content(case["input"])

        score = result.get("relevance_score", 10)
        assert score <= expected["relevance_max"], (
            f"期望低相关 (<= {expected['relevance_max']})，实际: {score}"
        )

    @pytest.mark.slow
    def test_boundary_short_input_no_crash(self):
        """边界案例: 极短输入不崩溃且返回有效结果"""
        case = EVAL_CASES[2]
        result = analyze_content(case["input"])

        # 范围断言: 结果存在且为 dict
        assert isinstance(result, dict), "应返回 dict"
        assert isinstance(result.get("summary", None), str), "summary 应为 str"
        assert isinstance(result.get("relevance_score", None), (int, float)), (
            "relevance_score 应为数值"
        )
        # 评分应在有效范围内
        assert 0 <= result.get("relevance_score", -1) <= 10, (
            f"relevance_score 超出范围: {result.get('relevance_score')}"
        )


# ============================================================
# 测试: LLM-as-Judge 打分测试
# ============================================================

class TestLLMJudge:
    """LLM 作为裁判，对分析结果打分"""

    @pytest.fixture(autouse=True)
    def _check_api_key(self):
        _require_api_key()

    @pytest.mark.slow
    def test_llm_judge_score_above_threshold(self):
        """LLM-as-Judge: 对正面案例的分析结果打分，要求 >= 5"""
        case = EVAL_CASES[0]

        result = analyze_content(case["input"])
        quality_score, reason = llm_judge(case["input"], result)

        assert quality_score >= 5, (
            f"LLM-as-Judge 评分过低: {quality_score}/10\n理由: {reason}"
        )
