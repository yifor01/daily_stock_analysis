# -*- coding: utf-8 -*-
"""
===================================
分析服務層
===================================

職責：
1. 封裝股票分析邏輯
2. 呼叫 analyzer 和 pipeline 執行分析
3. 儲存分析結果到資料庫
"""

import logging
import uuid
from typing import Optional, Dict, Any

from src.repositories.analysis_repo import AnalysisRepository

logger = logging.getLogger(__name__)


class AnalysisService:
    """
    分析服務
    
    封裝股票分析相關的業務邏輯
    """
    
    def __init__(self):
        """初始化分析服務"""
        self.repo = AnalysisRepository()
    
    def analyze_stock(
        self,
        stock_code: str,
        report_type: str = "detailed",
        force_refresh: bool = False,
        query_id: Optional[str] = None,
        send_notification: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        執行股票分析
        
        Args:
            stock_code: 股票程式碼
            report_type: 報告型別 (simple/detailed)
            force_refresh: 是否強制重新整理
            query_id: 查詢 ID（可選）
            send_notification: 是否傳送通知（API 觸發預設傳送）
            
        Returns:
            分析結果字典，包含:
            - stock_code: 股票程式碼
            - stock_name: 股票名稱
            - report: 分析報告
        """
        try:
            # 匯入分析相關模組
            from src.config import get_config
            from src.core.pipeline import StockAnalysisPipeline
            from src.enums import ReportType
            
            # 生成 query_id
            if query_id is None:
                query_id = uuid.uuid4().hex
            
            # 獲取配置
            config = get_config()
            
            # 建立分析流水線
            pipeline = StockAnalysisPipeline(
                config=config,
                query_id=query_id,
                query_source="api"
            )
            
            # 確定報告型別 (API: simple/detailed/full/brief -> ReportType)
            rt = ReportType.from_str(report_type)
            
            # 執行分析
            result = pipeline.process_single_stock(
                code=stock_code,
                skip_analysis=False,
                single_stock_notify=send_notification,
                report_type=rt
            )
            
            if result is None:
                logger.warning(f"分析股票 {stock_code} 返回空結果")
                return None
            
            # 構建響應
            return self._build_analysis_response(result, query_id, report_type=rt.value)
            
        except Exception as e:
            logger.error(f"分析股票 {stock_code} 失敗: {e}", exc_info=True)
            return None
    
    def _build_analysis_response(
        self, 
        result: Any, 
        query_id: str,
        report_type: str = "detailed",
    ) -> Dict[str, Any]:
        """
        構建分析響應
        
        Args:
            result: AnalysisResult 物件
            query_id: 查詢 ID
            report_type: 歸一化後的報告型別
            
        Returns:
            格式化的響應字典
        """
        # 獲取狙擊點位
        sniper_points = {}
        if hasattr(result, 'get_sniper_points'):
            sniper_points = result.get_sniper_points() or {}
        
        # 計算情緒標籤
        sentiment_label = self._get_sentiment_label(result.sentiment_score)
        
        # 構建報告結構
        report = {
            "meta": {
                "query_id": query_id,
                "stock_code": result.code,
                "stock_name": result.name,
                "report_type": report_type,
                "current_price": result.current_price,
                "change_pct": result.change_pct,
                "model_used": getattr(result, "model_used", None),
            },
            "summary": {
                "analysis_summary": result.analysis_summary,
                "operation_advice": result.operation_advice,
                "trend_prediction": result.trend_prediction,
                "sentiment_score": result.sentiment_score,
                "sentiment_label": sentiment_label,
            },
            "strategy": {
                "ideal_buy": sniper_points.get("ideal_buy"),
                "secondary_buy": sniper_points.get("secondary_buy"),
                "stop_loss": sniper_points.get("stop_loss"),
                "take_profit": sniper_points.get("take_profit"),
            },
            "details": {
                "news_summary": result.news_summary,
                "technical_analysis": result.technical_analysis,
                "fundamental_analysis": result.fundamental_analysis,
                "risk_warning": result.risk_warning,
            }
        }
        
        return {
            "stock_code": result.code,
            "stock_name": result.name,
            "report": report,
        }
    
    def _get_sentiment_label(self, score: int) -> str:
        """
        根據評分獲取情緒標籤
        
        Args:
            score: 情緒評分 (0-100)
            
        Returns:
            情緒標籤
        """
        if score >= 80:
            return "極度樂觀"
        elif score >= 60:
            return "樂觀"
        elif score >= 40:
            return "中性"
        elif score >= 20:
            return "悲觀"
        else:
            return "極度悲觀"
