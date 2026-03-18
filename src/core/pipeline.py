# -*- coding: utf-8 -*-
"""
===================================
A股自選股智慧分析系統 - 核心分析流水線
===================================

職責：
1. 管理整個分析流程
2. 協調資料獲取、儲存、搜尋、分析、通知等模組
3. 實現併發控制和異常處理
4. 提供股票分析的核心功能
"""

import logging
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import List, Dict, Any, Optional, Tuple

import pandas as pd

from src.config import get_config, Config
from src.storage import get_db
from data_provider import DataFetcherManager
from data_provider.realtime_types import ChipDistribution
from src.analyzer import GeminiAnalyzer, AnalysisResult, fill_chip_structure_if_needed, fill_price_position_if_needed
from src.data.stock_mapping import STOCK_NAME_MAP
from src.notification import NotificationService, NotificationChannel
from src.search_service import SearchService
from src.services.social_sentiment_service import SocialSentimentService
from src.enums import ReportType
from src.stock_analyzer import StockTrendAnalyzer, TrendAnalysisResult
from src.core.trading_calendar import get_market_for_stock, is_market_open
from data_provider.us_index_mapping import is_us_stock_code
from bot.models import BotMessage


logger = logging.getLogger(__name__)


class StockAnalysisPipeline:
    """
    股票分析主流程排程器
    
    職責：
    1. 管理整個分析流程
    2. 協調資料獲取、儲存、搜尋、分析、通知等模組
    3. 實現併發控制和異常處理
    """
    
    def __init__(
        self,
        config: Optional[Config] = None,
        max_workers: Optional[int] = None,
        source_message: Optional[BotMessage] = None,
        query_id: Optional[str] = None,
        query_source: Optional[str] = None,
        save_context_snapshot: Optional[bool] = None
    ):
        """
        初始化排程器
        
        Args:
            config: 配置物件（可選，預設使用全域性配置）
            max_workers: 最大併發執行緒數（可選，預設從配置讀取）
        """
        self.config = config or get_config()
        self.max_workers = max_workers or self.config.max_workers
        self.source_message = source_message
        self.query_id = query_id
        self.query_source = self._resolve_query_source(query_source)
        self.save_context_snapshot = (
            self.config.save_context_snapshot if save_context_snapshot is None else save_context_snapshot
        )
        
        # 初始化各模組
        self.db = get_db()
        self.fetcher_manager = DataFetcherManager()
        # 不再單獨建立 akshare_fetcher，統一使用 fetcher_manager 獲取增強資料
        self.trend_analyzer = StockTrendAnalyzer()  # 趨勢分析器
        self.analyzer = GeminiAnalyzer()
        self.notifier = NotificationService(source_message=source_message)
        
        # 初始化搜尋服務
        self.search_service = SearchService(
            bocha_keys=self.config.bocha_api_keys,
            tavily_keys=self.config.tavily_api_keys,
            brave_keys=self.config.brave_api_keys,
            serpapi_keys=self.config.serpapi_keys,
            minimax_keys=self.config.minimax_api_keys,
            news_max_age_days=self.config.news_max_age_days,
            news_strategy_profile=getattr(self.config, "news_strategy_profile", "short"),
        )
        
        logger.info(f"排程器初始化完成，最大併發數: {self.max_workers}")
        logger.info("已啟用趨勢分析器 (MA5>MA10>MA20 多頭判斷)")
        # 列印實時行情/籌碼配置狀態
        if self.config.enable_realtime_quote:
            logger.info(f"實時行情已啟用 (優先順序: {self.config.realtime_source_priority})")
        else:
            logger.info("實時行情已禁用，將使用歷史收盤價")
        if self.config.enable_chip_distribution:
            logger.info("籌碼分佈分析已啟用")
        else:
            logger.info("籌碼分佈分析已禁用")
        if self.search_service.is_available:
            logger.info("搜尋服務已啟用 (Tavily/SerpAPI)")
        else:
            logger.warning("搜尋服務未啟用（未配置 API Key）")

        # 初始化社交輿情服務（僅美股）
        self.social_sentiment_service = SocialSentimentService(
            api_key=self.config.social_sentiment_api_key,
            api_url=self.config.social_sentiment_api_url,
        )
        if self.social_sentiment_service.is_available:
            logger.info("Social sentiment service enabled (Reddit/X/Polymarket, US stocks only)")

    def fetch_and_save_stock_data(
        self, 
        code: str,
        force_refresh: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """
        獲取並儲存單隻股票資料
        
        斷點續傳邏輯：
        1. 檢查資料庫是否已有今日資料
        2. 如果有且不強制重新整理，則跳過網路請求
        3. 否則從資料來源獲取並儲存
        
        Args:
            code: 股票程式碼
            force_refresh: 是否強制重新整理（忽略本地快取）
            
        Returns:
            Tuple[是否成功, 錯誤資訊]
        """
        try:
            # 首先獲取股票名稱
            stock_name = self.fetcher_manager.get_stock_name(code)

            today = date.today()
            # 注意：這裡用自然日 date.today() 做“斷點續傳”判斷。
            # 若在週末/節假日/非交易日執行，或機器時區不在中國，可能出現：
            # - 資料庫已有最新交易日資料但仍會重複拉取（has_today_data 返回 False）
            # - 或在跨日/時區偏移時誤判“今日已有資料”
            # 該行為目前保留（按需求不改邏輯），但如需更嚴謹可改為“最新交易日/資料來源最新日期”判斷。
            
            # 斷點續傳檢查：如果今日資料已存在，跳過
            if not force_refresh and self.db.has_today_data(code, today):
                logger.info(f"{stock_name}({code}) 今日資料已存在，跳過獲取（斷點續傳）")
                return True, None

            # 從資料來源獲取資料
            logger.info(f"{stock_name}({code}) 開始從資料來源獲取資料...")
            df, source_name = self.fetcher_manager.get_daily_data(code, days=30)

            if df is None or df.empty:
                return False, "獲取資料為空"

            # 儲存到資料庫
            saved_count = self.db.save_daily_data(df, code, source_name)
            logger.info(f"{stock_name}({code}) 資料儲存成功（來源: {source_name}，新增 {saved_count} 條）")

            return True, None

        except Exception as e:
            error_msg = f"獲取/儲存資料失敗: {str(e)}"
            logger.error(f"{stock_name}({code}) {error_msg}")
            return False, error_msg
    
    def analyze_stock(self, code: str, report_type: ReportType, query_id: str) -> Optional[AnalysisResult]:
        """
        分析單隻股票（增強版：含量比、換手率、籌碼分析、多維度情報）
        
        流程：
        1. 獲取實時行情（量比、換手率）- 透過 DataFetcherManager 自動故障切換
        2. 獲取籌碼分佈 - 透過 DataFetcherManager 帶熔斷保護
        3. 進行趨勢分析（基於交易理念）
        4. 多維度情報搜尋（最新訊息+風險排查+業績預期）
        5. 從資料庫獲取分析上下文
        6. 呼叫 AI 進行綜合分析
        
        Args:
            query_id: 查詢鏈路關聯 id
            code: 股票程式碼
            report_type: 報告型別
            
        Returns:
            AnalysisResult 或 None（如果分析失敗）
        """
        try:
            # 獲取股票名稱（優先從實時行情獲取真實名稱）
            stock_name = self.fetcher_manager.get_stock_name(code)

            # Step 1: 獲取實時行情（量比、換手率等）- 使用統一入口，自動故障切換
            realtime_quote = None
            try:
                realtime_quote = self.fetcher_manager.get_realtime_quote(code)
                if realtime_quote:
                    # 使用實時行情返回的真實股票名稱
                    if realtime_quote.name:
                        stock_name = realtime_quote.name
                    # 相容不同資料來源的欄位（有些資料來源可能沒有 volume_ratio）
                    volume_ratio = getattr(realtime_quote, 'volume_ratio', None)
                    turnover_rate = getattr(realtime_quote, 'turnover_rate', None)
                    logger.info(f"{stock_name}({code}) 實時行情: 價格={realtime_quote.price}, "
                              f"量比={volume_ratio}, 換手率={turnover_rate}% "
                              f"(來源: {realtime_quote.source.value if hasattr(realtime_quote, 'source') else 'unknown'})")
                else:
                    logger.info(f"{stock_name}({code}) 實時行情獲取失敗或已禁用，將使用歷史資料進行分析")
            except Exception as e:
                logger.warning(f"{stock_name}({code}) 獲取實時行情失敗: {e}")

            # 如果還是沒有名稱，使用程式碼作為名稱
            if not stock_name:
                stock_name = f'股票{code}'

            # Step 2: 獲取籌碼分佈 - 使用統一入口，帶熔斷保護
            chip_data = None
            try:
                chip_data = self.fetcher_manager.get_chip_distribution(code)
                if chip_data:
                    logger.info(f"{stock_name}({code}) 籌碼分佈: 獲利比例={chip_data.profit_ratio:.1%}, "
                              f"90%集中度={chip_data.concentration_90:.2%}")
                else:
                    logger.debug(f"{stock_name}({code}) 籌碼分佈獲取失敗或已禁用")
            except Exception as e:
                logger.warning(f"{stock_name}({code}) 獲取籌碼分佈失敗: {e}")

            # If agent mode is explicitly enabled, or specific agent skills are configured, use the Agent analysis pipeline.
            # NOTE: use config.agent_mode (explicit opt-in) instead of
            # config.is_agent_available() so that users who only configured an
            # API Key for the traditional analysis path are not silently
            # switched to Agent mode (which is slower and more expensive).
            use_agent = getattr(self.config, 'agent_mode', False)
            if not use_agent:
                # Auto-enable agent mode when specific skills are configured (e.g., scheduled task with strategy)
                configured_skills = getattr(self.config, 'agent_skills', [])
                if configured_skills and configured_skills != ['all']:
                    use_agent = True
                    logger.info(f"{stock_name}({code}) Auto-enabled agent mode due to configured skills: {configured_skills}")

            # Step 2.5: 基本面能力聚合（統一入口，異常降級）
            # - 失敗時返回 partial/failed，不影響既有技術面/新聞鏈路
            # - 關閉開關時仍返回 not_supported 結構
            fundamental_context = None
            try:
                fundamental_context = self.fetcher_manager.get_fundamental_context(
                    code,
                    budget_seconds=getattr(self.config, 'fundamental_stage_timeout_seconds', 1.5),
                )
            except Exception as e:
                logger.warning(f"{stock_name}({code}) 基本面聚合失敗: {e}")
                fundamental_context = self.fetcher_manager.build_failed_fundamental_context(code, str(e))

            # P0: write-only snapshot, fail-open, no read dependency on this table.
            try:
                self.db.save_fundamental_snapshot(
                    query_id=query_id,
                    code=code,
                    payload=fundamental_context,
                    source_chain=fundamental_context.get("source_chain", []),
                    coverage=fundamental_context.get("coverage", {}),
                )
            except Exception as e:
                logger.debug(f"{stock_name}({code}) 基本面快照寫入失敗: {e}")

            # Step 3: 趨勢分析（基於交易理念）— 在 Agent 分支之前執行，供兩條路徑共用
            trend_result: Optional[TrendAnalysisResult] = None
            try:
                end_date = date.today()
                start_date = end_date - timedelta(days=89)  # ~60 trading days for MA60
                historical_bars = self.db.get_data_range(code, start_date, end_date)
                if historical_bars:
                    df = pd.DataFrame([bar.to_dict() for bar in historical_bars])
                    # Issue #234: Augment with realtime for intraday MA calculation
                    if self.config.enable_realtime_quote and realtime_quote:
                        df = self._augment_historical_with_realtime(df, realtime_quote, code)
                    trend_result = self.trend_analyzer.analyze(df, code)
                    logger.info(f"{stock_name}({code}) 趨勢分析: {trend_result.trend_status.value}, "
                              f"買入訊號={trend_result.buy_signal.value}, 評分={trend_result.signal_score}")
            except Exception as e:
                logger.warning(f"{stock_name}({code}) 趨勢分析失敗: {e}", exc_info=True)

            if use_agent:
                logger.info(f"{stock_name}({code}) 啟用 Agent 模式進行分析")
                return self._analyze_with_agent(
                    code,
                    report_type,
                    query_id,
                    stock_name,
                    realtime_quote,
                    chip_data,
                    fundamental_context,
                    trend_result,
                )

            # Step 4: 多維度情報搜尋（最新訊息+風險排查+業績預期）
            news_context = None
            if self.search_service.is_available:
                logger.info(f"{stock_name}({code}) 開始多維度情報搜尋...")

                # 使用多維度搜尋（最多5次搜尋）
                intel_results = self.search_service.search_comprehensive_intel(
                    stock_code=code,
                    stock_name=stock_name,
                    max_searches=5
                )

                # 格式化情報報告
                if intel_results:
                    news_context = self.search_service.format_intel_report(intel_results, stock_name)
                    total_results = sum(
                        len(r.results) for r in intel_results.values() if r.success
                    )
                    logger.info(f"{stock_name}({code}) 情報搜尋完成: 共 {total_results} 條結果")
                    logger.debug(f"{stock_name}({code}) 情報搜尋結果:\n{news_context}")

                    # 儲存新聞情報到資料庫（用於後續覆盤與查詢）
                    try:
                        query_context = self._build_query_context(query_id=query_id)
                        for dim_name, response in intel_results.items():
                            if response and response.success and response.results:
                                self.db.save_news_intel(
                                    code=code,
                                    name=stock_name,
                                    dimension=dim_name,
                                    query=response.query,
                                    response=response,
                                    query_context=query_context
                                )
                    except Exception as e:
                        logger.warning(f"{stock_name}({code}) 儲存新聞情報失敗: {e}")
            else:
                logger.info(f"{stock_name}({code}) 搜尋服務不可用，跳過情報搜尋")

            # Step 4.5: Social sentiment intelligence (US stocks only)
            if self.social_sentiment_service.is_available and is_us_stock_code(code):
                try:
                    social_context = self.social_sentiment_service.get_social_context(code)
                    if social_context:
                        logger.info(f"{stock_name}({code}) Social sentiment data retrieved")
                        if news_context:
                            news_context = news_context + "\n\n" + social_context
                        else:
                            news_context = social_context
                except Exception as e:
                    logger.warning(f"{stock_name}({code}) Social sentiment fetch failed: {e}")

            # Step 5: 獲取分析上下文（技術面資料）
            context = self.db.get_analysis_context(code)

            if context is None:
                logger.warning(f"{stock_name}({code}) 無法獲取歷史行情資料，將僅基於新聞和實時行情分析")
                context = {
                    'code': code,
                    'stock_name': stock_name,
                    'date': date.today().isoformat(),
                    'data_missing': True,
                    'today': {},
                    'yesterday': {}
                }
            
            # Step 6: 增強上下文資料（新增實時行情、籌碼、趨勢分析結果、股票名稱）
            enhanced_context = self._enhance_context(
                context, 
                realtime_quote, 
                chip_data,
                trend_result,
                stock_name,  # 傳入股票名稱
                fundamental_context,
            )
            
            # Step 7: 呼叫 AI 分析（傳入增強的上下文和新聞）
            result = self.analyzer.analyze(enhanced_context, news_context=news_context)

            # Step 7.5: 填充分析時的價格資訊到 result
            if result:
                result.query_id = query_id
                realtime_data = enhanced_context.get('realtime', {})
                result.current_price = realtime_data.get('price')
                result.change_pct = realtime_data.get('change_pct')

            # Step 7.6: chip_structure fallback (Issue #589)
            if result and chip_data:
                fill_chip_structure_if_needed(result, chip_data)

            # Step 7.7: price_position fallback
            if result:
                fill_price_position_if_needed(result, trend_result, realtime_quote)

            # Step 8: 儲存分析歷史記錄
            if result:
                try:
                    context_snapshot = self._build_context_snapshot(
                        enhanced_context=enhanced_context,
                        news_content=news_context,
                        realtime_quote=realtime_quote,
                        chip_data=chip_data
                    )
                    self.db.save_analysis_history(
                        result=result,
                        query_id=query_id,
                        report_type=report_type.value,
                        news_content=news_context,
                        context_snapshot=context_snapshot,
                        save_snapshot=self.save_context_snapshot
                    )
                except Exception as e:
                    logger.warning(f"{stock_name}({code}) 儲存分析歷史失敗: {e}")

            return result

        except Exception as e:
            logger.error(f"{stock_name}({code}) 分析失敗: {e}")
            logger.exception(f"{stock_name}({code}) 詳細錯誤資訊:")
            return None
    
    def _enhance_context(
        self,
        context: Dict[str, Any],
        realtime_quote,
        chip_data: Optional[ChipDistribution],
        trend_result: Optional[TrendAnalysisResult],
        stock_name: str = "",
        fundamental_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        增強分析上下文
        
        將實時行情、籌碼分佈、趨勢分析結果、股票名稱新增到上下文中
        
        Args:
            context: 原始上下文
            realtime_quote: 實時行情資料（UnifiedRealtimeQuote 或 None）
            chip_data: 籌碼分佈資料
            trend_result: 趨勢分析結果
            stock_name: 股票名稱
            
        Returns:
            增強後的上下文
        """
        enhanced = context.copy()
        
        # 新增股票名稱
        if stock_name:
            enhanced['stock_name'] = stock_name
        elif realtime_quote and getattr(realtime_quote, 'name', None):
            enhanced['stock_name'] = realtime_quote.name

        # 將執行時搜尋視窗透傳給 analyzer，避免與全域性配置重新讀取產生視窗不一致
        enhanced['news_window_days'] = getattr(self.search_service, "news_window_days", 3)
        
        # 新增實時行情（相容不同資料來源的欄位差異）
        if realtime_quote:
            # 使用 getattr 安全獲取欄位，缺失欄位返回 None 或預設值
            volume_ratio = getattr(realtime_quote, 'volume_ratio', None)
            enhanced['realtime'] = {
                'name': getattr(realtime_quote, 'name', ''),
                'price': getattr(realtime_quote, 'price', None),
                'change_pct': getattr(realtime_quote, 'change_pct', None),
                'volume_ratio': volume_ratio,
                'volume_ratio_desc': self._describe_volume_ratio(volume_ratio) if volume_ratio else '無資料',
                'turnover_rate': getattr(realtime_quote, 'turnover_rate', None),
                'pe_ratio': getattr(realtime_quote, 'pe_ratio', None),
                'pb_ratio': getattr(realtime_quote, 'pb_ratio', None),
                'total_mv': getattr(realtime_quote, 'total_mv', None),
                'circ_mv': getattr(realtime_quote, 'circ_mv', None),
                'change_60d': getattr(realtime_quote, 'change_60d', None),
                'source': getattr(realtime_quote, 'source', None),
            }
            # 移除 None 值以減少上下文大小
            enhanced['realtime'] = {k: v for k, v in enhanced['realtime'].items() if v is not None}
        
        # 新增籌碼分佈
        if chip_data:
            current_price = getattr(realtime_quote, 'price', 0) if realtime_quote else 0
            enhanced['chip'] = {
                'profit_ratio': chip_data.profit_ratio,
                'avg_cost': chip_data.avg_cost,
                'concentration_90': chip_data.concentration_90,
                'concentration_70': chip_data.concentration_70,
                'chip_status': chip_data.get_chip_status(current_price or 0),
            }
        
        # 新增趨勢分析結果
        if trend_result:
            enhanced['trend_analysis'] = {
                'trend_status': trend_result.trend_status.value,
                'ma_alignment': trend_result.ma_alignment,
                'trend_strength': trend_result.trend_strength,
                'bias_ma5': trend_result.bias_ma5,
                'bias_ma10': trend_result.bias_ma10,
                'volume_status': trend_result.volume_status.value,
                'volume_trend': trend_result.volume_trend,
                'buy_signal': trend_result.buy_signal.value,
                'signal_score': trend_result.signal_score,
                'signal_reasons': trend_result.signal_reasons,
                'risk_factors': trend_result.risk_factors,
            }

        # Issue #234: Override today with realtime OHLC + trend MA for intraday analysis
        # Guard: trend_result.ma5 > 0 ensures MA calculation succeeded (data sufficient)
        if realtime_quote and trend_result and trend_result.ma5 > 0:
            price = getattr(realtime_quote, 'price', None)
            if price is not None and price > 0:
                yesterday_close = None
                if enhanced.get('yesterday') and isinstance(enhanced['yesterday'], dict):
                    yesterday_close = enhanced['yesterday'].get('close')
                orig_today = enhanced.get('today') or {}
                open_p = getattr(realtime_quote, 'open_price', None) or getattr(
                    realtime_quote, 'pre_close', None
                ) or yesterday_close or orig_today.get('open') or price
                high_p = getattr(realtime_quote, 'high', None) or price
                low_p = getattr(realtime_quote, 'low', None) or price
                vol = getattr(realtime_quote, 'volume', None)
                amt = getattr(realtime_quote, 'amount', None)
                pct = getattr(realtime_quote, 'change_pct', None)
                realtime_today = {
                    'close': price,
                    'open': open_p,
                    'high': high_p,
                    'low': low_p,
                    'ma5': trend_result.ma5,
                    'ma10': trend_result.ma10,
                    'ma20': trend_result.ma20,
                }
                if vol is not None:
                    realtime_today['volume'] = vol
                if amt is not None:
                    realtime_today['amount'] = amt
                if pct is not None:
                    realtime_today['pct_chg'] = pct
                for k, v in orig_today.items():
                    if k not in realtime_today and v is not None:
                        realtime_today[k] = v
                enhanced['today'] = realtime_today
                enhanced['ma_status'] = self._compute_ma_status(
                    price, trend_result.ma5, trend_result.ma10, trend_result.ma20
                )
                enhanced['date'] = date.today().isoformat()
                if yesterday_close is not None:
                    try:
                        yc = float(yesterday_close)
                        if yc > 0:
                            enhanced['price_change_ratio'] = round(
                                (price - yc) / yc * 100, 2
                            )
                    except (TypeError, ValueError):
                        pass
                if vol is not None and enhanced.get('yesterday'):
                    yest_vol = enhanced['yesterday'].get('volume') if isinstance(
                        enhanced['yesterday'], dict
                    ) else None
                    if yest_vol is not None:
                        try:
                            yv = float(yest_vol)
                            if yv > 0:
                                enhanced['volume_change_ratio'] = round(
                                    float(vol) / yv, 2
                                )
                        except (TypeError, ValueError):
                            pass

        # ETF/index flag for analyzer prompt (Fixes #274)
        enhanced['is_index_etf'] = SearchService.is_index_or_etf(
            context.get('code', ''), enhanced.get('stock_name', stock_name)
        )

        # P0: append unified fundamental block; keep as additional context only
        enhanced["fundamental_context"] = (
            fundamental_context
            if isinstance(fundamental_context, dict)
            else self.fetcher_manager.build_failed_fundamental_context(
                context.get("code", ""),
                "invalid fundamental context",
            )
        )

        return enhanced

    def _analyze_with_agent(
        self, 
        code: str, 
        report_type: ReportType, 
        query_id: str,
        stock_name: str,
        realtime_quote: Any,
        chip_data: Optional[ChipDistribution],
        fundamental_context: Optional[Dict[str, Any]] = None,
        trend_result: Optional[TrendAnalysisResult] = None,
    ) -> Optional[AnalysisResult]:
        """
        使用 Agent 模式分析單隻股票。
        """
        try:
            from src.agent.factory import build_agent_executor

            # Build executor from shared factory (ToolRegistry and SkillManager prototype are cached)
            executor = build_agent_executor(self.config, getattr(self.config, 'agent_skills', None) or None)

            # Build initial context to avoid redundant tool calls
            initial_context = {
                "stock_code": code,
                "stock_name": stock_name,
                "report_type": report_type.value,
                "fundamental_context": fundamental_context,
            }
            
            if realtime_quote:
                initial_context["realtime_quote"] = self._safe_to_dict(realtime_quote)
            if chip_data:
                initial_context["chip_distribution"] = self._safe_to_dict(chip_data)
            if trend_result:
                initial_context["trend_result"] = self._safe_to_dict(trend_result)

            # Agent path: inject social sentiment as news_context so both
            # executor (_build_user_message) and orchestrator (ctx.set_data)
            # can consume it through the existing news_context channel
            if self.social_sentiment_service.is_available and is_us_stock_code(code):
                try:
                    social_context = self.social_sentiment_service.get_social_context(code)
                    if social_context:
                        existing = initial_context.get("news_context")
                        if existing:
                            initial_context["news_context"] = existing + "\n\n" + social_context
                        else:
                            initial_context["news_context"] = social_context
                        logger.info(f"[{code}] Agent mode: social sentiment data injected into news_context")
                except Exception as e:
                    logger.warning(f"[{code}] Agent mode: social sentiment fetch failed: {e}")

            # 執行 Agent
            message = f"請分析股票 {code} ({stock_name})，並生成決策儀表盤報告。"
            agent_result = executor.run(message, context=initial_context)

            # 轉換為 AnalysisResult
            result = self._agent_result_to_analysis_result(agent_result, code, stock_name, report_type, query_id)
            if result:
                result.query_id = query_id
            # Agent weak integrity: placeholder fill only, no LLM retry
            if result and getattr(self.config, "report_integrity_enabled", False):
                from src.analyzer import check_content_integrity, apply_placeholder_fill

                pass_integrity, missing = check_content_integrity(result)
                if not pass_integrity:
                    apply_placeholder_fill(result, missing)
                    logger.info(
                        "[LLM完整性] integrity_mode=agent_weak 必填欄位缺失 %s，已佔位補全",
                        missing,
                    )
            # chip_structure fallback (Issue #589), before save_analysis_history
            if result and chip_data:
                fill_chip_structure_if_needed(result, chip_data)

            # price_position fallback (same as non-agent path Step 7.7)
            if result:
                fill_price_position_if_needed(result, trend_result, realtime_quote)

            resolved_stock_name = result.name if result and result.name else stock_name

            # 儲存新聞情報到資料庫（Agent 工具結果僅用於 LLM 上下文，未持久化，Fixes #396）
            # 使用 search_stock_news（與 Agent 工具呼叫邏輯一致），僅 1 次 API 呼叫，無額外延遲
            if self.search_service.is_available:
                try:
                    news_response = self.search_service.search_stock_news(
                        stock_code=code,
                        stock_name=resolved_stock_name,
                        max_results=5
                    )
                    if news_response.success and news_response.results:
                        query_context = self._build_query_context(query_id=query_id)
                        self.db.save_news_intel(
                            code=code,
                            name=resolved_stock_name,
                            dimension="latest_news",
                            query=news_response.query,
                            response=news_response,
                            query_context=query_context
                        )
                        logger.info(f"[{code}] Agent 模式: 新聞情報已儲存 {len(news_response.results)} 條")
                except Exception as e:
                    logger.warning(f"[{code}] Agent 模式儲存新聞情報失敗: {e}")

            # 儲存分析歷史記錄
            if result:
                try:
                    initial_context["stock_name"] = resolved_stock_name
                    self.db.save_analysis_history(
                        result=result,
                        query_id=query_id,
                        report_type=report_type.value,
                        news_content=None,
                        context_snapshot=initial_context,
                        save_snapshot=self.save_context_snapshot
                    )
                except Exception as e:
                    logger.warning(f"[{code}] 儲存 Agent 分析歷史失敗: {e}")

            return result

        except Exception as e:
            logger.error(f"[{code}] Agent 分析失敗: {e}")
            logger.exception(f"[{code}] Agent 詳細錯誤資訊:")
            return None

    def _agent_result_to_analysis_result(
        self, agent_result, code: str, stock_name: str, report_type: ReportType, query_id: str
    ) -> AnalysisResult:
        """
        將 AgentResult 轉換為 AnalysisResult。
        """
        result = AnalysisResult(
            code=code,
            name=stock_name,
            sentiment_score=50,
            trend_prediction="未知",
            operation_advice="觀望",
            success=agent_result.success,
            error_message=agent_result.error or None,
            data_sources=f"agent:{agent_result.provider}",
            model_used=agent_result.model or None,
        )

        if agent_result.success and agent_result.dashboard:
            dash = agent_result.dashboard
            ai_stock_name = str(dash.get("stock_name", "")).strip()
            if ai_stock_name and self._is_placeholder_stock_name(stock_name, code):
                result.name = ai_stock_name
            result.sentiment_score = self._safe_int(dash.get("sentiment_score"), 50)
            result.trend_prediction = dash.get("trend_prediction", "未知")
            raw_advice = dash.get("operation_advice", "觀望")
            if isinstance(raw_advice, dict):
                # LLM may return {"no_position": "...", "has_position": "..."}
                # Derive a short string from decision_type for the scalar field
                _signal_to_advice = {
                    "buy": "買入", "sell": "賣出", "hold": "持有",
                    "strong_buy": "強烈買入", "strong_sell": "強烈賣出",
                }
                # Normalize decision_type (strip/lower) before lookup so
                # variants like "BUY" or " Buy " map correctly.
                raw_dt = str(dash.get("decision_type") or "hold").strip().lower()
                result.operation_advice = _signal_to_advice.get(raw_dt, "觀望")
            else:
                result.operation_advice = str(raw_advice) if raw_advice else "觀望"
            from src.agent.protocols import normalize_decision_signal

            result.decision_type = normalize_decision_signal(
                dash.get("decision_type", "hold")
            )
            result.analysis_summary = dash.get("analysis_summary", "")
            # The AI returns a top-level dict that contains a nested 'dashboard' sub-key
            # with core_conclusion / battle_plan / intelligence.  AnalysisResult's helper
            # methods (get_sniper_points, get_core_conclusion, etc.) expect that inner
            # structure, so we unwrap it here.
            result.dashboard = dash.get("dashboard") or dash
        else:
            result.sentiment_score = 50
            result.operation_advice = "觀望"
            if not result.error_message:
                result.error_message = "Agent 未能生成有效的決策儀表盤"

        return result

    @staticmethod
    def _is_placeholder_stock_name(name: str, code: str) -> bool:
        """Return True when the stock name is missing or placeholder-like."""
        if not name:
            return True
        normalized = str(name).strip()
        if not normalized:
            return True
        if normalized == code:
            return True
        if normalized.startswith("股票"):
            return True
        if "Unknown" in normalized:
            return True
        return False

    @staticmethod
    def _safe_int(value: Any, default: int = 50) -> int:
        """安全地將值轉換為整數。"""
        if value is None:
            return default
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            import re
            match = re.search(r'-?\d+', value)
            if match:
                return int(match.group())
        return default
    
    def _describe_volume_ratio(self, volume_ratio: float) -> str:
        """
        量比描述
        
        量比 = 當前成交量 / 過去5日平均成交量
        """
        if volume_ratio < 0.5:
            return "極度萎縮"
        elif volume_ratio < 0.8:
            return "明顯萎縮"
        elif volume_ratio < 1.2:
            return "正常"
        elif volume_ratio < 2.0:
            return "溫和放量"
        elif volume_ratio < 3.0:
            return "明顯放量"
        else:
            return "巨量"

    @staticmethod
    def _compute_ma_status(close: float, ma5: float, ma10: float, ma20: float) -> str:
        """
        Compute MA alignment status from price and MA values.
        Logic mirrors storage._analyze_ma_status (Issue #234).
        """
        close = close or 0
        ma5 = ma5 or 0
        ma10 = ma10 or 0
        ma20 = ma20 or 0
        if close > ma5 > ma10 > ma20 > 0:
            return "多頭排列 📈"
        elif close < ma5 < ma10 < ma20 and ma20 > 0:
            return "空頭排列 📉"
        elif close > ma5 and ma5 > ma10:
            return "短期向好 🔼"
        elif close < ma5 and ma5 < ma10:
            return "短期走弱 🔽"
        else:
            return "震盪整理 ↔️"

    def _augment_historical_with_realtime(
        self, df: pd.DataFrame, realtime_quote: Any, code: str
    ) -> pd.DataFrame:
        """
        Augment historical OHLCV with today's realtime quote for intraday MA calculation.
        Issue #234: Use realtime price instead of yesterday's close for technical indicators.
        """
        if df is None or df.empty or 'close' not in df.columns:
            return df
        if realtime_quote is None:
            return df
        price = getattr(realtime_quote, 'price', None)
        if price is None or not (isinstance(price, (int, float)) and price > 0):
            return df

        # Optional: skip augmentation on non-trading days (fail-open)
        enable_realtime_tech = getattr(
            self.config, 'enable_realtime_technical_indicators', True
        )
        if not enable_realtime_tech:
            return df
        market = get_market_for_stock(code)
        if market and not is_market_open(market, date.today()):
            return df

        last_val = df['date'].max()
        last_date = (
            last_val.date() if hasattr(last_val, 'date') else
            (last_val if isinstance(last_val, date) else pd.Timestamp(last_val).date())
        )
        yesterday_close = float(df.iloc[-1]['close']) if len(df) > 0 else price
        open_p = getattr(realtime_quote, 'open_price', None) or getattr(
            realtime_quote, 'pre_close', None
        ) or yesterday_close
        high_p = getattr(realtime_quote, 'high', None) or price
        low_p = getattr(realtime_quote, 'low', None) or price
        vol = getattr(realtime_quote, 'volume', None) or 0
        amt = getattr(realtime_quote, 'amount', None)
        pct = getattr(realtime_quote, 'change_pct', None)

        if last_date >= date.today():
            # Update last row with realtime close (copy to avoid mutating caller's df)
            df = df.copy()
            idx = df.index[-1]
            df.loc[idx, 'close'] = price
            if open_p is not None:
                df.loc[idx, 'open'] = open_p
            if high_p is not None:
                df.loc[idx, 'high'] = high_p
            if low_p is not None:
                df.loc[idx, 'low'] = low_p
            if vol:
                df.loc[idx, 'volume'] = vol
            if amt is not None:
                df.loc[idx, 'amount'] = amt
            if pct is not None:
                df.loc[idx, 'pct_chg'] = pct
        else:
            # Append virtual today row
            new_row = {
                'code': code,
                'date': date.today(),
                'open': open_p,
                'high': high_p,
                'low': low_p,
                'close': price,
                'volume': vol,
                'amount': amt if amt is not None else 0,
                'pct_chg': pct if pct is not None else 0,
            }
            new_df = pd.DataFrame([new_row])
            df = pd.concat([df, new_df], ignore_index=True)
        return df

    def _build_context_snapshot(
        self,
        enhanced_context: Dict[str, Any],
        news_content: Optional[str],
        realtime_quote: Any,
        chip_data: Optional[ChipDistribution]
    ) -> Dict[str, Any]:
        """
        構建分析上下文快照
        """
        return {
            "enhanced_context": enhanced_context,
            "news_content": news_content,
            "realtime_quote_raw": self._safe_to_dict(realtime_quote),
            "chip_distribution_raw": self._safe_to_dict(chip_data),
        }

    @staticmethod
    def _safe_to_dict(value: Any) -> Optional[Dict[str, Any]]:
        """
        安全轉換為字典
        """
        if value is None:
            return None
        if hasattr(value, "to_dict"):
            try:
                return value.to_dict()
            except Exception:
                return None
        if hasattr(value, "__dict__"):
            try:
                return dict(value.__dict__)
            except Exception:
                return None
        return None

    def _resolve_query_source(self, query_source: Optional[str]) -> str:
        """
        解析請求來源。

        優先順序（從高到低）：
        1. 顯式傳入的 query_source：呼叫方明確指定時優先使用，便於覆蓋推斷結果或相容未來 source_message 來自非 bot 的場景
        2. 存在 source_message 時推斷為 "bot"：當前約定為機器人會話上下文
        3. 存在 query_id 時推斷為 "web"：Web 觸發的請求會帶上 query_id
        4. 預設 "system"：定時任務或 CLI 等無上述上下文時

        Args:
            query_source: 呼叫方顯式指定的來源，如 "bot" / "web" / "cli" / "system"

        Returns:
            歸一化後的來源標識字串，如 "bot" / "web" / "cli" / "system"
        """
        if query_source:
            return query_source
        if self.source_message:
            return "bot"
        if self.query_id:
            return "web"
        return "system"

    def _build_query_context(self, query_id: Optional[str] = None) -> Dict[str, str]:
        """
        生成使用者查詢關聯資訊
        """
        effective_query_id = query_id or self.query_id or ""

        context: Dict[str, str] = {
            "query_id": effective_query_id,
            "query_source": self.query_source or "",
        }

        if self.source_message:
            context.update({
                "requester_platform": self.source_message.platform or "",
                "requester_user_id": self.source_message.user_id or "",
                "requester_user_name": self.source_message.user_name or "",
                "requester_chat_id": self.source_message.chat_id or "",
                "requester_message_id": self.source_message.message_id or "",
                "requester_query": self.source_message.content or "",
            })

        return context
    
    def process_single_stock(
        self,
        code: str,
        skip_analysis: bool = False,
        single_stock_notify: bool = False,
        report_type: ReportType = ReportType.SIMPLE,
        analysis_query_id: Optional[str] = None,
    ) -> Optional[AnalysisResult]:
        """
        處理單隻股票的完整流程

        包括：
        1. 獲取資料
        2. 儲存資料
        3. AI 分析
        4. 單股推送（可選，#55）

        此方法會被執行緒池呼叫，需要處理好異常

        Args:
            analysis_query_id: 查詢鏈路關聯 id
            code: 股票程式碼
            skip_analysis: 是否跳過 AI 分析
            single_stock_notify: 是否啟用單股推送模式（每分析完一隻立即推送）
            report_type: 報告型別列舉（從配置讀取，Issue #119）

        Returns:
            AnalysisResult 或 None
        """
        logger.info(f"========== 開始處理 {code} ==========")
        
        try:
            # Step 1: 獲取並儲存資料
            success, error = self.fetch_and_save_stock_data(code)
            
            if not success:
                logger.warning(f"[{code}] 資料獲取失敗: {error}")
                # 即使獲取失敗，也嘗試用已有資料分析
            
            # Step 2: AI 分析
            if skip_analysis:
                logger.info(f"[{code}] 跳過 AI 分析（dry-run 模式）")
                return None
            
            effective_query_id = analysis_query_id or self.query_id or uuid.uuid4().hex
            result = self.analyze_stock(code, report_type, query_id=effective_query_id)
            
            if result:
                if not result.success:
                    logger.warning(
                        f"[{code}] 分析未成功: {result.error_message or '未知錯誤'}"
                    )
                else:
                    logger.info(
                        f"[{code}] 分析完成: {result.operation_advice}, "
                        f"評分 {result.sentiment_score}"
                    )
                
                # 單股推送模式（#55）：每分析完一隻股票立即推送
                if single_stock_notify and self.notifier.is_available():
                    try:
                        # 根據報告型別選擇生成方法
                        if report_type == ReportType.FULL:
                            report_content = self.notifier.generate_dashboard_report([result])
                            logger.info(f"[{code}] 使用完整報告格式")
                        elif report_type == ReportType.BRIEF:
                            report_content = self.notifier.generate_brief_report([result])
                            logger.info(f"[{code}] 使用簡潔報告格式")
                        else:
                            report_content = self.notifier.generate_single_stock_report(result)
                            logger.info(f"[{code}] 使用精簡報告格式")
                        
                        if self.notifier.send(report_content, email_stock_codes=[code]):
                            logger.info(f"[{code}] 單股推送成功")
                        else:
                            logger.warning(f"[{code}] 單股推送失敗")
                    except Exception as e:
                        logger.error(f"[{code}] 單股推送異常: {e}")
            
            return result
            
        except Exception as e:
            # 捕獲所有異常，確保單股失敗不影響整體
            logger.exception(f"[{code}] 處理過程發生未知異常: {e}")
            return None
    
    def run(
        self,
        stock_codes: Optional[List[str]] = None,
        dry_run: bool = False,
        send_notification: bool = True,
        merge_notification: bool = False
    ) -> List[AnalysisResult]:
        """
        執行完整的分析流程

        流程：
        1. 獲取待分析的股票列表
        2. 使用執行緒池併發處理
        3. 收集分析結果
        4. 傳送通知

        Args:
            stock_codes: 股票程式碼列表（可選，預設使用配置中的自選股）
            dry_run: 是否僅獲取資料不分析
            send_notification: 是否傳送推送通知
            merge_notification: 是否合併推送（跳過本次推送，由 main 層合併個股+大盤後統一傳送，Issue #190）

        Returns:
            分析結果列表
        """
        start_time = time.time()
        
        # 使用配置中的股票列表
        if stock_codes is None:
            self.config.refresh_stock_list()
            stock_codes = self.config.stock_list
        
        if not stock_codes:
            logger.error("未配置自選股列表，請在 .env 檔案中設定 STOCK_LIST")
            return []
        
        logger.info(f"===== 開始分析 {len(stock_codes)} 只股票 =====")
        logger.info(f"股票列表: {', '.join(stock_codes)}")
        logger.info(f"併發數: {self.max_workers}, 模式: {'僅獲取資料' if dry_run else '完整分析'}")
        
        # === 批次預取實時行情（最佳化：避免每隻股票都觸發全量拉取）===
        # 只有股票數量 >= 5 時才進行預取，少量股票直接逐個查詢更高效
        if len(stock_codes) >= 5:
            prefetch_count = self.fetcher_manager.prefetch_realtime_quotes(stock_codes)
            if prefetch_count > 0:
                logger.info(f"已啟用批次預取架構：一次拉取全市場資料，{len(stock_codes)} 只股票共享快取")

        # Issue #455: 預取股票名稱，避免併發分析時顯示「股票xxxxx」
        # dry_run 僅做資料拉取，不需要名稱預取，避免額外網路開銷
        if not dry_run:
            self.fetcher_manager.prefetch_stock_names(stock_codes, use_bulk=False)

        # 單股推送模式（#55）：從配置讀取
        single_stock_notify = getattr(self.config, 'single_stock_notify', False)
        # Issue #119: 從配置讀取報告型別
        report_type_str = getattr(self.config, 'report_type', 'simple').lower()
        if report_type_str == 'brief':
            report_type = ReportType.BRIEF
        elif report_type_str == 'full':
            report_type = ReportType.FULL
        else:
            report_type = ReportType.SIMPLE
        # Issue #128: 從配置讀取分析間隔
        analysis_delay = getattr(self.config, 'analysis_delay', 0)

        if single_stock_notify:
            logger.info(f"已啟用單股推送模式：每分析完一隻股票立即推送（報告型別: {report_type_str}）")
        
        results: List[AnalysisResult] = []
        
        # 使用執行緒池併發處理
        # 注意：max_workers 設定較低（預設3）以避免觸發反爬
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交任務
            future_to_code = {
                executor.submit(
                    self.process_single_stock,
                    code,
                    skip_analysis=dry_run,
                    single_stock_notify=single_stock_notify and send_notification,
                    report_type=report_type,  # Issue #119: 傳遞報告型別
                    analysis_query_id=uuid.uuid4().hex,
                ): code
                for code in stock_codes
            }
            
            # 收集結果
            for idx, future in enumerate(as_completed(future_to_code)):
                code = future_to_code[future]
                try:
                    result = future.result()
                    if result:
                        results.append(result)

                    # Issue #128: 分析間隔 - 在個股分析和大盤分析之間新增延遲
                    if idx < len(stock_codes) - 1 and analysis_delay > 0:
                        # 注意：此 sleep 發生在“主執行緒收集 future 的迴圈”中，
                        # 並不會阻止執行緒池中的任務同時發起網路請求。
                        # 因此它對降低併發請求峰值的效果有限；真正的峰值主要由 max_workers 決定。
                        # 該行為目前保留（按需求不改邏輯）。
                        logger.debug(f"等待 {analysis_delay} 秒後繼續下一隻股票...")
                        time.sleep(analysis_delay)

                except Exception as e:
                    logger.error(f"[{code}] 任務執行失敗: {e}")
        
        # 統計
        elapsed_time = time.time() - start_time
        
        # dry-run 模式下，資料獲取成功即視為成功
        if dry_run:
            # 檢查哪些股票的資料今天已存在
            success_count = sum(1 for code in stock_codes if self.db.has_today_data(code))
            fail_count = len(stock_codes) - success_count
        else:
            success_count = len(results)
            fail_count = len(stock_codes) - success_count
        
        logger.info("===== 分析完成 =====")
        logger.info(f"成功: {success_count}, 失敗: {fail_count}, 耗時: {elapsed_time:.2f} 秒")
        
        # 儲存報告到本地檔案（無論是否推送通知都儲存）
        if results and not dry_run:
            self._save_local_report(results, report_type)

        # 傳送通知（單股推送模式下跳過彙總推送，避免重複）
        if results and send_notification and not dry_run:
            if single_stock_notify:
                # 單股推送模式：只儲存彙總報告，不再重複推送
                logger.info("單股推送模式：跳過彙總推送，僅儲存報告到本地")
                self._send_notifications(results, report_type, skip_push=True)
            elif merge_notification:
                # 合併模式（Issue #190）：僅儲存，不推送，由 main 層合併個股+大盤後統一傳送
                logger.info("合併推送模式：跳過本次推送，將在個股+大盤覆盤後統一傳送")
                self._send_notifications(results, report_type, skip_push=True)
            else:
                self._send_notifications(results, report_type)
        
        return results
    
    def _save_local_report(
        self,
        results: List[AnalysisResult],
        report_type: ReportType = ReportType.SIMPLE,
    ) -> None:
        """儲存分析報告到本地檔案（與通知推送解耦）"""
        try:
            report = self._generate_aggregate_report(results, report_type)
            filepath = self.notifier.save_report_to_file(report)
            logger.info(f"決策儀表盤日報已儲存: {filepath}")
        except Exception as e:
            logger.error(f"儲存本地報告失敗: {e}")

    def _send_notifications(
        self,
        results: List[AnalysisResult],
        report_type: ReportType = ReportType.SIMPLE,
        skip_push: bool = False,
    ) -> None:
        """
        傳送分析結果通知
        
        生成決策儀表盤格式的報告
        
        Args:
            results: 分析結果列表
            skip_push: 是否跳過推送（僅儲存到本地，用於單股推送模式）
        """
        try:
            logger.info("生成決策儀表盤日報...")
            report = self._generate_aggregate_report(results, report_type)
            
            # 跳過推送（單股推送模式 / 合併模式：報告已由 _save_local_report 儲存）
            if skip_push:
                return
            
            # 推送通知
            if self.notifier.is_available():
                channels = self.notifier.get_available_channels()
                context_success = self.notifier.send_to_context(report)

                # Issue #455: Markdown 轉圖片（與 notification.send 邏輯一致）
                from src.md2img import markdown_to_image

                channels_needing_image = {
                    ch for ch in channels
                    if ch.value in self.notifier._markdown_to_image_channels
                }
                non_wechat_channels_needing_image = {
                    ch for ch in channels_needing_image if ch != NotificationChannel.WECHAT
                }

                def _get_md2img_hint() -> str:
                    try:
                        engine = getattr(get_config(), "md2img_engine", "wkhtmltoimage")
                    except Exception:
                        engine = "wkhtmltoimage"
                    return (
                        "npm i -g markdown-to-file" if engine == "markdown-to-file"
                        else "wkhtmltopdf (apt install wkhtmltopdf / brew install wkhtmltopdf)"
                    )

                image_bytes = None
                if non_wechat_channels_needing_image:
                    image_bytes = markdown_to_image(
                        report, max_chars=self.notifier._markdown_to_image_max_chars
                    )
                    if image_bytes:
                        logger.info(
                            "Markdown 已轉換為圖片，將向 %s 傳送圖片",
                            [ch.value for ch in non_wechat_channels_needing_image],
                        )
                    else:
                        logger.warning(
                            "Markdown 轉圖片失敗，將回退為文字傳送。請檢查 MARKDOWN_TO_IMAGE_CHANNELS 配置並安裝 %s",
                            _get_md2img_hint(),
                        )

                # 企業微信：只發精簡版（平臺限制）
                wechat_success = False
                if NotificationChannel.WECHAT in channels:
                    if report_type == ReportType.BRIEF:
                        dashboard_content = self.notifier.generate_brief_report(results)
                    else:
                        dashboard_content = self.notifier.generate_wechat_dashboard(results)
                    logger.info(f"企業微信儀表盤長度: {len(dashboard_content)} 字元")
                    logger.debug(f"企業微信推送內容:\n{dashboard_content}")
                    wechat_image_bytes = None
                    if NotificationChannel.WECHAT in channels_needing_image:
                        wechat_image_bytes = markdown_to_image(
                            dashboard_content,
                            max_chars=self.notifier._markdown_to_image_max_chars,
                        )
                        if wechat_image_bytes is None:
                            logger.warning(
                                "企業微信 Markdown 轉圖片失敗，將回退為文字傳送。請檢查 MARKDOWN_TO_IMAGE_CHANNELS 配置並安裝 %s",
                                _get_md2img_hint(),
                            )
                    use_image = self.notifier._should_use_image_for_channel(
                        NotificationChannel.WECHAT, wechat_image_bytes
                    )
                    if use_image:
                        wechat_success = self.notifier._send_wechat_image(wechat_image_bytes)
                    else:
                        wechat_success = self.notifier.send_to_wechat(dashboard_content)

                # 其他渠道：發完整報告（避免自定義 Webhook 被 wechat 截斷邏輯汙染）
                non_wechat_success = False
                stock_email_groups = getattr(self.config, 'stock_email_groups', []) or []
                for channel in channels:
                    if channel == NotificationChannel.WECHAT:
                        continue
                    if channel == NotificationChannel.FEISHU:
                        non_wechat_success = self.notifier.send_to_feishu(report) or non_wechat_success
                    elif channel == NotificationChannel.TELEGRAM:
                        use_image = self.notifier._should_use_image_for_channel(
                            channel, image_bytes
                        )
                        if use_image:
                            result = self.notifier._send_telegram_photo(image_bytes)
                        else:
                            result = self.notifier.send_to_telegram(report)
                        non_wechat_success = result or non_wechat_success
                    elif channel == NotificationChannel.EMAIL:
                        if stock_email_groups:
                            code_to_emails: Dict[str, Optional[List[str]]] = {}
                            for r in results:
                                if r.code not in code_to_emails:
                                    emails = []
                                    for stocks, emails_list in stock_email_groups:
                                        if r.code in stocks:
                                            emails.extend(emails_list)
                                    code_to_emails[r.code] = list(dict.fromkeys(emails)) if emails else None
                            emails_to_results: Dict[Optional[Tuple], List] = defaultdict(list)
                            for r in results:
                                recs = code_to_emails.get(r.code)
                                key = tuple(recs) if recs else None
                                emails_to_results[key].append(r)
                            for key, group_results in emails_to_results.items():
                                grp_report = self._generate_aggregate_report(group_results, report_type)
                                grp_image_bytes = None
                                if channel.value in self.notifier._markdown_to_image_channels:
                                    grp_image_bytes = markdown_to_image(
                                        grp_report,
                                        max_chars=self.notifier._markdown_to_image_max_chars,
                                    )
                                use_image = self.notifier._should_use_image_for_channel(
                                    channel, grp_image_bytes
                                )
                                receivers = list(key) if key is not None else None
                                if use_image:
                                    result = self.notifier._send_email_with_inline_image(
                                        grp_image_bytes, receivers=receivers
                                    )
                                else:
                                    result = self.notifier.send_to_email(
                                        grp_report, receivers=receivers
                                    )
                                non_wechat_success = result or non_wechat_success
                        else:
                            use_image = self.notifier._should_use_image_for_channel(
                                channel, image_bytes
                            )
                            if use_image:
                                result = self.notifier._send_email_with_inline_image(image_bytes)
                            else:
                                result = self.notifier.send_to_email(report)
                            non_wechat_success = result or non_wechat_success
                    elif channel == NotificationChannel.CUSTOM:
                        use_image = self.notifier._should_use_image_for_channel(
                            channel, image_bytes
                        )
                        if use_image:
                            result = self.notifier._send_custom_webhook_image(
                                image_bytes, fallback_content=report
                            )
                        else:
                            result = self.notifier.send_to_custom(report)
                        non_wechat_success = result or non_wechat_success
                    elif channel == NotificationChannel.PUSHPLUS:
                        non_wechat_success = self.notifier.send_to_pushplus(report) or non_wechat_success
                    elif channel == NotificationChannel.SERVERCHAN3:
                        non_wechat_success = self.notifier.send_to_serverchan3(report) or non_wechat_success
                    elif channel == NotificationChannel.DISCORD:
                        non_wechat_success = self.notifier.send_to_discord(report) or non_wechat_success
                    elif channel == NotificationChannel.PUSHOVER:
                        non_wechat_success = self.notifier.send_to_pushover(report) or non_wechat_success
                    elif channel == NotificationChannel.ASTRBOT:
                        non_wechat_success = self.notifier.send_to_astrbot(report) or non_wechat_success
                    else:
                        logger.warning(f"未知通知渠道: {channel}")

                success = wechat_success or non_wechat_success or context_success
                if success:
                    logger.info("決策儀表盤推送成功")
                else:
                    logger.warning("決策儀表盤推送失敗")
            else:
                logger.info("通知渠道未配置，跳過推送")
                
        except Exception as e:
            import traceback
            logger.error(f"傳送通知失敗: {e}\n{traceback.format_exc()}")

    def _generate_aggregate_report(
        self,
        results: List[AnalysisResult],
        report_type: ReportType,
    ) -> str:
        """Generate aggregate report with backward-compatible notifier fallback."""
        generator = getattr(self.notifier, "generate_aggregate_report", None)
        if callable(generator):
            return generator(results, report_type)
        if report_type == ReportType.BRIEF and hasattr(self.notifier, "generate_brief_report"):
            return self.notifier.generate_brief_report(results)
        return self.notifier.generate_dashboard_report(results)
