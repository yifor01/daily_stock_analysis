# -*- coding: utf-8 -*-
"""
===================================
通用響應模型
===================================

職責：
1. 定義通用的響應模型（HealthResponse, ErrorResponse 等）
2. 提供統一的響應格式
"""

from typing import Optional, Any

from pydantic import BaseModel, Field


class RootResponse(BaseModel):
    """API 根路由響應"""
    
    message: str = Field(..., description="API 執行狀態訊息", example="Daily Stock Analysis API is running")
    version: Optional[str] = Field(None, description="API 版本", example="1.0.0")
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "Daily Stock Analysis API is running",
                "version": "1.0.0"
            }
        }


class HealthResponse(BaseModel):
    """健康檢查響應"""
    
    status: str = Field(..., description="服務狀態", example="ok")
    timestamp: Optional[str] = Field(None, description="時間戳")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "ok",
                "timestamp": "2024-01-01T12:00:00"
            }
        }


class ErrorResponse(BaseModel):
    """錯誤響應"""
    
    error: str = Field(..., description="錯誤型別", example="validation_error")
    message: str = Field(..., description="錯誤詳情", example="請求引數錯誤")
    detail: Optional[Any] = Field(None, description="附加錯誤資訊")
    
    class Config:
        json_schema_extra = {
            "example": {
                "error": "not_found",
                "message": "資源不存在",
                "detail": None
            }
        }


class SuccessResponse(BaseModel):
    """通用成功響應"""
    
    success: bool = Field(True, description="是否成功")
    message: Optional[str] = Field(None, description="成功訊息")
    data: Optional[Any] = Field(None, description="響應資料")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "操作成功",
                "data": None
            }
        }
