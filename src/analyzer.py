# -*- coding: utf-8 -*-
"""
===================================
A股自選股智慧分析系統 - AI分析層
===================================

職責：
1. 封裝 LLM 呼叫邏輯（透過 LiteLLM 統一呼叫 Gemini/Anthropic/OpenAI 等）
2. 結合技術面和訊息面生成分析報告
3. 解析 LLM 響應為結構化 AnalysisResult
"""

import json
import logging
import math
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Tuple

import litellm
from json_repair import repair_json
from litellm import Router

from src.agent.llm_adapter import get_thinking_extra_body
from src.config import (
    Config,
    extra_litellm_params,
    get_api_keys_for_model,
    get_config,
    get_configured_llm_models,
    resolve_news_window_days,
)
from src.storage import persist_llm_usage
from src.data.stock_mapping import STOCK_NAME_MAP
from src.schemas.report_schema import AnalysisReportSchema

logger = logging.getLogger(__name__)


def check_content_integrity(result: "AnalysisResult") -> Tuple[bool, List[str]]:
    """
    Check mandatory fields for report content integrity.
    Returns (pass, missing_fields). Module-level for use by pipeline (agent weak mode).
    """
    missing: List[str] = []
    if result.sentiment_score is None:
        missing.append("sentiment_score")
    advice = result.operation_advice
    if not advice or not isinstance(advice, str) or not advice.strip():
        missing.append("operation_advice")
    summary = result.analysis_summary
    if not summary or not isinstance(summary, str) or not summary.strip():
        missing.append("analysis_summary")
    dash = result.dashboard if isinstance(result.dashboard, dict) else {}
    core = dash.get("core_conclusion")
    core = core if isinstance(core, dict) else {}
    if not (core.get("one_sentence") or "").strip():
        missing.append("dashboard.core_conclusion.one_sentence")
    intel = dash.get("intelligence")
    intel = intel if isinstance(intel, dict) else None
    if intel is None or "risk_alerts" not in intel:
        missing.append("dashboard.intelligence.risk_alerts")
    if result.decision_type in ("buy", "hold"):
        battle = dash.get("battle_plan")
        battle = battle if isinstance(battle, dict) else {}
        sp = battle.get("sniper_points")
        sp = sp if isinstance(sp, dict) else {}
        stop_loss = sp.get("stop_loss")
        if stop_loss is None or (isinstance(stop_loss, str) and not stop_loss.strip()):
            missing.append("dashboard.battle_plan.sniper_points.stop_loss")
    return len(missing) == 0, missing


def apply_placeholder_fill(result: "AnalysisResult", missing_fields: List[str]) -> None:
    """Fill missing mandatory fields with placeholders (in-place). Module-level for pipeline."""
    for field in missing_fields:
        if field == "sentiment_score":
            result.sentiment_score = 50
        elif field == "operation_advice":
            result.operation_advice = result.operation_advice or "待補充"
        elif field == "analysis_summary":
            result.analysis_summary = result.analysis_summary or "待補充"
        elif field == "dashboard.core_conclusion.one_sentence":
            if not result.dashboard:
                result.dashboard = {}
            if "core_conclusion" not in result.dashboard:
                result.dashboard["core_conclusion"] = {}
            result.dashboard["core_conclusion"]["one_sentence"] = (
                result.dashboard["core_conclusion"].get("one_sentence") or "待補充"
            )
        elif field == "dashboard.intelligence.risk_alerts":
            if not result.dashboard:
                result.dashboard = {}
            if "intelligence" not in result.dashboard:
                result.dashboard["intelligence"] = {}
            if "risk_alerts" not in result.dashboard["intelligence"]:
                result.dashboard["intelligence"]["risk_alerts"] = []
        elif field == "dashboard.battle_plan.sniper_points.stop_loss":
            if not result.dashboard:
                result.dashboard = {}
            if "battle_plan" not in result.dashboard:
                result.dashboard["battle_plan"] = {}
            if "sniper_points" not in result.dashboard["battle_plan"]:
                result.dashboard["battle_plan"]["sniper_points"] = {}
            result.dashboard["battle_plan"]["sniper_points"]["stop_loss"] = "待補充"


# ---------- chip_structure fallback (Issue #589) ----------

_CHIP_KEYS: tuple = ("profit_ratio", "avg_cost", "concentration", "chip_health")


def _is_value_placeholder(v: Any) -> bool:
    """True if value is empty or placeholder (N/A, 資料缺失, etc.)."""
    if v is None:
        return True
    if isinstance(v, (int, float)) and v == 0:
        return True
    s = str(v).strip().lower()
    return s in ("", "n/a", "na", "資料缺失", "未知")


def _safe_float(v: Any, default: float = 0.0) -> float:
    """Safely convert to float; return default on failure. Private helper for chip fill."""
    if v is None:
        return default
    if isinstance(v, (int, float)):
        try:
            return default if math.isnan(float(v)) else float(v)
        except (ValueError, TypeError):
            return default
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return default


def _derive_chip_health(profit_ratio: float, concentration_90: float) -> str:
    """Derive chip_health from profit_ratio and concentration_90."""
    if profit_ratio >= 0.9:
        return "警惕"  # 獲利盤極高
    if concentration_90 >= 0.25:
        return "警惕"  # 籌碼分散
    if concentration_90 < 0.15 and 0.3 <= profit_ratio < 0.9:
        return "健康"  # 集中且獲利比例適中
    return "一般"


def _build_chip_structure_from_data(chip_data: Any) -> Dict[str, Any]:
    """Build chip_structure dict from ChipDistribution or dict."""
    if hasattr(chip_data, "profit_ratio"):
        pr = _safe_float(chip_data.profit_ratio)
        ac = chip_data.avg_cost
        c90 = _safe_float(chip_data.concentration_90)
    else:
        d = chip_data if isinstance(chip_data, dict) else {}
        pr = _safe_float(d.get("profit_ratio"))
        ac = d.get("avg_cost")
        c90 = _safe_float(d.get("concentration_90"))
    chip_health = _derive_chip_health(pr, c90)
    return {
        "profit_ratio": f"{pr:.1%}",
        "avg_cost": ac if (ac is not None and _safe_float(ac) != 0.0) else "N/A",
        "concentration": f"{c90:.2%}",
        "chip_health": chip_health,
    }


def fill_chip_structure_if_needed(result: "AnalysisResult", chip_data: Any) -> None:
    """When chip_data exists, fill chip_structure placeholder fields from chip_data (in-place)."""
    if not result or not chip_data:
        return
    try:
        if not result.dashboard:
            result.dashboard = {}
        dash = result.dashboard
        # Use `or {}` rather than setdefault so that an explicit `null` from LLM is also replaced
        dp = dash.get("data_perspective") or {}
        dash["data_perspective"] = dp
        cs = dp.get("chip_structure") or {}
        filled = _build_chip_structure_from_data(chip_data)
        # Start from a copy of cs to preserve any extra keys the LLM may have added
        merged = dict(cs)
        for k in _CHIP_KEYS:
            if _is_value_placeholder(merged.get(k)):
                merged[k] = filled[k]
        if merged != cs:
            dp["chip_structure"] = merged
            logger.info("[chip_structure] Filled placeholder chip fields from data source (Issue #589)")
    except Exception as e:
        logger.warning("[chip_structure] Fill failed, skipping: %s", e)


_PRICE_POS_KEYS = ("ma5", "ma10", "ma20", "bias_ma5", "bias_status", "current_price", "support_level", "resistance_level")


def fill_price_position_if_needed(
    result: "AnalysisResult",
    trend_result: Any = None,
    realtime_quote: Any = None,
) -> None:
    """Fill missing price_position fields from trend_result / realtime data (in-place)."""
    if not result:
        return
    try:
        if not result.dashboard:
            result.dashboard = {}
        dash = result.dashboard
        dp = dash.get("data_perspective") or {}
        dash["data_perspective"] = dp
        pp = dp.get("price_position") or {}

        computed: Dict[str, Any] = {}
        if trend_result:
            tr = trend_result if isinstance(trend_result, dict) else (
                trend_result.__dict__ if hasattr(trend_result, "__dict__") else {}
            )
            computed["ma5"] = tr.get("ma5")
            computed["ma10"] = tr.get("ma10")
            computed["ma20"] = tr.get("ma20")
            computed["bias_ma5"] = tr.get("bias_ma5")
            computed["current_price"] = tr.get("current_price")
            support_levels = tr.get("support_levels") or []
            resistance_levels = tr.get("resistance_levels") or []
            if support_levels:
                computed["support_level"] = support_levels[0]
            if resistance_levels:
                computed["resistance_level"] = resistance_levels[0]
        if realtime_quote:
            rq = realtime_quote if isinstance(realtime_quote, dict) else (
                realtime_quote.to_dict() if hasattr(realtime_quote, "to_dict") else {}
            )
            if _is_value_placeholder(computed.get("current_price")):
                computed["current_price"] = rq.get("price")

        filled = False
        for k in _PRICE_POS_KEYS:
            if _is_value_placeholder(pp.get(k)) and not _is_value_placeholder(computed.get(k)):
                pp[k] = computed[k]
                filled = True
        if filled:
            dp["price_position"] = pp
            logger.info("[price_position] Filled placeholder fields from computed data")
    except Exception as e:
        logger.warning("[price_position] Fill failed, skipping: %s", e)


def get_stock_name_multi_source(
    stock_code: str,
    context: Optional[Dict] = None,
    data_manager = None
) -> str:
    """
    多來源獲取股票中文名稱

    獲取策略（按優先順序）：
    1. 從傳入的 context 中獲取（realtime 資料）
    2. 從靜態對映表 STOCK_NAME_MAP 獲取
    3. 從 DataFetcherManager 獲取（各資料來源）
    4. 返回預設名稱（股票+程式碼）

    Args:
        stock_code: 股票程式碼
        context: 分析上下文（可選）
        data_manager: DataFetcherManager 例項（可選）

    Returns:
        股票中文名稱
    """
    # 1. 從上下文獲取（實時行情資料）
    if context:
        # 優先從 stock_name 欄位獲取
        if context.get('stock_name'):
            name = context['stock_name']
            if name and not name.startswith('股票'):
                return name

        # 其次從 realtime 資料獲取
        if 'realtime' in context and context['realtime'].get('name'):
            return context['realtime']['name']

    # 2. 從靜態對映表獲取
    if stock_code in STOCK_NAME_MAP:
        return STOCK_NAME_MAP[stock_code]

    # 3. 從資料來源獲取
    if data_manager is None:
        try:
            from data_provider.base import DataFetcherManager
            data_manager = DataFetcherManager()
        except Exception as e:
            logger.debug(f"無法初始化 DataFetcherManager: {e}")

    if data_manager:
        try:
            name = data_manager.get_stock_name(stock_code)
            if name:
                # 更新快取
                STOCK_NAME_MAP[stock_code] = name
                return name
        except Exception as e:
            logger.debug(f"從資料來源獲取股票名稱失敗: {e}")

    # 4. 返回預設名稱
    return f'股票{stock_code}'


@dataclass
class AnalysisResult:
    """
    AI 分析結果資料類 - 決策儀表盤版

    封裝 Gemini 返回的分析結果，包含決策儀表盤和詳細分析
    """
    code: str
    name: str

    # ========== 核心指標 ==========
    sentiment_score: int  # 綜合評分 0-100 (>70強烈看多, >60看多, 40-60震盪, <40看空)
    trend_prediction: str  # 趨勢預測：強烈看多/看多/震盪/看空/強烈看空
    operation_advice: str  # 操作建議：買入/加倉/持有/減倉/賣出/觀望
    decision_type: str = "hold"  # 決策型別：buy/hold/sell（用於統計）
    confidence_level: str = "中"  # 置信度：高/中/低

    # ========== 決策儀表盤 (新增) ==========
    dashboard: Optional[Dict[str, Any]] = None  # 完整的決策儀表盤資料

    # ========== 走勢分析 ==========
    trend_analysis: str = ""  # 走勢形態分析（支撐位、壓力位、趨勢線等）
    short_term_outlook: str = ""  # 短期展望（1-3日）
    medium_term_outlook: str = ""  # 中期展望（1-2周）

    # ========== 技術面分析 ==========
    technical_analysis: str = ""  # 技術指標綜合分析
    ma_analysis: str = ""  # 均線分析（多頭/空頭排列，金叉/死叉等）
    volume_analysis: str = ""  # 量能分析（放量/縮量，主力動向等）
    pattern_analysis: str = ""  # K線形態分析

    # ========== 基本面分析 ==========
    fundamental_analysis: str = ""  # 基本面綜合分析
    sector_position: str = ""  # 板塊地位和行業趨勢
    company_highlights: str = ""  # 公司亮點/風險點

    # ========== 情緒面/訊息面分析 ==========
    news_summary: str = ""  # 近期重要新聞/公告摘要
    market_sentiment: str = ""  # 市場情緒分析
    hot_topics: str = ""  # 相關熱點話題

    # ========== 綜合分析 ==========
    analysis_summary: str = ""  # 綜合分析摘要
    key_points: str = ""  # 核心看點（3-5個要點）
    risk_warning: str = ""  # 風險提示
    buy_reason: str = ""  # 買入/賣出理由

    # ========== 後設資料 ==========
    market_snapshot: Optional[Dict[str, Any]] = None  # 當日行情快照（展示用）
    raw_response: Optional[str] = None  # 原始響應（除錯用）
    search_performed: bool = False  # 是否執行了聯網搜尋
    data_sources: str = ""  # 資料來源說明
    success: bool = True
    error_message: Optional[str] = None

    # ========== 價格資料（分析時快照）==========
    current_price: Optional[float] = None  # 分析時的股價
    change_pct: Optional[float] = None     # 分析時的漲跌幅(%)

    # ========== 模型標記（Issue #528）==========
    model_used: Optional[str] = None  # 分析使用的 LLM 模型（完整名，如 gemini/gemini-2.0-flash）

    # ========== 歷史對比（Report Engine P0）==========
    query_id: Optional[str] = None  # 本次分析 query_id，用於歷史對比時排除本次記錄

    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        return {
            'code': self.code,
            'name': self.name,
            'sentiment_score': self.sentiment_score,
            'trend_prediction': self.trend_prediction,
            'operation_advice': self.operation_advice,
            'decision_type': self.decision_type,
            'confidence_level': self.confidence_level,
            'dashboard': self.dashboard,  # 決策儀表盤資料
            'trend_analysis': self.trend_analysis,
            'short_term_outlook': self.short_term_outlook,
            'medium_term_outlook': self.medium_term_outlook,
            'technical_analysis': self.technical_analysis,
            'ma_analysis': self.ma_analysis,
            'volume_analysis': self.volume_analysis,
            'pattern_analysis': self.pattern_analysis,
            'fundamental_analysis': self.fundamental_analysis,
            'sector_position': self.sector_position,
            'company_highlights': self.company_highlights,
            'news_summary': self.news_summary,
            'market_sentiment': self.market_sentiment,
            'hot_topics': self.hot_topics,
            'analysis_summary': self.analysis_summary,
            'key_points': self.key_points,
            'risk_warning': self.risk_warning,
            'buy_reason': self.buy_reason,
            'market_snapshot': self.market_snapshot,
            'search_performed': self.search_performed,
            'success': self.success,
            'error_message': self.error_message,
            'current_price': self.current_price,
            'change_pct': self.change_pct,
            'model_used': self.model_used,
        }

    def get_core_conclusion(self) -> str:
        """獲取核心結論（一句話）"""
        if self.dashboard and 'core_conclusion' in self.dashboard:
            return self.dashboard['core_conclusion'].get('one_sentence', self.analysis_summary)
        return self.analysis_summary

    def get_position_advice(self, has_position: bool = False) -> str:
        """獲取持倉建議"""
        if self.dashboard and 'core_conclusion' in self.dashboard:
            pos_advice = self.dashboard['core_conclusion'].get('position_advice', {})
            if has_position:
                return pos_advice.get('has_position', self.operation_advice)
            return pos_advice.get('no_position', self.operation_advice)
        return self.operation_advice

    def get_sniper_points(self) -> Dict[str, str]:
        """獲取狙擊點位"""
        if self.dashboard and 'battle_plan' in self.dashboard:
            return self.dashboard['battle_plan'].get('sniper_points', {})
        return {}

    def get_checklist(self) -> List[str]:
        """獲取檢查清單"""
        if self.dashboard and 'battle_plan' in self.dashboard:
            return self.dashboard['battle_plan'].get('action_checklist', [])
        return []

    def get_risk_alerts(self) -> List[str]:
        """獲取風險警報"""
        if self.dashboard and 'intelligence' in self.dashboard:
            return self.dashboard['intelligence'].get('risk_alerts', [])
        return []

    def get_emoji(self) -> str:
        """根據操作建議返回對應 emoji"""
        emoji_map = {
            '買入': '🟢',
            '加倉': '🟢',
            '強烈買入': '💚',
            '持有': '🟡',
            '觀望': '⚪',
            '減倉': '🟠',
            '賣出': '🔴',
            '強烈賣出': '❌',
        }
        advice = self.operation_advice or ''
        # Direct match first
        if advice in emoji_map:
            return emoji_map[advice]
        # Handle compound advice like "賣出/觀望" — use the first part
        for part in advice.replace('/', '|').split('|'):
            part = part.strip()
            if part in emoji_map:
                return emoji_map[part]
        # Score-based fallback
        score = self.sentiment_score
        if score >= 80:
            return '💚'
        elif score >= 65:
            return '🟢'
        elif score >= 55:
            return '🟡'
        elif score >= 45:
            return '⚪'
        elif score >= 35:
            return '🟠'
        else:
            return '🔴'

    def get_confidence_stars(self) -> str:
        """返回置信度星級"""
        star_map = {'高': '⭐⭐⭐', '中': '⭐⭐', '低': '⭐'}
        return star_map.get(self.confidence_level, '⭐⭐')


class GeminiAnalyzer:
    """
    Gemini AI 分析器

    職責：
    1. 呼叫 Google Gemini API 進行股票分析
    2. 結合預先搜尋的新聞和技術面資料生成分析報告
    3. 解析 AI 返回的 JSON 格式結果

    使用方式：
        analyzer = GeminiAnalyzer()
        result = analyzer.analyze(context, news_context)
    """

    # ========================================
    # 系統提示詞 - 決策儀表盤 v2.0
    # ========================================
    # 輸出格式升級：從簡單訊號升級為決策儀表盤
    # 核心模組：核心結論 + 資料透視 + 輿情情報 + 作戰計劃
    # ========================================

    SYSTEM_PROMPT = """你是一位專注於趨勢交易的 A 股投資分析師，負責生成專業的【決策儀表盤】分析報告。

## 核心交易理念（必須嚴格遵守）

### 1. 嚴進策略（不追高）
- **絕對不追高**：當股價偏離 MA5 超過 5% 時，堅決不買入
- **乖離率公式**：(現價 - MA5) / MA5 × 100%
- 乖離率 < 2%：最佳買點區間
- 乖離率 2-5%：可小倉介入
- 乖離率 > 5%：嚴禁追高！直接判定為"觀望"

### 2. 趨勢交易（順勢而為）
- **多頭排列必須條件**：MA5 > MA10 > MA20
- 只做多頭排列的股票，空頭排列堅決不碰
- 均線發散上行優於均線粘合
- 趨勢強度判斷：看均線間距是否在擴大

### 3. 效率優先（籌碼結構）
- 關注籌碼集中度：90%集中度 < 15% 表示籌碼集中
- 獲利比例分析：70-90% 獲利盤時需警惕獲利回吐
- 平均成本與現價關係：現價高於平均成本 5-15% 為健康

### 4. 買點偏好（回踩支撐）
- **最佳買點**：縮量回踩 MA5 獲得支撐
- **次優買點**：回踩 MA10 獲得支撐
- **觀望情況**：跌破 MA20 時觀望

### 5. 風險排查重點
- 減持公告（股東、高管減持）
- 業績預虧/大幅下滑
- 監管處罰/立案調查
- 行業政策利空
- 大額解禁

### 6. 估值關注（PE/PB）
- 分析時請關注市盈率（PE）是否合理
- PE 明顯偏高時（如遠超行業平均或歷史均值），需在風險點中說明
- 高成長股可適當容忍較高 PE，但需有業績支撐

### 7. 強勢趨勢股放寬
- 強勢趨勢股（多頭排列且趨勢強度高、量能配合）可適當放寬乖離率要求
- 此類股票可輕倉追蹤，但仍需設定止損，不盲目追高

## 輸出格式：決策儀表盤 JSON

請嚴格按照以下 JSON 格式輸出，這是一個完整的【決策儀表盤】：

```json
{
    "stock_name": "股票中文名稱",
    "sentiment_score": 0-100整數,
    "trend_prediction": "強烈看多/看多/震盪/看空/強烈看空",
    "operation_advice": "買入/加倉/持有/減倉/賣出/觀望",
    "decision_type": "buy/hold/sell",
    "confidence_level": "高/中/低",

    "dashboard": {
        "core_conclusion": {
            "one_sentence": "一句話核心結論（30字以內，直接告訴使用者做什麼）",
            "signal_type": "🟢買入訊號/🟡持有觀望/🔴賣出訊號/⚠️風險警告",
            "time_sensitivity": "立即行動/今日內/本週內/不急",
            "position_advice": {
                "no_position": "空倉者建議：具體操作指引",
                "has_position": "持倉者建議：具體操作指引"
            }
        },

        "data_perspective": {
            "trend_status": {
                "ma_alignment": "均線排列狀態描述",
                "is_bullish": true/false,
                "trend_score": 0-100
            },
            "price_position": {
                "current_price": 當前價格數值,
                "ma5": MA5數值,
                "ma10": MA10數值,
                "ma20": MA20數值,
                "bias_ma5": 乖離率百分比數值,
                "bias_status": "安全/警戒/危險",
                "support_level": 支撐位價格,
                "resistance_level": 壓力位價格
            },
            "volume_analysis": {
                "volume_ratio": 量比數值,
                "volume_status": "放量/縮量/平量",
                "turnover_rate": 換手率百分比,
                "volume_meaning": "量能含義解讀（如：縮量回撥錶示拋壓減輕）"
            },
            "chip_structure": {
                "profit_ratio": 獲利比例,
                "avg_cost": 平均成本,
                "concentration": 籌碼集中度,
                "chip_health": "健康/一般/警惕"
            }
        },

        "intelligence": {
            "latest_news": "【最新訊息】近期重要新聞摘要",
            "risk_alerts": ["風險點1：具體描述", "風險點2：具體描述"],
            "positive_catalysts": ["利好1：具體描述", "利好2：具體描述"],
            "earnings_outlook": "業績預期分析（基於年報預告、業績快報等）",
            "sentiment_summary": "輿情情緒一句話總結"
        },

        "battle_plan": {
            "sniper_points": {
                "ideal_buy": "理想買入點：XX元（在MA5附近）",
                "secondary_buy": "次優買入點：XX元（在MA10附近）",
                "stop_loss": "止損位：XX元（跌破MA20或X%）",
                "take_profit": "目標位：XX元（前高/整數關口）"
            },
            "position_strategy": {
                "suggested_position": "建議倉位：X成",
                "entry_plan": "分批建倉策略描述",
                "risk_control": "風控策略描述"
            },
            "action_checklist": [
                "✅/⚠️/❌ 檢查項1：多頭排列",
                "✅/⚠️/❌ 檢查項2：乖離率合理（強勢趨勢可放寬）",
                "✅/⚠️/❌ 檢查項3：量能配合",
                "✅/⚠️/❌ 檢查項4：無重大利空",
                "✅/⚠️/❌ 檢查項5：籌碼健康",
                "✅/⚠️/❌ 檢查項6：PE估值合理"
            ]
        }
    },

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
    "hot_topics": "相關熱點",

    "search_performed": true/false,
    "data_sources": "資料來源說明"
}
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
5. **風險優先順序**：輿情中的風險點要醒目標出"""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize LLM Analyzer via LiteLLM.

        Args:
            api_key: Ignored (kept for backward compatibility). Keys are loaded from config.
        """
        self._router = None
        self._litellm_available = False
        self._init_litellm()
        if not self._litellm_available:
            logger.warning("No LLM configured (LITELLM_MODEL / API keys), AI analysis will be unavailable")

    def _has_channel_config(self, config: Config) -> bool:
        """Check if multi-channel config (channels / YAML / legacy model_list) is active."""
        return bool(config.llm_model_list) and not all(
            e.get('model_name', '').startswith('__legacy_') for e in config.llm_model_list
        )

    def _init_litellm(self) -> None:
        """Initialize litellm Router from channels / YAML / legacy keys."""
        config = get_config()
        litellm_model = config.litellm_model
        if not litellm_model:
            logger.warning("Analyzer LLM: LITELLM_MODEL not configured")
            return

        self._litellm_available = True

        # --- Channel / YAML path: build Router from pre-built model_list ---
        if self._has_channel_config(config):
            model_list = config.llm_model_list
            self._router = Router(
                model_list=model_list,
                routing_strategy="simple-shuffle",
                num_retries=2,
            )
            unique_models = list(dict.fromkeys(
                e['litellm_params']['model'] for e in model_list
            ))
            logger.info(
                f"Analyzer LLM: Router initialized from channels/YAML — "
                f"{len(model_list)} deployment(s), models: {unique_models}"
            )
            return

        # --- Legacy path: build Router for multi-key, or use single key ---
        keys = get_api_keys_for_model(litellm_model, config)

        if len(keys) > 1:
            # Build legacy Router for primary model multi-key load-balancing
            extra_params = extra_litellm_params(litellm_model, config)
            legacy_model_list = [
                {
                    "model_name": litellm_model,
                    "litellm_params": {
                        "model": litellm_model,
                        "api_key": k,
                        **extra_params,
                    },
                }
                for k in keys
            ]
            self._router = Router(
                model_list=legacy_model_list,
                routing_strategy="simple-shuffle",
                num_retries=2,
            )
            logger.info(
                f"Analyzer LLM: Legacy Router initialized with {len(keys)} keys "
                f"for {litellm_model}"
            )
        elif keys:
            logger.info(f"Analyzer LLM: litellm initialized (model={litellm_model})")
        else:
            logger.info(
                f"Analyzer LLM: litellm initialized (model={litellm_model}, "
                f"API key from environment)"
            )

    def is_available(self) -> bool:
        """Check if LiteLLM is properly configured with at least one API key."""
        return self._router is not None or self._litellm_available

    def _call_litellm(self, prompt: str, generation_config: dict) -> Tuple[str, str, Dict[str, Any]]:
        """Call LLM via litellm with fallback across configured models.

        When channels/YAML are configured, every model goes through the Router
        (which handles per-model key selection, load balancing, and retries).
        In legacy mode, the primary model may use the Router while fallback
        models fall back to direct litellm.completion().

        Args:
            prompt: User prompt text.
            generation_config: Dict with optional keys: temperature, max_output_tokens, max_tokens.

        Returns:
            Tuple of (response text, model_used, usage). On success model_used is the full model
            name and usage is a dict with prompt_tokens, completion_tokens, total_tokens.
        """
        config = get_config()
        max_tokens = (
            generation_config.get('max_output_tokens')
            or generation_config.get('max_tokens')
            or 8192
        )
        temperature = generation_config.get('temperature', 0.7)

        models_to_try = [config.litellm_model] + (config.litellm_fallback_models or [])
        models_to_try = [m for m in models_to_try if m]

        use_channel_router = self._has_channel_config(config)

        last_error = None
        for model in models_to_try:
            try:
                model_short = model.split("/")[-1] if "/" in model else model
                call_kwargs: Dict[str, Any] = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                extra = get_thinking_extra_body(model_short)
                if extra:
                    call_kwargs["extra_body"] = extra

                _router_model_names = set(get_configured_llm_models(config.llm_model_list))
                if use_channel_router and self._router and model in _router_model_names:
                    # Channel / YAML path: Router manages key + base_url per model
                    response = self._router.completion(**call_kwargs)
                elif self._router and model == config.litellm_model and not use_channel_router:
                    # Legacy path: Router only for primary model multi-key
                    response = self._router.completion(**call_kwargs)
                else:
                    # Legacy/direct-env path: direct call (also handles direct-env
                    # providers like groq/ or bedrock/ that are not in the Router
                    # model_list even when channel mode is active)
                    keys = get_api_keys_for_model(model, config)
                    if keys:
                        call_kwargs["api_key"] = keys[0]
                    call_kwargs.update(extra_litellm_params(model, config))
                    response = litellm.completion(**call_kwargs)

                if response and response.choices and response.choices[0].message.content:
                    usage: Dict[str, Any] = {}
                    if response.usage:
                        usage = {
                            "prompt_tokens": response.usage.prompt_tokens or 0,
                            "completion_tokens": response.usage.completion_tokens or 0,
                            "total_tokens": response.usage.total_tokens or 0,
                        }
                    return (response.choices[0].message.content, model, usage)
                raise ValueError("LLM returned empty response")

            except Exception as e:
                logger.warning(f"[LiteLLM] {model} failed: {e}")
                last_error = e
                continue

        raise Exception(f"All LLM models failed (tried {len(models_to_try)} model(s)). Last error: {last_error}")

    def generate_text(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> Optional[str]:
        """Public entry point for free-form text generation.

        External callers (e.g. MarketAnalyzer) must use this method instead of
        calling _call_litellm() directly or accessing private attributes such as
        _litellm_available, _router, _model, _use_openai, or _use_anthropic.

        Args:
            prompt:      Text prompt to send to the LLM.
            max_tokens:  Maximum tokens in the response (default 2048).
            temperature: Sampling temperature (default 0.7).

        Returns:
            Response text, or None if the LLM call fails (error is logged).
        """
        try:
            result = self._call_litellm(
                prompt,
                generation_config={"max_tokens": max_tokens, "temperature": temperature},
            )
            if isinstance(result, tuple):
                text, model_used, usage = result
                persist_llm_usage(usage, model_used, call_type="market_review")
                return text
            return result
        except Exception as exc:
            logger.error("[generate_text] LLM call failed: %s", exc)
            return None

    def analyze(
        self, 
        context: Dict[str, Any],
        news_context: Optional[str] = None
    ) -> AnalysisResult:
        """
        分析單隻股票
        
        流程：
        1. 格式化輸入資料（技術面 + 新聞）
        2. 呼叫 Gemini API（帶重試和模型切換）
        3. 解析 JSON 響應
        4. 返回結構化結果
        
        Args:
            context: 從 storage.get_analysis_context() 獲取的上下文資料
            news_context: 預先搜尋的新聞內容（可選）
            
        Returns:
            AnalysisResult 物件
        """
        code = context.get('code', 'Unknown')
        config = get_config()
        
        # 請求前增加延時（防止連續請求觸發限流）
        request_delay = config.gemini_request_delay
        if request_delay > 0:
            logger.debug(f"[LLM] 請求前等待 {request_delay:.1f} 秒...")
            time.sleep(request_delay)
        
        # 優先從上下文獲取股票名稱（由 main.py 傳入）
        name = context.get('stock_name')
        if not name or name.startswith('股票'):
            # 備選：從 realtime 中獲取
            if 'realtime' in context and context['realtime'].get('name'):
                name = context['realtime']['name']
            else:
                # 最後從對映表獲取
                name = STOCK_NAME_MAP.get(code, f'股票{code}')
        
        # 如果模型不可用，返回預設結果
        if not self.is_available():
            return AnalysisResult(
                code=code,
                name=name,
                sentiment_score=50,
                trend_prediction='震盪',
                operation_advice='持有',
                confidence_level='低',
                analysis_summary='AI 分析功能未啟用（未配置 API Key）',
                risk_warning='請配置 LLM API Key（GEMINI_API_KEY/ANTHROPIC_API_KEY/OPENAI_API_KEY）後重試',
                success=False,
                error_message='LLM API Key 未配置',
                model_used=None,
            )
        
        try:
            # 格式化輸入（包含技術面資料和新聞）
            prompt = self._format_prompt(context, name, news_context)
            
            config = get_config()
            model_name = config.litellm_model or "unknown"
            logger.info(f"========== AI 分析 {name}({code}) ==========")
            logger.info(f"[LLM配置] 模型: {model_name}")
            logger.info(f"[LLM配置] Prompt 長度: {len(prompt)} 字元")
            logger.info(f"[LLM配置] 是否包含新聞: {'是' if news_context else '否'}")

            # 記錄完整 prompt 到日誌（INFO級別記錄摘要，DEBUG記錄完整）
            prompt_preview = prompt[:500] + "..." if len(prompt) > 500 else prompt
            logger.info(f"[LLM Prompt 預覽]\n{prompt_preview}")
            logger.debug(f"=== 完整 Prompt ({len(prompt)}字元) ===\n{prompt}\n=== End Prompt ===")

            # 設定生成配置
            generation_config = {
                "temperature": config.llm_temperature,
                "max_output_tokens": 8192,
            }

            logger.info(f"[LLM呼叫] 開始呼叫 {model_name}...")

            # 使用 litellm 呼叫（支援完整性校驗重試）
            current_prompt = prompt
            retry_count = 0
            max_retries = config.report_integrity_retry if config.report_integrity_enabled else 0

            while True:
                start_time = time.time()
                response_text, model_used, llm_usage = self._call_litellm(current_prompt, generation_config)
                elapsed = time.time() - start_time

                # 記錄響應資訊
                logger.info(
                    f"[LLM返回] {model_name} 響應成功, 耗時 {elapsed:.2f}s, 響應長度 {len(response_text)} 字元"
                )
                response_preview = response_text[:300] + "..." if len(response_text) > 300 else response_text
                logger.info(f"[LLM返回 預覽]\n{response_preview}")
                logger.debug(
                    f"=== {model_name} 完整響應 ({len(response_text)}字元) ===\n{response_text}\n=== End Response ==="
                )

                # 解析響應
                result = self._parse_response(response_text, code, name)
                result.raw_response = response_text
                result.search_performed = bool(news_context)
                result.market_snapshot = self._build_market_snapshot(context)
                result.model_used = model_used

                # 內容完整性校驗（可選）
                if not config.report_integrity_enabled:
                    break
                pass_integrity, missing_fields = self._check_content_integrity(result)
                if pass_integrity:
                    break
                if retry_count < max_retries:
                    current_prompt = self._build_integrity_retry_prompt(
                        prompt,
                        response_text,
                        missing_fields,
                    )
                    retry_count += 1
                    logger.info(
                        "[LLM完整性] 必填欄位缺失 %s，第 %d 次補全重試",
                        missing_fields,
                        retry_count,
                    )
                else:
                    self._apply_placeholder_fill(result, missing_fields)
                    logger.warning(
                        "[LLM完整性] 必填欄位缺失 %s，已佔位補全，不阻塞流程",
                        missing_fields,
                    )
                    break

            persist_llm_usage(llm_usage, model_used, call_type="analysis", stock_code=code)

            logger.info(f"[LLM解析] {name}({code}) 分析完成: {result.trend_prediction}, 評分 {result.sentiment_score}")

            return result
            
        except Exception as e:
            logger.error(f"AI 分析 {name}({code}) 失敗: {e}")
            return AnalysisResult(
                code=code,
                name=name,
                sentiment_score=50,
                trend_prediction='震盪',
                operation_advice='持有',
                confidence_level='低',
                analysis_summary=f'分析過程出錯: {str(e)[:100]}',
                risk_warning='分析失敗，請稍後重試或手動分析',
                success=False,
                error_message=str(e),
                model_used=None,
            )
    
    def _format_prompt(
        self, 
        context: Dict[str, Any], 
        name: str,
        news_context: Optional[str] = None
    ) -> str:
        """
        格式化分析提示詞（決策儀表盤 v2.0）
        
        包含：技術指標、實時行情（量比/換手率）、籌碼分佈、趨勢分析、新聞
        
        Args:
            context: 技術面資料上下文（包含增強資料）
            name: 股票名稱（預設值，可能被上下文覆蓋）
            news_context: 預先搜尋的新聞內容
        """
        code = context.get('code', 'Unknown')
        
        # 優先使用上下文中的股票名稱（從 realtime_quote 獲取）
        stock_name = context.get('stock_name', name)
        if not stock_name or stock_name == f'股票{code}':
            stock_name = STOCK_NAME_MAP.get(code, f'股票{code}')
            
        today = context.get('today', {})
        
        # ========== 構建決策儀表盤格式的輸入 ==========
        prompt = f"""# 決策儀表盤分析請求

## 📊 股票基礎資訊
| 專案 | 資料 |
|------|------|
| 股票程式碼 | **{code}** |
| 股票名稱 | **{stock_name}** |
| 分析日期 | {context.get('date', '未知')} |

---

## 📈 技術面資料

### 今日行情
| 指標 | 數值 |
|------|------|
| 收盤價 | {today.get('close', 'N/A')} 元 |
| 開盤價 | {today.get('open', 'N/A')} 元 |
| 最高價 | {today.get('high', 'N/A')} 元 |
| 最低價 | {today.get('low', 'N/A')} 元 |
| 漲跌幅 | {today.get('pct_chg', 'N/A')}% |
| 成交量 | {self._format_volume(today.get('volume'))} |
| 成交額 | {self._format_amount(today.get('amount'))} |

### 均線系統（關鍵判斷指標）
| 均線 | 數值 | 說明 |
|------|------|------|
| MA5 | {today.get('ma5', 'N/A')} | 短期趨勢線 |
| MA10 | {today.get('ma10', 'N/A')} | 中短期趨勢線 |
| MA20 | {today.get('ma20', 'N/A')} | 中期趨勢線 |
| 均線形態 | {context.get('ma_status', '未知')} | 多頭/空頭/纏繞 |
"""
        
        # 新增實時行情資料（量比、換手率等）
        if 'realtime' in context:
            rt = context['realtime']
            prompt += f"""
### 實時行情增強資料
| 指標 | 數值 | 解讀 |
|------|------|------|
| 當前價格 | {rt.get('price', 'N/A')} 元 | |
| **量比** | **{rt.get('volume_ratio', 'N/A')}** | {rt.get('volume_ratio_desc', '')} |
| **換手率** | **{rt.get('turnover_rate', 'N/A')}%** | |
| 市盈率(動態) | {rt.get('pe_ratio', 'N/A')} | |
| 市淨率 | {rt.get('pb_ratio', 'N/A')} | |
| 總市值 | {self._format_amount(rt.get('total_mv'))} | |
| 流通市值 | {self._format_amount(rt.get('circ_mv'))} | |
| 60日漲跌幅 | {rt.get('change_60d', 'N/A')}% | 中期表現 |
"""

        # 新增財報與分紅（價值投資口徑）
        fundamental_context = context.get("fundamental_context") if isinstance(context, dict) else None
        earnings_block = (
            fundamental_context.get("earnings", {})
            if isinstance(fundamental_context, dict)
            else {}
        )
        earnings_data = (
            earnings_block.get("data", {})
            if isinstance(earnings_block, dict)
            else {}
        )
        financial_report = (
            earnings_data.get("financial_report", {})
            if isinstance(earnings_data, dict)
            else {}
        )
        dividend_metrics = (
            earnings_data.get("dividend", {})
            if isinstance(earnings_data, dict)
            else {}
        )
        if isinstance(financial_report, dict) or isinstance(dividend_metrics, dict):
            financial_report = financial_report if isinstance(financial_report, dict) else {}
            dividend_metrics = dividend_metrics if isinstance(dividend_metrics, dict) else {}
            ttm_yield = dividend_metrics.get("ttm_dividend_yield_pct", "N/A")
            ttm_cash = dividend_metrics.get("ttm_cash_dividend_per_share", "N/A")
            ttm_count = dividend_metrics.get("ttm_event_count", "N/A")
            report_date = financial_report.get("report_date", "N/A")
            prompt += f"""
### 財報與分紅（價值投資口徑）
| 指標 | 數值 | 說明 |
|------|------|------|
| 最近報告期 | {report_date} | 來自結構化財報欄位 |
| 營業收入 | {financial_report.get('revenue', 'N/A')} | |
| 歸母淨利潤 | {financial_report.get('net_profit_parent', 'N/A')} | |
| 經營現金流 | {financial_report.get('operating_cash_flow', 'N/A')} | |
| ROE | {financial_report.get('roe', 'N/A')} | |
| 近12個月每股現金分紅 | {ttm_cash} | 僅現金分紅、稅前口徑 |
| TTM 股息率 | {ttm_yield} | 公式：近12個月每股現金分紅 / 當前價格 × 100% |
| TTM 分紅事件數 | {ttm_count} | |

> 若上述欄位為 N/A 或缺失，請明確寫“資料缺失，無法判斷”，禁止編造。
"""

        # 新增籌碼分佈資料
        if 'chip' in context:
            chip = context['chip']
            profit_ratio = chip.get('profit_ratio', 0)
            prompt += f"""
### 籌碼分佈資料（效率指標）
| 指標 | 數值 | 健康標準 |
|------|------|----------|
| **獲利比例** | **{profit_ratio:.1%}** | 70-90%時警惕 |
| 平均成本 | {chip.get('avg_cost', 'N/A')} 元 | 現價應高於5-15% |
| 90%籌碼集中度 | {chip.get('concentration_90', 0):.2%} | <15%為集中 |
| 70%籌碼集中度 | {chip.get('concentration_70', 0):.2%} | |
| 籌碼狀態 | {chip.get('chip_status', '未知')} | |
"""
        
        # 新增趨勢分析結果（基於交易理念的預判）
        if 'trend_analysis' in context:
            trend = context['trend_analysis']
            bias_warning = "🚨 超過5%，嚴禁追高！" if trend.get('bias_ma5', 0) > 5 else "✅ 安全範圍"
            prompt += f"""
### 趨勢分析預判（基於交易理念）
| 指標 | 數值 | 判定 |
|------|------|------|
| 趨勢狀態 | {trend.get('trend_status', '未知')} | |
| 均線排列 | {trend.get('ma_alignment', '未知')} | MA5>MA10>MA20為多頭 |
| 趨勢強度 | {trend.get('trend_strength', 0)}/100 | |
| **乖離率(MA5)** | **{trend.get('bias_ma5', 0):+.2f}%** | {bias_warning} |
| 乖離率(MA10) | {trend.get('bias_ma10', 0):+.2f}% | |
| 量能狀態 | {trend.get('volume_status', '未知')} | {trend.get('volume_trend', '')} |
| 系統訊號 | {trend.get('buy_signal', '未知')} | |
| 系統評分 | {trend.get('signal_score', 0)}/100 | |

#### 系統分析理由
**買入理由**：
{chr(10).join('- ' + r for r in trend.get('signal_reasons', ['無'])) if trend.get('signal_reasons') else '- 無'}

**風險因素**：
{chr(10).join('- ' + r for r in trend.get('risk_factors', ['無'])) if trend.get('risk_factors') else '- 無'}
"""
        
        # 新增昨日對比資料
        if 'yesterday' in context:
            volume_change = context.get('volume_change_ratio', 'N/A')
            prompt += f"""
### 量價變化
- 成交量較昨日變化：{volume_change}倍
- 價格較昨日變化：{context.get('price_change_ratio', 'N/A')}%
"""
        
        # 新增新聞搜尋結果（重點區域）
        news_window_days: Optional[int] = None
        context_window = context.get("news_window_days")
        try:
            if context_window is not None:
                parsed_window = int(context_window)
                if parsed_window > 0:
                    news_window_days = parsed_window
        except (TypeError, ValueError):
            news_window_days = None

        if news_window_days is None:
            prompt_config = get_config()
            news_window_days = resolve_news_window_days(
                news_max_age_days=getattr(prompt_config, "news_max_age_days", 3),
                news_strategy_profile=getattr(prompt_config, "news_strategy_profile", "short"),
            )
        prompt += """
---

## 📰 輿情情報
"""
        if news_context:
            prompt += f"""
以下是 **{stock_name}({code})** 近{news_window_days}日的新聞搜尋結果，請重點提取：
1. 🚨 **風險警報**：減持、處罰、利空
2. 🎯 **利好催化**：業績、合同、政策
3. 📊 **業績預期**：年報預告、業績快報
4. 🕒 **時間規則（強制）**：
   - 輸出到 `risk_alerts` / `positive_catalysts` / `latest_news` 的每一條都必須帶具體日期（YYYY-MM-DD）
   - 超出近{news_window_days}日視窗的新聞一律忽略
   - 時間未知、無法確定釋出日期的新聞一律忽略

```
{news_context}
```
"""
        else:
            prompt += """
未搜尋到該股票近期的相關新聞。請主要依據技術面資料進行分析。
"""

        # 注入缺失資料警告
        if context.get('data_missing'):
            prompt += """
⚠️ **資料缺失警告**
由於介面限制，當前無法獲取完整的實時行情和技術指標資料。
請 **忽略上述表格中的 N/A 資料**，重點依據 **【📰 輿情情報】** 中的新聞進行基本面和情緒面分析。
在回答技術面問題（如均線、乖離率）時，請直接說明“資料缺失，無法判斷”，**嚴禁編造資料**。
"""

        # 明確的輸出要求
        prompt += f"""
---

## ✅ 分析任務

請為 **{stock_name}({code})** 生成【決策儀表盤】，嚴格按照 JSON 格式輸出。
"""
        if context.get('is_index_etf'):
            prompt += """
> ⚠️ **指數/ETF 分析約束**：該標的為指數跟蹤型 ETF 或市場指數。
> - 風險分析僅關注：**指數走勢、跟蹤誤差、市場流動性**
> - 嚴禁將基金公司的訴訟、聲譽、高管變動納入風險警報
> - 業績預期基於**指數成分股整體表現**，而非基金公司財報
> - `risk_alerts` 中不得出現基金管理人相關的公司經營風險

"""
        prompt += f"""
### ⚠️ 重要：輸出正確的股票名稱格式
正確的股票名稱格式為“股票名稱（股票程式碼）”，例如“貴州茅臺（600519）”。
如果上方顯示的股票名稱為"股票{code}"或不正確，請在分析開頭**明確輸出該股票的正確中文全稱**。

### 重點關注（必須明確回答）：
1. ❓ 是否滿足 MA5>MA10>MA20 多頭排列？
2. ❓ 當前乖離率是否在安全範圍內（<5%）？—— 超過5%必須標註"嚴禁追高"
3. ❓ 量能是否配合（縮量回撥/放量突破）？
4. ❓ 籌碼結構是否健康？
5. ❓ 訊息面有無重大利空？（減持、處罰、業績變臉等）

### 決策儀表盤要求：
- **股票名稱**：必須輸出正確的中文全稱（如"貴州茅臺"而非"股票600519"）
- **核心結論**：一句話說清該買/該賣/該等
- **持倉分類建議**：空倉者怎麼做 vs 持倉者怎麼做
- **具體狙擊點位**：買入價、止損價、目標價（精確到分）
- **檢查清單**：每項用 ✅/⚠️/❌ 標記
- **訊息面時間合規**：`latest_news`、`risk_alerts`、`positive_catalysts` 不得包含超出近{news_window_days}日或時間未知的資訊

請輸出完整的 JSON 格式決策儀表盤。"""
        
        return prompt
    
    def _format_volume(self, volume: Optional[float]) -> str:
        """格式化成交量顯示"""
        if volume is None:
            return 'N/A'
        if volume >= 1e8:
            return f"{volume / 1e8:.2f} 億股"
        elif volume >= 1e4:
            return f"{volume / 1e4:.2f} 萬股"
        else:
            return f"{volume:.0f} 股"
    
    def _format_amount(self, amount: Optional[float]) -> str:
        """格式化成交額顯示"""
        if amount is None:
            return 'N/A'
        if amount >= 1e8:
            return f"{amount / 1e8:.2f} 億元"
        elif amount >= 1e4:
            return f"{amount / 1e4:.2f} 萬元"
        else:
            return f"{amount:.0f} 元"

    def _format_percent(self, value: Optional[float]) -> str:
        """格式化百分比顯示"""
        if value is None:
            return 'N/A'
        try:
            return f"{float(value):.2f}%"
        except (TypeError, ValueError):
            return 'N/A'

    def _format_price(self, value: Optional[float]) -> str:
        """格式化價格顯示"""
        if value is None:
            return 'N/A'
        try:
            return f"{float(value):.2f}"
        except (TypeError, ValueError):
            return 'N/A'

    def _build_market_snapshot(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """構建當日行情快照（展示用）"""
        today = context.get('today', {}) or {}
        realtime = context.get('realtime', {}) or {}
        yesterday = context.get('yesterday', {}) or {}

        prev_close = yesterday.get('close')
        close = today.get('close')
        high = today.get('high')
        low = today.get('low')

        amplitude = None
        change_amount = None
        if prev_close not in (None, 0) and high is not None and low is not None:
            try:
                amplitude = (float(high) - float(low)) / float(prev_close) * 100
            except (TypeError, ValueError, ZeroDivisionError):
                amplitude = None
        if prev_close is not None and close is not None:
            try:
                change_amount = float(close) - float(prev_close)
            except (TypeError, ValueError):
                change_amount = None

        snapshot = {
            "date": context.get('date', '未知'),
            "close": self._format_price(close),
            "open": self._format_price(today.get('open')),
            "high": self._format_price(high),
            "low": self._format_price(low),
            "prev_close": self._format_price(prev_close),
            "pct_chg": self._format_percent(today.get('pct_chg')),
            "change_amount": self._format_price(change_amount),
            "amplitude": self._format_percent(amplitude),
            "volume": self._format_volume(today.get('volume')),
            "amount": self._format_amount(today.get('amount')),
        }

        if realtime:
            snapshot.update({
                "price": self._format_price(realtime.get('price')),
                "volume_ratio": realtime.get('volume_ratio', 'N/A'),
                "turnover_rate": self._format_percent(realtime.get('turnover_rate')),
                "source": getattr(realtime.get('source'), 'value', realtime.get('source', 'N/A')),
            })

        return snapshot

    def _check_content_integrity(self, result: AnalysisResult) -> Tuple[bool, List[str]]:
        """Delegate to module-level check_content_integrity."""
        return check_content_integrity(result)

    def _build_integrity_complement_prompt(self, missing_fields: List[str]) -> str:
        """Build complement instruction for missing mandatory fields."""
        lines = ["### 補全要求：請在上方分析基礎上補充以下必填內容，並輸出完整 JSON："]
        for f in missing_fields:
            if f == "sentiment_score":
                lines.append("- sentiment_score: 0-100 綜合評分")
            elif f == "operation_advice":
                lines.append("- operation_advice: 買入/加倉/持有/減倉/賣出/觀望")
            elif f == "analysis_summary":
                lines.append("- analysis_summary: 綜合分析摘要")
            elif f == "dashboard.core_conclusion.one_sentence":
                lines.append("- dashboard.core_conclusion.one_sentence: 一句話決策")
            elif f == "dashboard.intelligence.risk_alerts":
                lines.append("- dashboard.intelligence.risk_alerts: 風險警報列表（可為空陣列）")
            elif f == "dashboard.battle_plan.sniper_points.stop_loss":
                lines.append("- dashboard.battle_plan.sniper_points.stop_loss: 止損價")
        return "\n".join(lines)

    def _build_integrity_retry_prompt(
        self,
        base_prompt: str,
        previous_response: str,
        missing_fields: List[str],
    ) -> str:
        """Build retry prompt using the previous response as the complement baseline."""
        complement = self._build_integrity_complement_prompt(missing_fields)
        previous_output = previous_response.strip()
        return "\n\n".join([
            base_prompt,
            "### 上一次輸出如下，請在該輸出基礎上補齊缺失欄位，並重新輸出完整 JSON。不要省略已有欄位：",
            previous_output,
            complement,
        ])

    def _apply_placeholder_fill(self, result: AnalysisResult, missing_fields: List[str]) -> None:
        """Delegate to module-level apply_placeholder_fill."""
        apply_placeholder_fill(result, missing_fields)

    def _parse_response(
        self, 
        response_text: str, 
        code: str, 
        name: str
    ) -> AnalysisResult:
        """
        解析 Gemini 響應（決策儀表盤版）
        
        嘗試從響應中提取 JSON 格式的分析結果，包含 dashboard 欄位
        如果解析失敗，嘗試智慧提取或返回預設結果
        """
        try:
            # 清理響應文字：移除 markdown 程式碼塊標記
            cleaned_text = response_text
            if '```json' in cleaned_text:
                cleaned_text = cleaned_text.replace('```json', '').replace('```', '')
            elif '```' in cleaned_text:
                cleaned_text = cleaned_text.replace('```', '')
            
            # 嘗試找到 JSON 內容
            json_start = cleaned_text.find('{')
            json_end = cleaned_text.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = cleaned_text[json_start:json_end]
                
                # 嘗試修復常見的 JSON 問題
                json_str = self._fix_json_string(json_str)
                
                data = json.loads(json_str)

                # Schema validation (lenient: on failure, continue with raw dict)
                try:
                    AnalysisReportSchema.model_validate(data)
                except Exception as e:
                    logger.warning(
                        "LLM report schema validation failed, continuing with raw dict: %s",
                        str(e)[:100],
                    )

                # 提取 dashboard 資料
                dashboard = data.get('dashboard', None)

                # 優先使用 AI 返回的股票名稱（如果原名稱無效或包含程式碼）
                ai_stock_name = data.get('stock_name')
                if ai_stock_name and (name.startswith('股票') or name == code or 'Unknown' in name):
                    name = ai_stock_name

                # 解析所有欄位，使用預設值防止缺失
                # 解析 decision_type，如果沒有則根據 operation_advice 推斷
                decision_type = data.get('decision_type', '')
                if not decision_type:
                    op = data.get('operation_advice', '持有')
                    if op in ['買入', '加倉', '強烈買入']:
                        decision_type = 'buy'
                    elif op in ['賣出', '減倉', '強烈賣出']:
                        decision_type = 'sell'
                    else:
                        decision_type = 'hold'
                
                return AnalysisResult(
                    code=code,
                    name=name,
                    # 核心指標
                    sentiment_score=int(data.get('sentiment_score', 50)),
                    trend_prediction=data.get('trend_prediction', '震盪'),
                    operation_advice=data.get('operation_advice', '持有'),
                    decision_type=decision_type,
                    confidence_level=data.get('confidence_level', '中'),
                    # 決策儀表盤
                    dashboard=dashboard,
                    # 走勢分析
                    trend_analysis=data.get('trend_analysis', ''),
                    short_term_outlook=data.get('short_term_outlook', ''),
                    medium_term_outlook=data.get('medium_term_outlook', ''),
                    # 技術面
                    technical_analysis=data.get('technical_analysis', ''),
                    ma_analysis=data.get('ma_analysis', ''),
                    volume_analysis=data.get('volume_analysis', ''),
                    pattern_analysis=data.get('pattern_analysis', ''),
                    # 基本面
                    fundamental_analysis=data.get('fundamental_analysis', ''),
                    sector_position=data.get('sector_position', ''),
                    company_highlights=data.get('company_highlights', ''),
                    # 情緒面/訊息面
                    news_summary=data.get('news_summary', ''),
                    market_sentiment=data.get('market_sentiment', ''),
                    hot_topics=data.get('hot_topics', ''),
                    # 綜合
                    analysis_summary=data.get('analysis_summary', '分析完成'),
                    key_points=data.get('key_points', ''),
                    risk_warning=data.get('risk_warning', ''),
                    buy_reason=data.get('buy_reason', ''),
                    # 後設資料
                    search_performed=data.get('search_performed', False),
                    data_sources=data.get('data_sources', '技術面資料'),
                    success=True,
                )
            else:
                # 沒有找到 JSON，嘗試從純文字中提取資訊
                logger.warning(f"無法從響應中提取 JSON，使用原始文字分析")
                return self._parse_text_response(response_text, code, name)
                
        except json.JSONDecodeError as e:
            logger.warning(f"JSON 解析失敗: {e}，嘗試從文字提取")
            return self._parse_text_response(response_text, code, name)
    
    def _fix_json_string(self, json_str: str) -> str:
        """修復常見的 JSON 格式問題"""
        import re
        
        # 移除註釋
        json_str = re.sub(r'//.*?\n', '\n', json_str)
        json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)
        
        # 修復尾隨逗號
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)
        
        # 確保布林值是小寫
        json_str = json_str.replace('True', 'true').replace('False', 'false')
        
        # fix by json-repair
        json_str = repair_json(json_str)
        
        return json_str
    
    def _parse_text_response(
        self, 
        response_text: str, 
        code: str, 
        name: str
    ) -> AnalysisResult:
        """從純文字響應中儘可能提取分析資訊"""
        # 嘗試識別關鍵詞來判斷情緒
        sentiment_score = 50
        trend = '震盪'
        advice = '持有'
        
        text_lower = response_text.lower()
        
        # 簡單的情緒識別
        positive_keywords = ['看多', '買入', '上漲', '突破', '強勢', '利好', '加倉', 'bullish', 'buy']
        negative_keywords = ['看空', '賣出', '下跌', '跌破', '弱勢', '利空', '減倉', 'bearish', 'sell']
        
        positive_count = sum(1 for kw in positive_keywords if kw in text_lower)
        negative_count = sum(1 for kw in negative_keywords if kw in text_lower)
        
        if positive_count > negative_count + 1:
            sentiment_score = 65
            trend = '看多'
            advice = '買入'
            decision_type = 'buy'
        elif negative_count > positive_count + 1:
            sentiment_score = 35
            trend = '看空'
            advice = '賣出'
            decision_type = 'sell'
        else:
            decision_type = 'hold'
        
        # 擷取前500字元作為摘要
        summary = response_text[:500] if response_text else '無分析結果'
        
        return AnalysisResult(
            code=code,
            name=name,
            sentiment_score=sentiment_score,
            trend_prediction=trend,
            operation_advice=advice,
            decision_type=decision_type,
            confidence_level='低',
            analysis_summary=summary,
            key_points='JSON解析失敗，僅供參考',
            risk_warning='分析結果可能不準確，建議結合其他資訊判斷',
            raw_response=response_text,
            success=True,
        )
    
    def batch_analyze(
        self, 
        contexts: List[Dict[str, Any]],
        delay_between: float = 2.0
    ) -> List[AnalysisResult]:
        """
        批次分析多隻股票
        
        注意：為避免 API 速率限制，每次分析之間會有延遲
        
        Args:
            contexts: 上下文資料列表
            delay_between: 每次分析之間的延遲（秒）
            
        Returns:
            AnalysisResult 列表
        """
        results = []
        
        for i, context in enumerate(contexts):
            if i > 0:
                logger.debug(f"等待 {delay_between} 秒後繼續...")
                time.sleep(delay_between)
            
            result = self.analyze(context)
            results.append(result)
        
        return results


# 便捷函式
def get_analyzer() -> GeminiAnalyzer:
    """獲取 LLM 分析器例項"""
    return GeminiAnalyzer()


if __name__ == "__main__":
    # 測試程式碼
    logging.basicConfig(level=logging.DEBUG)
    
    # 模擬上下文資料
    test_context = {
        'code': '600519',
        'date': '2026-01-09',
        'today': {
            'open': 1800.0,
            'high': 1850.0,
            'low': 1780.0,
            'close': 1820.0,
            'volume': 10000000,
            'amount': 18200000000,
            'pct_chg': 1.5,
            'ma5': 1810.0,
            'ma10': 1800.0,
            'ma20': 1790.0,
            'volume_ratio': 1.2,
        },
        'ma_status': '多頭排列 📈',
        'volume_change_ratio': 1.3,
        'price_change_ratio': 1.5,
    }
    
    analyzer = GeminiAnalyzer()
    
    if analyzer.is_available():
        print("=== AI 分析測試 ===")
        result = analyzer.analyze(test_context)
        print(f"分析結果: {result.to_dict()}")
    else:
        print("Gemini API 未配置，跳過測試")
