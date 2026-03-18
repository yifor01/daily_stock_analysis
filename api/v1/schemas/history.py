# -*- coding: utf-8 -*-
"""
===================================
歷史記錄相關模型
===================================

職責：
1. 定義歷史記錄列表和詳情模型
2. 定義分析報告完整模型
"""

from typing import Optional, List, Any

from pydantic import BaseModel, ConfigDict, Field


class HistoryItem(BaseModel):
    """歷史記錄摘要（列表展示用）"""

    id: Optional[int] = Field(None, description="分析歷史記錄主鍵 ID")
    query_id: str = Field(..., description="分析記錄關聯 query_id（批次分析時重複）")
    stock_code: str = Field(..., description="股票程式碼")
    stock_name: Optional[str] = Field(None, description="股票名稱")
    report_type: Optional[str] = Field(None, description="報告型別")
    sentiment_score: Optional[int] = Field(
        None, 
        description="情緒評分 (0-100)",
        ge=0,
        le=100
    )
    operation_advice: Optional[str] = Field(None, description="操作建議")
    created_at: Optional[str] = Field(None, description="建立時間")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": 1234,
                "query_id": "abc123",
                "stock_code": "600519",
                "stock_name": "貴州茅臺",
                "report_type": "detailed",
                "sentiment_score": 75,
                "operation_advice": "持有",
                "created_at": "2024-01-01T12:00:00"
            }
        }


class HistoryListResponse(BaseModel):
    """歷史記錄列表響應"""
    
    total: int = Field(..., description="總記錄數")
    page: int = Field(..., description="當前頁碼")
    limit: int = Field(..., description="每頁數量")
    items: List[HistoryItem] = Field(default_factory=list, description="記錄列表")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total": 100,
                "page": 1,
                "limit": 20,
                "items": []
            }
        }


class DeleteHistoryRequest(BaseModel):
    """刪除歷史記錄請求"""

    record_ids: List[int] = Field(default_factory=list, description="要刪除的歷史記錄主鍵 ID 列表")


class DeleteHistoryResponse(BaseModel):
    """刪除歷史記錄響應"""

    deleted: int = Field(..., description="實際刪除的歷史記錄數量")


class NewsIntelItem(BaseModel):
    """新聞情報條目"""

    title: str = Field(..., description="新聞標題")
    snippet: str = Field("", description="新聞摘要（最多200字）")
    url: str = Field(..., description="新聞連結")

    class Config:
        json_schema_extra = {
            "example": {
                "title": "公司釋出業績快報，營收同比增長 20%",
                "snippet": "公司公告顯示，季度營收同比增長 20%...",
                "url": "https://example.com/news/123"
            }
        }


class NewsIntelResponse(BaseModel):
    """新聞情報響應"""

    total: int = Field(..., description="新聞條數")
    items: List[NewsIntelItem] = Field(default_factory=list, description="新聞列表")

    class Config:
        json_schema_extra = {
            "example": {
                "total": 2,
                "items": []
            }
        }


class ReportMeta(BaseModel):
    """報告元資訊"""

    model_config = ConfigDict(protected_namespaces=("model_validate", "model_dump"))

    id: Optional[int] = Field(None, description="分析歷史記錄主鍵 ID（僅歷史報告有此欄位）")
    query_id: str = Field(..., description="分析記錄關聯 query_id（批次分析時重複）")
    stock_code: str = Field(..., description="股票程式碼")
    stock_name: Optional[str] = Field(None, description="股票名稱")
    report_type: Optional[str] = Field(None, description="報告型別")
    created_at: Optional[str] = Field(None, description="建立時間")
    current_price: Optional[float] = Field(None, description="分析時股價")
    change_pct: Optional[float] = Field(None, description="分析時漲跌幅(%)")
    model_used: Optional[str] = Field(None, description="分析使用的 LLM 模型")


class ReportSummary(BaseModel):
    """報告概覽區"""
    
    analysis_summary: Optional[str] = Field(None, description="關鍵結論")
    operation_advice: Optional[str] = Field(None, description="操作建議")
    trend_prediction: Optional[str] = Field(None, description="趨勢預測")
    sentiment_score: Optional[int] = Field(
        None, 
        description="情緒評分 (0-100)",
        ge=0,
        le=100
    )
    sentiment_label: Optional[str] = Field(None, description="情緒標籤")


class ReportStrategy(BaseModel):
    """策略點位區"""
    
    ideal_buy: Optional[str] = Field(None, description="理想買入價")
    secondary_buy: Optional[str] = Field(None, description="第二買入價")
    stop_loss: Optional[str] = Field(None, description="止損價")
    take_profit: Optional[str] = Field(None, description="止盈價")


class ReportDetails(BaseModel):
    """報告詳情區"""
    
    news_content: Optional[str] = Field(None, description="新聞摘要")
    raw_result: Optional[Any] = Field(None, description="原始分析結果（JSON）")
    context_snapshot: Optional[Any] = Field(None, description="分析時上下文快照（JSON）")
    financial_report: Optional[Any] = Field(None, description="結構化財報摘要（來自 fundamental_context）")
    dividend_metrics: Optional[Any] = Field(None, description="結構化分紅指標（含 TTM 口徑）")


class AnalysisReport(BaseModel):
    """完整分析報告"""

    meta: ReportMeta = Field(..., description="元資訊")
    summary: ReportSummary = Field(..., description="概覽區")
    strategy: Optional[ReportStrategy] = Field(None, description="策略點位區")
    details: Optional[ReportDetails] = Field(None, description="詳情區")

    class Config:
        json_schema_extra = {
            "example": {
                "meta": {
                    "query_id": "abc123",
                    "stock_code": "600519",
                    "stock_name": "貴州茅臺",
                    "report_type": "detailed",
                    "created_at": "2024-01-01T12:00:00"
                },
                "summary": {
                    "analysis_summary": "技術面向好，建議持有",
                    "operation_advice": "持有",
                    "trend_prediction": "看多",
                    "sentiment_score": 75,
                    "sentiment_label": "樂觀"
                },
                "strategy": {
                    "ideal_buy": "1800.00",
                    "secondary_buy": "1750.00",
                    "stop_loss": "1700.00",
                    "take_profit": "2000.00"
                },
                "details": None
            }
        }


class MarkdownReportResponse(BaseModel):
    """Markdown 格式報告響應"""

    content: str = Field(..., description="Markdown 格式的完整報告內容")

    class Config:
        json_schema_extra = {
            "example": {
                "content": "# 📊 貴州茅臺 (600519) 分析報告\n\n> 分析日期：**2024-01-01**\n\n..."
            }
        }
