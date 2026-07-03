"""第五周：LLM 驱动的多 Agent A 股投研系统。

本文件只实现 LLM Agent，不提供规则版、基线版或演示版降级路径。
如果没有配置 LLM API key，程序会直接报错，不会生成伪 Agent 研报。

运行示例：

    python week5/multi_agent_system.py
    python week5/multi_agent_system.py --backend langchain
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from llm_client import LangChainClient, LLMClient
from prompts import PROMPT_TEMPLATES, SYSTEM_GUARDRAILS
from stock_context_builder import (
    FactorItem,
    StockContext,
    build_contexts,
    context_to_markdown,
    format_number,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "week5/outputs"
DEFAULT_SUMMARY_REPORT = ROOT / "week5/stock_deep_report.md"


class TextBackend(Protocol):
    def complete(self, prompt: str) -> str:
        ...


@dataclass(frozen=True)
class AgentOutput:
    """单个 LLM Agent 的输出。"""

    agent_name: str
    title: str
    content: str


class LLMAgents:
    """由 LLM 实际生成分析结论的多 Agent 集合。"""

    def __init__(self, backend: TextBackend) -> None:
        self.backend = backend

    def _run_prompt(self, prompt_key: str, context: StockContext, extra: str = "") -> str:
        prompt = PROMPT_TEMPLATES[prompt_key].format(
            guardrails=SYSTEM_GUARDRAILS,
            stock_context=context_to_markdown(context),
            agent_outputs=extra,
        )
        return self.backend.complete(prompt)

    def data_agent(self, context: StockContext) -> AgentOutput:
        return AgentOutput("DataAgent", "数据摘要", self._run_prompt("data", context))

    def factor_agent(self, context: StockContext) -> AgentOutput:
        return AgentOutput("FactorAgent", "因子画像", self._run_prompt("factor", context))

    def technical_agent(self, context: StockContext) -> AgentOutput:
        return AgentOutput("TechnicalAgent", "技术面和量价状态", self._run_prompt("technical", context))

    def fundamental_agent(self, context: StockContext) -> AgentOutput:
        return AgentOutput("FundamentalAgent", "基本面质量和成长", self._run_prompt("fundamental", context))

    def risk_agent(self, context: StockContext) -> AgentOutput:
        return AgentOutput("RiskAgent", "风险识别", self._run_prompt("risk", context))

    def decision_agent(self, context: StockContext, prior_outputs: list[AgentOutput]) -> AgentOutput:
        extra = "\n\n".join(
            f"## {output.agent_name}：{output.title}\n{output.content}"
            for output in prior_outputs
        )
        return AgentOutput("DecisionAgent", "综合决策", self._run_prompt("decision", context, extra))


def build_agents(backend: str) -> LLMAgents:
    if backend == "llm":
        return LLMAgents(LLMClient())
    if backend == "langchain":
        return LLMAgents(LangChainClient())
    raise ValueError(f"未知 backend：{backend}")


def run_agents_for_stock(context: StockContext, agents: LLMAgents) -> list[AgentOutput]:
    outputs = [
        agents.data_agent(context),
        agents.factor_agent(context),
        agents.technical_agent(context),
        agents.fundamental_agent(context),
        agents.risk_agent(context),
    ]
    outputs.append(agents.decision_agent(context, outputs))
    return outputs


def render_factor_table(context: StockContext) -> str:
    lines = [
        "| 因子 | 类别 | 方向 | 权重 | 原始值 | 标准化得分 | 加权贡献 |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for item in context.factor_items:
        lines.append(
            "| {name} | {category} | {direction} | {weight:.2f} | {raw} | {score} | {weighted} |".format(
                name=item.name,
                category=item.category,
                direction=item.direction_text,
                weight=item.weight,
                raw=format_number(item.raw_value, 4),
                score=format_number(item.score, 4),
                weighted=format_number(item.weighted_score, 4),
            )
        )
    return "\n".join(lines)


def report_filename(context: StockContext) -> str:
    return f"{context.symbol}_{context.name}_report.md"


def render_report(context: StockContext, outputs: list[AgentOutput], backend: str) -> str:
    lines = [
        f"# {context.name}（{context.symbol}）LLM 多 Agent 深度投研报告",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Agent 后端：{backend}",
        "",
        "> 本报告由 LLM 驱动的多 Agent 投研系统生成，基于第四周多因子数据，"
        "用于课程学习和投研流程演示，不构成投资建议。",
        "",
        "## 一、股票概览",
        "",
        f"- 股票代码：{context.symbol}",
        f"- 股票名称：{context.name}",
        f"- 行业：{context.industry}",
        f"- 多因子排名：第 {context.rank} 名",
        f"- 综合得分：{context.composite_score:.4f}",
        "",
        "## 二、因子明细",
        "",
        render_factor_table(context),
        "",
    ]

    for index, output in enumerate(outputs, start=3):
        lines.extend(
            [
                f"## {index}、{output.title}（{output.agent_name}）",
                "",
                output.content,
                "",
            ]
        )

    lines.extend(
        [
            "## 附：LLM Agent 方法说明",
            "",
            "- StockContextBuilder 先读取第四周 final 数据，构建个股研究材料包。",
            "- DataAgent、FactorAgent、TechnicalAgent、FundamentalAgent、RiskAgent 和 DecisionAgent 均通过 LLM 调用生成输出。",
            "- 系统不提供规则版替代路径；如果 LLM API 不可用，程序会失败而不是生成伪研报。",
            "- 所有 prompt 都包含约束：不得编造新闻、政策、公告、券商观点，不输出买卖指令或收益承诺。",
        ]
    )
    return "\n".join(lines)


def write_reports(
    contexts: list[StockContext],
    agents: LLMAgents,
    output_dir: Path,
    summary_path: Path,
    backend: str,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    summary_sections = [
        "# 第五周 TOP5 股票 LLM 多 Agent 深度研报汇总",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Agent 后端：{backend}",
        "",
        "本汇总报告基于第四周沪深300多因子 TOP 股票池生成。"
        "每只股票均由 LLM 驱动的 DataAgent、FactorAgent、TechnicalAgent、"
        "FundamentalAgent、RiskAgent 和 DecisionAgent 分析。",
        "",
        "> 说明：本报告仅用于课程学习和投研流程演示，不构成投资建议。",
        "",
    ]

    for context in contexts:
        outputs = run_agents_for_stock(context, agents)
        report = render_report(context, outputs, backend=backend)
        path = output_dir / report_filename(context)
        path.write_text(report, encoding="utf-8")
        written.append(path)

        summary_sections.extend(
            [
                "---",
                "",
                f"# {context.name}（{context.symbol}）",
                "",
                f"- 多因子排名：第 {context.rank} 名",
                f"- 综合得分：{context.composite_score:.4f}",
                f"- 单股报告：`outputs/{report_filename(context)}`",
                "",
            ]
        )
        for output in outputs:
            summary_sections.extend(
                [
                    f"## {output.title}（{output.agent_name}）",
                    "",
                    output.content,
                    "",
                ]
            )

    summary_path.write_text("\n".join(summary_sections), encoding="utf-8")
    written.append(summary_path)
    return written


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-n", type=int, default=5, help="生成前 N 只股票的深度研报。")
    parser.add_argument(
        "--backend",
        choices=["llm", "langchain"],
        default="llm",
        help="Agent 后端。默认 llm 会直接调用 OpenAI-compatible Chat Completions；langchain 也必须调用 LLM。",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_REPORT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    contexts = build_contexts(top_n=args.top_n)
    agents = build_agents(args.backend)
    written = write_reports(contexts, agents, args.output_dir, args.summary, backend=args.backend)

    print(f"第五周 LLM 多 Agent 研报生成完成，backend={args.backend}")
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
