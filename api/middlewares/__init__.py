# -*- coding: utf-8 -*-
"""
===================================
API 中介軟體模組初始化
===================================

職責：
1. 匯出所有中介軟體
"""

from api.middlewares.error_handler import ErrorHandlerMiddleware

__all__ = ["ErrorHandlerMiddleware"]
