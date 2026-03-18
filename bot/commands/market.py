# -*- coding: utf-8 -*-
"""
===================================
大盤覆盤命令
===================================

執行大盤覆盤分析，生成市場概覽報告。
"""

import logging
import threading
from typing import List

from bot.commands.base import BotCommand
from bot.models import BotMessage, BotResponse

logger = logging.getLogger(__name__)


class MarketCommand(BotCommand):
    """
    大盤覆盤命令
    
    執行大盤覆盤分析，包括：
    - 主要指數表現
    - 板塊熱點
    - 市場情緒
    - 後市展望
    
    用法：
        /market - 執行大盤覆盤
    """

    @property
    def name(self) -> str:
        return "market"

    @property
    def aliases(self) -> List[str]:
        return ["m", "大盤", "覆盤", "行情"]

    @property
    def description(self) -> str:
        return "大盤覆盤分析"

    @property
    def usage(self) -> str:
        return "/market"

    def execute(self, message: BotMessage, args: List[str]) -> BotResponse:
        """執行大盤覆盤命令"""
        logger.info(f"[MarketCommand] 開始大盤覆盤分析")

        # 在後臺執行緒中執行復盤（避免阻塞）
        thread = threading.Thread(
            target=self._run_market_review,
            args=(message,),
            daemon=True
        )
        thread.start()

        return BotResponse.markdown_response(
            "✅ **大盤覆盤任務已啟動**\n\n"
            "正在分析：\n"
            "• 主要指數表現\n"
            "• 板塊熱點分析\n"
            "• 市場情緒判斷\n"
            "• 後市展望\n\n"
            "分析完成後將自動推送結果。"
        )

    def _run_market_review(self, message: BotMessage) -> None:
        """後臺執行大盤覆盤"""
        try:
            from src.config import get_config
            from src.notification import NotificationService
            from src.market_analyzer import MarketAnalyzer
            from src.search_service import SearchService
            from src.analyzer import GeminiAnalyzer

            config = get_config()
            notifier = NotificationService(source_message=message)

            # 初始化搜尋服務
            search_service = None
            if config.bocha_api_keys or config.tavily_api_keys or config.brave_api_keys or config.serpapi_keys or config.minimax_api_keys or config.searxng_base_urls:
                search_service = SearchService(
                    bocha_keys=config.bocha_api_keys,
                    tavily_keys=config.tavily_api_keys,
                    brave_keys=config.brave_api_keys,
                    serpapi_keys=config.serpapi_keys,
                    minimax_keys=config.minimax_api_keys,
                    searxng_base_urls=config.searxng_base_urls,
                    news_max_age_days=config.news_max_age_days,
                )

            # 初始化 AI 分析器
            analyzer = None
            if config.gemini_api_key or config.openai_api_key:
                analyzer = GeminiAnalyzer()

            # 讀取配置中的市場區域，與定時任務/CLI 保持一致
            region = getattr(config, 'market_review_region', 'cn')

            # 執行復盤
            market_analyzer = MarketAnalyzer(
                search_service=search_service,
                analyzer=analyzer,
                region=region,
            )

            review_report = market_analyzer.run_daily_review()

            if review_report:
                # 推送結果
                report_content = f"🎯 **大盤覆盤**\n\n{review_report}"
                notifier.send(report_content, email_send_to_all=True)
                logger.info("[MarketCommand] 大盤覆盤完成並已推送")
            else:
                logger.warning("[MarketCommand] 大盤覆盤返回空結果")

        except Exception as e:
            logger.error(f"[MarketCommand] 大盤覆盤失敗: {e}")
            logger.exception(e)
