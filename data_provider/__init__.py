# -*- coding: utf-8 -*-
"""
===================================
資料來源策略層 - 包初始化
===================================

本包實現策略模式管理多個資料來源，實現：
1. 統一的資料獲取介面
2. 自動故障切換
3. 防封禁流控策略

資料來源優先順序（動態調整）：
【配置了 TUSHARE_TOKEN 時】
1. TushareFetcher (Priority 0) - 🔥 最高優先順序（動態提升）
2. EfinanceFetcher (Priority 0) - 同優先順序
3. AkshareFetcher (Priority 1) - 來自 akshare 庫
4. PytdxFetcher (Priority 2) - 來自 pytdx 庫（通達信）
5. BaostockFetcher (Priority 3) - 來自 baostock 庫
6. YfinanceFetcher (Priority 4) - 來自 yfinance 庫

【未配置 TUSHARE_TOKEN 時】
1. EfinanceFetcher (Priority 0) - 最高優先順序，來自 efinance 庫
2. AkshareFetcher (Priority 1) - 來自 akshare 庫
3. PytdxFetcher (Priority 2) - 來自 pytdx 庫（通達信）
4. TushareFetcher (Priority 2) - 來自 tushare 庫（不可用）
5. BaostockFetcher (Priority 3) - 來自 baostock 庫
6. YfinanceFetcher (Priority 4) - 來自 yfinance 庫

提示：優先順序數字越小越優先，同優先順序按初始化順序排列
"""

from .base import BaseFetcher, DataFetcherManager
from .efinance_fetcher import EfinanceFetcher
from .akshare_fetcher import AkshareFetcher, is_hk_stock_code
from .tushare_fetcher import TushareFetcher
from .pytdx_fetcher import PytdxFetcher
from .baostock_fetcher import BaostockFetcher
from .yfinance_fetcher import YfinanceFetcher
from .us_index_mapping import is_us_index_code, is_us_stock_code, get_us_index_yf_symbol, US_INDEX_MAPPING

__all__ = [
    'BaseFetcher',
    'DataFetcherManager',
    'EfinanceFetcher',
    'AkshareFetcher',
    'TushareFetcher',
    'PytdxFetcher',
    'BaostockFetcher',
    'YfinanceFetcher',
    'is_us_index_code',
    'is_us_stock_code',
    'is_hk_stock_code',
    'get_us_index_yf_symbol',
    'US_INDEX_MAPPING',
]
