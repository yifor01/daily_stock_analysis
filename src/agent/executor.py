# -*- coding: utf-8 -*-
"""
Agent Executor — ReAct loop with tool calling.

Orchestrates the LLM + tools interaction loop:
1. Build system prompt (persona + tools + skills)
2. Send to LLM with tool declarations
3. If tool_call → execute tool → feed result back
4. If text → parse as final answer
5. Loop until final answer or max_steps

The core execution loop is delegated to :mod:`src.agent.runner` so that
both the legacy single-agent path and future multi-agent runners share the
same implementation.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from src.agent.llm_adapter import LLMToolAdapter
from src.agent.runner import run_agent_loop, parse_dashboard_json
from src.agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


# ============================================================
# Agent result
# ============================================================

@dataclass
class AgentResult:
    """Result from an agent execution run."""
    success: bool = False
    content: str = ""                          # final text answer from agent
    dashboard: Optional[Dict[str, Any]] = None  # parsed dashboard JSON
    tool_calls_log: List[Dict[str, Any]] = field(default_factory=list)  # execution trace
    total_steps: int = 0
    total_tokens: int = 0
    provider: str = ""
    model: str = ""                            # comma-separated models used (supports fallback)
    error: Optional[str] = None


# ============================================================
# System prompt builder
# ============================================================

AGENT_SYSTEM_PROMPT = """你是一位專注於趨勢交易的 A 股投資分析 Agent，擁有資料工具和交易策略，負責生成專業的【決策儀表盤】分析報告。

## 工作流程（必須嚴格按階段順序執行，每階段等工具結果返回後再進入下一階段）

**第一階段 · 行情與K線**（首先執行）
- `get_realtime_quote` 獲取實時行情
- `get_daily_history` 獲取歷史K線

**第二階段 · 技術與籌碼**（等第一階段結果返回後執行）
- `analyze_trend` 獲取技術指標
- `get_chip_distribution` 獲取籌碼分佈

**第三階段 · 情報搜尋**（等前兩階段完成後執行）
- `search_stock_news` 搜尋最新資訊、減持、業績預告等風險訊號

**第四階段 · 生成報告**（所有資料就緒後，輸出完整決策儀表盤 JSON）

> ⚠️ 每階段的工具呼叫必須完整返回結果後，才能進入下一階段。禁止將不同階段的工具合併到同一次呼叫中。

## 核心交易理念（必須嚴格遵守）

### 1. 嚴進策略（不追高）
- **絕對不追高**：當股價偏離 MA5 超過 5% 時，堅決不買入
- 乖離率 < 2%：最佳買點區間
- 乖離率 2-5%：可小倉介入
- 乖離率 > 5%：嚴禁追高！直接判定為"觀望"

### 2. 趨勢交易（順勢而為）
- **多頭排列必須條件**：MA5 > MA10 > MA20
- 只做多頭排列的股票，空頭排列堅決不碰
- 均線發散上行優於均線粘合

### 3. 效率優先（籌碼結構）
- 關注籌碼集中度：90%集中度 < 15% 表示籌碼集中
- 獲利比例分析：70-90% 獲利盤時需警惕獲利回吐
- 平均成本與現價關係：現價高於平均成本 5-15% 為健康

### 4. 買點偏好（回踩支撐）
- **最佳買點**：縮量回踩 MA5 獲得支撐
- **次優買點**：回踩 MA10 獲得支撐
- **觀望情況**：跌破 MA20 時觀望

### 5. 風險排查重點
- 減持公告、業績預虧、監管處罰、行業政策利空、大額解禁

### 6. 估值關注（PE/PB）
- PE 明顯偏高時需在風險點中說明

### 7. 強勢趨勢股放寬
- 強勢趨勢股可適當放寬乖離率要求，輕倉追蹤但需設止損

## 規則

1. **必須呼叫工具獲取真實資料** — 絕不編造數字，所有資料必須來自工具返回結果。
2. **系統化分析** — 嚴格按工作流程分階段執行，每階段完整返回後再進入下一階段，**禁止**將不同階段的工具合併到同一次呼叫中。
3. **應用交易策略** — 評估每個啟用策略的條件，在報告中體現策略判斷結果。
4. **輸出格式** — 最終響應必須是有效的決策儀表盤 JSON。
5. **風險優先** — 必須排查風險（股東減持、業績預警、監管問題）。
6. **工具失敗處理** — 記錄失敗原因，使用已有資料繼續分析，不重複呼叫失敗工具。

{skills_section}

## 輸出格式：決策儀表盤 JSON

你的最終響應必須是以下結構的有效 JSON 物件：

```json
{{
    "stock_name": "股票中文名稱",
    "sentiment_score": 0-100整數,
    "trend_prediction": "強烈看多/看多/震盪/看空/強烈看空",
    "operation_advice": "買入/加倉/持有/減倉/賣出/觀望",
    "decision_type": "buy/hold/sell",
    "confidence_level": "高/中/低",
    "dashboard": {{
        "core_conclusion": {{
            "one_sentence": "一句話核心結論（30字以內）",
            "signal_type": "🟢買入訊號/🟡持有觀望/🔴賣出訊號/⚠️風險警告",
            "time_sensitivity": "立即行動/今日內/本週內/不急",
            "position_advice": {{
                "no_position": "空倉者建議",
                "has_position": "持倉者建議"
            }}
        }},
        "data_perspective": {{
            "trend_status": {{"ma_alignment": "", "is_bullish": true, "trend_score": 0}},
            "price_position": {{"current_price": 0, "ma5": 0, "ma10": 0, "ma20": 0, "bias_ma5": 0, "bias_status": "", "support_level": 0, "resistance_level": 0}},
            "volume_analysis": {{"volume_ratio": 0, "volume_status": "", "turnover_rate": 0, "volume_meaning": ""}},
            "chip_structure": {{"profit_ratio": 0, "avg_cost": 0, "concentration": 0, "chip_health": ""}}
        }},
        "intelligence": {{
            "latest_news": "",
            "risk_alerts": [],
            "positive_catalysts": [],
            "earnings_outlook": "",
            "sentiment_summary": ""
        }},
        "battle_plan": {{
            "sniper_points": {{"ideal_buy": "", "secondary_buy": "", "stop_loss": "", "take_profit": ""}},
            "position_strategy": {{"suggested_position": "", "entry_plan": "", "risk_control": ""}},
            "action_checklist": []
        }}
    }},
    "analysis_summary": "100字綜合分析摘要",
    "key_points": "3-5個核心看點，逗號分隔",
    "risk_warning": "風險提示",
    "buy_reason": "操作理由，引用交易理念",
    "trend_analysis": "走勢形態分析",
    "short_term_outlook": "短期1-3日展望",
    "medium_term_outlook": "中期1-2周展望",
    "technical_analysis": "技術面綜合分析",
    "ma_analysis": "均線系統分析",
    "volume_analysis": "量能分析",
    "pattern_analysis": "K線形態分析",
    "fundamental_analysis": "基本面分析",
    "sector_position": "板塊行業分析",
    "company_highlights": "公司亮點/風險",
    "news_summary": "新聞摘要",
    "market_sentiment": "市場情緒",
    "hot_topics": "相關熱點"
}}
```

## 評分標準

### 強烈買入（80-100分）：
- ✅ 多頭排列：MA5 > MA10 > MA20
- ✅ 低乖離率：<2%，最佳買點
- ✅ 縮量回撥或放量突破
- ✅ 籌碼集中健康
- ✅ 訊息面有利好催化

### 買入（60-79分）：
- ✅ 多頭排列或弱勢多頭
- ✅ 乖離率 <5%
- ✅ 量能正常
- ⚪ 允許一項次要條件不滿足

### 觀望（40-59分）：
- ⚠️ 乖離率 >5%（追高風險）
- ⚠️ 均線纏繞趨勢不明
- ⚠️ 有風險事件

### 賣出/減倉（0-39分）：
- ❌ 空頭排列
- ❌ 跌破MA20
- ❌ 放量下跌
- ❌ 重大利空

## 決策儀表盤核心原則

1. **核心結論先行**：一句話說清該買該賣
2. **分持倉建議**：空倉者和持倉者給不同建議
3. **精確狙擊點**：必須給出具體價格，不說模糊的話
4. **檢查清單視覺化**：用 ✅⚠️❌ 明確顯示每項檢查結果
5. **風險優先順序**：輿情中的風險點要醒目標出
"""

CHAT_SYSTEM_PROMPT = """你是一位專注於趨勢交易的 A 股投資分析 Agent，擁有資料工具和交易策略，負責解答使用者的股票投資問題。

## 分析工作流程（必須嚴格按階段執行，禁止跳步或合併階段）

當使用者詢問某支股票時，必須按以下四個階段順序呼叫工具，每階段等工具結果全部返回後再進入下一階段：

**第一階段 · 行情與K線**（必須先執行）
- 呼叫 `get_realtime_quote` 獲取實時行情和當前價格
- 呼叫 `get_daily_history` 獲取近期歷史K線資料

**第二階段 · 技術與籌碼**（等第一階段結果返回後再執行）
- 呼叫 `analyze_trend` 獲取 MA/MACD/RSI 等技術指標
- 呼叫 `get_chip_distribution` 獲取籌碼分佈結構

**第三階段 · 情報搜尋**（等前兩階段完成後再執行）
- 呼叫 `search_stock_news` 搜尋最新新聞公告、減持、業績預告等風險訊號

**第四階段 · 綜合分析**（所有工具資料就緒後生成回答）
- 基於上述真實資料，結合啟用策略進行綜合研判，輸出投資建議

> ⚠️ 禁止將不同階段的工具合併到同一次呼叫中（例如禁止在第一次呼叫中同時請求行情、技術指標和新聞）。

## 核心交易理念（必須嚴格遵守）

### 1. 嚴進策略（不追高）
- **絕對不追高**：當股價偏離 MA5 超過 5% 時，堅決不買入
- 乖離率 < 2%：最佳買點區間
- 乖離率 2-5%：可小倉介入
- 乖離率 > 5%：嚴禁追高！直接判定為"觀望"

### 2. 趨勢交易（順勢而為）
- **多頭排列必須條件**：MA5 > MA10 > MA20
- 只做多頭排列的股票，空頭排列堅決不碰
- 均線發散上行優於均線粘合

### 3. 效率優先（籌碼結構）
- 關注籌碼集中度：90%集中度 < 15% 表示籌碼集中
- 獲利比例分析：70-90% 獲利盤時需警惕獲利回吐
- 平均成本與現價關係：現價高於平均成本 5-15% 為健康

### 4. 買點偏好（回踩支撐）
- **最佳買點**：縮量回踩 MA5 獲得支撐
- **次優買點**：回踩 MA10 獲得支撐
- **觀望情況**：跌破 MA20 時觀望

### 5. 風險排查重點
- 減持公告、業績預虧、監管處罰、行業政策利空、大額解禁

### 6. 估值關注（PE/PB）
- PE 明顯偏高時需在風險點中說明

### 7. 強勢趨勢股放寬
- 強勢趨勢股可適當放寬乖離率要求，輕倉追蹤但需設止損

## 規則

1. **必須呼叫工具獲取真實資料** — 絕不編造數字，所有資料必須來自工具返回結果。
2. **應用交易策略** — 評估每個啟用策略的條件，在回答中體現策略判斷結果。
3. **自由對話** — 根據使用者的問題，自由組織語言回答，不需要輸出 JSON。
4. **風險優先** — 必須排查風險（股東減持、業績預警、監管問題）。
5. **工具失敗處理** — 記錄失敗原因，使用已有資料繼續分析，不重複呼叫失敗工具。

{skills_section}
"""


# ============================================================
# Agent Executor
# ============================================================

class AgentExecutor:
    """ReAct agent loop with tool calling.

    Usage::

        executor = AgentExecutor(tool_registry, llm_adapter)
        result = executor.run("Analyze stock 600519")
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        llm_adapter: LLMToolAdapter,
        skill_instructions: str = "",
        max_steps: int = 10,
    ):
        self.tool_registry = tool_registry
        self.llm_adapter = llm_adapter
        self.skill_instructions = skill_instructions
        self.max_steps = max_steps

    def run(self, task: str, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        """Execute the agent loop for a given task.

        Args:
            task: The user task / analysis request.
            context: Optional context dict (e.g., {"stock_code": "600519"}).

        Returns:
            AgentResult with parsed dashboard or error.
        """
        # Build system prompt with skills
        skills_section = ""
        if self.skill_instructions:
            skills_section = f"## 啟用的交易策略\n\n{self.skill_instructions}"
        system_prompt = AGENT_SYSTEM_PROMPT.format(skills_section=skills_section)

        # Build tool declarations in OpenAI format (litellm handles all providers)
        tool_decls = self.tool_registry.to_openai_tools()

        # Initialize conversation
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": self._build_user_message(task, context)},
        ]

        return self._run_loop(messages, tool_decls, parse_dashboard=True)

    def chat(self, message: str, session_id: str, progress_callback: Optional[Callable] = None, context: Optional[Dict[str, Any]] = None) -> AgentResult:
        """Execute the agent loop for a free-form chat message.

        Args:
            message: The user's chat message.
            session_id: The conversation session ID.
            progress_callback: Optional callback for streaming progress events.
            context: Optional context dict from previous analysis for data reuse.

        Returns:
            AgentResult with the text response.
        """
        from src.agent.conversation import conversation_manager

        # Build system prompt with skills
        skills_section = ""
        if self.skill_instructions:
            skills_section = f"## 啟用的交易策略\n\n{self.skill_instructions}"
        system_prompt = CHAT_SYSTEM_PROMPT.format(skills_section=skills_section)

        # Build tool declarations in OpenAI format (litellm handles all providers)
        tool_decls = self.tool_registry.to_openai_tools()

        # Get conversation history
        session = conversation_manager.get_or_create(session_id)
        history = session.get_history()

        # Initialize conversation
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]
        messages.extend(history)

        # Inject previous analysis context if provided (data reuse from report follow-up)
        if context:
            context_parts = []
            if context.get("stock_code"):
                context_parts.append(f"股票程式碼: {context['stock_code']}")
            if context.get("stock_name"):
                context_parts.append(f"股票名稱: {context['stock_name']}")
            if context.get("previous_price"):
                context_parts.append(f"上次分析價格: {context['previous_price']}")
            if context.get("previous_change_pct"):
                context_parts.append(f"上次漲跌幅: {context['previous_change_pct']}%")
            if context.get("previous_analysis_summary"):
                summary = context["previous_analysis_summary"]
                summary_text = json.dumps(summary, ensure_ascii=False) if isinstance(summary, dict) else str(summary)
                context_parts.append(f"上次分析摘要:\n{summary_text}")
            if context.get("previous_strategy"):
                strategy = context["previous_strategy"]
                strategy_text = json.dumps(strategy, ensure_ascii=False) if isinstance(strategy, dict) else str(strategy)
                context_parts.append(f"上次策略分析:\n{strategy_text}")
            if context_parts:
                context_msg = "[系統提供的歷史分析上下文，可供參考對比]\n" + "\n".join(context_parts)
                messages.append({"role": "user", "content": context_msg})
                messages.append({"role": "assistant", "content": "好的，我已瞭解該股票的歷史分析資料。請告訴我你想了解什麼？"})

        messages.append({"role": "user", "content": message})

        # Persist the user turn immediately so the session appears in history during processing
        conversation_manager.add_message(session_id, "user", message)

        result = self._run_loop(messages, tool_decls, parse_dashboard=False, progress_callback=progress_callback)

        # Persist assistant reply (or error note) for context continuity
        if result.success:
            conversation_manager.add_message(session_id, "assistant", result.content)
        else:
            error_note = f"[分析失敗] {result.error or '未知錯誤'}"
            conversation_manager.add_message(session_id, "assistant", error_note)

        return result

    def _run_loop(self, messages: List[Dict[str, Any]], tool_decls: List[Dict[str, Any]], parse_dashboard: bool, progress_callback: Optional[Callable] = None) -> AgentResult:
        """Delegate to the shared runner and adapt the result.

        This preserves the exact same observable behaviour as the original
        inline implementation while sharing the single authoritative loop
        in :mod:`src.agent.runner`.
        """
        loop_result = run_agent_loop(
            messages=messages,
            tool_registry=self.tool_registry,
            llm_adapter=self.llm_adapter,
            max_steps=self.max_steps,
            progress_callback=progress_callback,
        )

        model_str = loop_result.model

        if parse_dashboard and loop_result.success:
            dashboard = parse_dashboard_json(loop_result.content)
            return AgentResult(
                success=dashboard is not None,
                content=loop_result.content,
                dashboard=dashboard,
                tool_calls_log=loop_result.tool_calls_log,
                total_steps=loop_result.total_steps,
                total_tokens=loop_result.total_tokens,
                provider=loop_result.provider,
                model=model_str,
                error=None if dashboard else "Failed to parse dashboard JSON from agent response",
            )

        return AgentResult(
            success=loop_result.success,
            content=loop_result.content,
            dashboard=None,
            tool_calls_log=loop_result.tool_calls_log,
            total_steps=loop_result.total_steps,
            total_tokens=loop_result.total_tokens,
            provider=loop_result.provider,
            model=model_str,
            error=loop_result.error,
        )

    def _build_user_message(self, task: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Build the initial user message."""
        parts = [task]
        if context:
            if context.get("stock_code"):
                parts.append(f"\n股票程式碼: {context['stock_code']}")
            if context.get("report_type"):
                parts.append(f"報告型別: {context['report_type']}")

            # Inject pre-fetched context data to avoid redundant fetches
            if context.get("realtime_quote"):
                parts.append(f"\n[系統已獲取的實時行情]\n{json.dumps(context['realtime_quote'], ensure_ascii=False)}")
            if context.get("chip_distribution"):
                parts.append(f"\n[系統已獲取的籌碼分佈]\n{json.dumps(context['chip_distribution'], ensure_ascii=False)}")
            if context.get("news_context"):
                parts.append(f"\n[系統已獲取的新聞與輿情情報]\n{context['news_context']}")

        parts.append("\n請使用可用工具獲取缺失的資料（如歷史K線、新聞等），然後以決策儀表盤 JSON 格式輸出分析結果。")
        return "\n".join(parts)
