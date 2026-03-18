# -*- coding: utf-8 -*-
"""
===================================
API v1 Endpoints 模組初始化
===================================

職責：
1. 宣告所有 endpoint 路由模組
"""

from api.v1.endpoints import (
    health,
    analysis,
    history,
    stocks,
    backtest,
    system_config,
    auth,
    agent,
    usage,
    portfolio,
)
__all__ = [
    "health",
    "analysis",
    "history",
    "stocks",
    "backtest",
    "system_config",
    "auth",
    "agent",
    "usage",
    "portfolio",
]
