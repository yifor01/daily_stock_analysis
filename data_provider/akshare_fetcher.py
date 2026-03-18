# -*- coding: utf-8 -*-
"""
===================================
AkshareFetcher - 主資料來源 (Priority 1)
===================================

資料來源：
1. 東方財富爬蟲（透過 akshare 庫） - 預設資料來源
2. 新浪財經介面 - 備選資料來源
3. 騰訊財經介面 - 備選資料來源

特點：免費、無需 Token、資料全面
風險：爬蟲機制易被反爬封禁

防封禁策略：
1. 每次請求前隨機休眠 2-5 秒
2. 隨機輪換 User-Agent
3. 使用 tenacity 實現指數退避重試
4. 熔斷器機制：連續失敗後自動冷卻

增強資料：
- 實時行情：量比、換手率、市盈率、市淨率、總市值、流通市值
- 籌碼分佈：獲利比例、平均成本、籌碼集中度
"""

import logging
import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

import pandas as pd
import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from patch.eastmoney_patch import eastmoney_patch
from src.config import get_config
from .base import BaseFetcher, DataFetchError, RateLimitError, STANDARD_COLUMNS, is_bse_code, is_st_stock, is_kc_cy_stock, normalize_stock_code
from .realtime_types import (
    UnifiedRealtimeQuote, ChipDistribution, RealtimeSource,
    get_realtime_circuit_breaker, get_chip_circuit_breaker,
    safe_float, safe_int  # 使用統一的型別轉換函式
)
from .us_index_mapping import is_us_index_code, is_us_stock_code


# 保留舊的 RealtimeQuote 別名，用於向後相容
RealtimeQuote = UnifiedRealtimeQuote


logger = logging.getLogger(__name__)

SINA_REALTIME_ENDPOINT = "hq.sinajs.cn/list"
TENCENT_REALTIME_ENDPOINT = "qt.gtimg.cn/q"


# User-Agent 池，用於隨機輪換
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]


# 快取實時行情資料（避免重複請求）
# TTL 設為 20 分鐘 (1200秒)：
# - 批次分析場景：通常 30 只股票在 5 分鐘內分析完，20 分鐘足夠覆蓋
# - 實時性要求：股票分析不需要秒級實時資料，20 分鐘延遲可接受
# - 防封禁：減少 API 呼叫頻率
_realtime_cache: Dict[str, Any] = {
    'data': None,
    'timestamp': 0,
    'ttl': 1200  # 20分鐘快取有效期
}

# ETF 實時行情快取
_etf_realtime_cache: Dict[str, Any] = {
    'data': None,
    'timestamp': 0,
    'ttl': 1200  # 20分鐘快取有效期
}


def _is_etf_code(stock_code: str) -> bool:
    """
    判斷程式碼是否為 ETF 基金
    
    ETF 程式碼規則：
    - 上交所 ETF: 51xxxx, 52xxxx, 56xxxx, 58xxxx
    - 深交所 ETF: 15xxxx, 16xxxx, 18xxxx
    
    Args:
        stock_code: 股票/基金程式碼
        
    Returns:
        True 表示是 ETF 程式碼，False 表示是普通股票程式碼
    """
    etf_prefixes = ('51', '52', '56', '58', '15', '16', '18')
    code = stock_code.strip().split('.')[0]
    return code.startswith(etf_prefixes) and len(code) == 6


def _is_hk_code(stock_code: str) -> bool:
    """
    判斷程式碼是否為港股

    港股程式碼規則：
    - 5位數字程式碼，如 '00700' (騰訊控股)
    - 部分港股程式碼可能帶有字首，如 'hk00700', 'hk1810'

    Args:
        stock_code: 股票程式碼

    Returns:
        True 表示是港股程式碼，False 表示不是港股程式碼
    """
    # 去除可能的 'hk' 字首並檢查是否為純數字
    code = stock_code.strip().lower()
    if code.endswith('.hk'):
        numeric_part = code[:-3]
        return numeric_part.isdigit() and 1 <= len(numeric_part) <= 5
    if code.startswith('hk'):
        # 帶 hk 字首的一定是港股，去掉字首後應為純數字（1-5位）
        numeric_part = code[2:]
        return numeric_part.isdigit() and 1 <= len(numeric_part) <= 5
    # 無字首時，5位純數字才視為港股（避免誤判 A 股程式碼）
    return code.isdigit() and len(code) == 5


def is_hk_stock_code(stock_code: str) -> bool:
    """
    Public API: determine if a stock code is a Hong Kong stock.

    Delegates to _is_hk_code for internal compatibility.

    Args:
        stock_code: Stock code (e.g. '00700', 'hk00700')

    Returns:
        True if HK stock, False otherwise
    """
    return _is_hk_code(stock_code)


def _is_us_code(stock_code: str) -> bool:
    """
    判斷程式碼是否為美股股票（不包括美股指數）。

    委託給 us_index_mapping 模組的 is_us_stock_code()。

    Args:
        stock_code: 股票程式碼

    Returns:
        True 表示是美股程式碼，False 表示不是美股程式碼

    Examples:
        >>> _is_us_code('AAPL')
        True
        >>> _is_us_code('TSLA')
        True
        >>> _is_us_code('SPX')
        False
        >>> _is_us_code('600519')
        False
    """
    return is_us_stock_code(stock_code)


def _to_sina_tx_symbol(stock_code: str) -> str:
    """Convert 6-digit A-share code to sh/sz/bj prefixed symbol for Sina/Tencent APIs."""
    base = (stock_code.strip().split(".")[0] if "." in stock_code else stock_code).strip()
    if is_bse_code(base):
        return f"bj{base}"
    # Shanghai: 60xxxx, 5xxxx (ETF), 90xxxx (B-shares)
    if base.startswith(("6", "5", "90")):
        return f"sh{base}"
    return f"sz{base}"


def _classify_realtime_http_error(exc: Exception) -> Tuple[str, str]:
    """
    Classify Sina/Tencent realtime quote failures into stable categories.
    """
    detail = str(exc).strip() or type(exc).__name__
    lowered = detail.lower()

    remote_disconnect_keywords = (
        "remotedisconnected",
        "remote end closed connection without response",
        "connection aborted",
        "connection broken",
        "protocolerror",
        "chunkedencodingerror",
    )
    timeout_keywords = (
        "timeout",
        "timed out",
        "readtimeout",
        "connecttimeout",
    )
    rate_limit_keywords = (
        "banned",
        "blocked",
        "頻率",
        "rate limit",
        "too many requests",
        "429",
        "限制",
        "forbidden",
        "403",
    )

    if any(keyword in lowered for keyword in remote_disconnect_keywords):
        return "remote_disconnect", detail
    if isinstance(exc, (TimeoutError, requests.exceptions.Timeout)) or any(
        keyword in lowered for keyword in timeout_keywords
    ):
        return "timeout", detail
    if any(keyword in lowered for keyword in rate_limit_keywords):
        return "rate_limit_or_anti_bot", detail
    if isinstance(exc, requests.exceptions.RequestException):
        return "request_error", detail
    return "unknown_request_error", detail


def _build_realtime_failure_message(
    source_name: str,
    endpoint: str,
    stock_code: str,
    symbol: str,
    category: str,
    detail: str,
    elapsed: float,
    error_type: str,
) -> str:
    return (
        f"{source_name} 實時行情介面失敗: endpoint={endpoint}, stock_code={stock_code}, "
        f"symbol={symbol}, category={category}, error_type={error_type}, "
        f"elapsed={elapsed:.2f}s, detail={detail}"
    )


class AkshareFetcher(BaseFetcher):
    """
    Akshare 資料來源實現
    
    優先順序：1（最高）
    資料來源：東方財富網爬蟲
    
    關鍵策略：
    - 每次請求前隨機休眠 2.0-5.0 秒
    - 隨機 User-Agent 輪換
    - 失敗後指數退避重試（最多3次）
    """
    
    name = "AkshareFetcher"
    priority = int(os.getenv("AKSHARE_PRIORITY", "1"))
    
    def __init__(self, sleep_min: float = 2.0, sleep_max: float = 5.0):
        """
        初始化 AkshareFetcher
        
        Args:
            sleep_min: 最小休眠時間（秒）
            sleep_max: 最大休眠時間（秒）
        """
        self.sleep_min = sleep_min
        self.sleep_max = sleep_max
        self._last_request_time: Optional[float] = None
        # 東財補丁開啟才執行打補丁操作
        if get_config().enable_eastmoney_patch:
            eastmoney_patch()
    
    def _set_random_user_agent(self) -> None:
        """
        設定隨機 User-Agent
        
        透過修改 requests Session 的 headers 實現
        這是關鍵的反爬策略之一
        """
        try:
            import akshare as ak
            # akshare 內部使用 requests，我們透過環境變數或直接設定來影響
            # 實際上 akshare 可能不直接暴露 session，這裡透過 fake_useragent 作為補充
            random_ua = random.choice(USER_AGENTS)
            logger.debug(f"設定 User-Agent: {random_ua[:50]}...")
        except Exception as e:
            logger.debug(f"設定 User-Agent 失敗: {e}")
    
    def _enforce_rate_limit(self) -> None:
        """
        強制執行速率限制
        
        策略：
        1. 檢查距離上次請求的時間間隔
        2. 如果間隔不足，補充休眠時間
        3. 然後再執行隨機 jitter 休眠
        """
        if self._last_request_time is not None:
            elapsed = time.time() - self._last_request_time
            min_interval = self.sleep_min
            if elapsed < min_interval:
                additional_sleep = min_interval - elapsed
                logger.debug(f"補充休眠 {additional_sleep:.2f} 秒")
                time.sleep(additional_sleep)
        
        # 執行隨機 jitter 休眠
        self.random_sleep(self.sleep_min, self.sleep_max)
        self._last_request_time = time.time()
    
    @retry(
        stop=stop_after_attempt(3),  # 最多重試3次
        wait=wait_exponential(multiplier=1, min=2, max=30),  # 指數退避：2, 4, 8... 最大30秒
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        從 Akshare 獲取原始資料
        
        根據程式碼型別自動選擇 API：
        - 美股：不支援，丟擲異常由 YfinanceFetcher 處理（Issue #311）
        - 港股：使用 ak.stock_hk_hist()
        - ETF 基金：使用 ak.fund_etf_hist_em()
        - 普通 A 股：使用 ak.stock_zh_a_hist()
        
        流程：
        1. 判斷程式碼型別（美股/港股/ETF/A股）
        2. 設定隨機 User-Agent
        3. 執行速率限制（隨機休眠）
        4. 呼叫對應的 akshare API
        5. 處理返回資料
        """
        # 根據程式碼型別選擇不同的獲取方法
        if _is_us_code(stock_code):
            # 美股：akshare 的 stock_us_daily 介面復權存在已知問題（參見 Issue #311）
            # 交由 YfinanceFetcher 處理，確保復權價格一致
            raise DataFetchError(
                f"AkshareFetcher 不支援美股 {stock_code}，請使用 YfinanceFetcher 獲取正確的復權價格"
            )
        elif _is_hk_code(stock_code):
            return self._fetch_hk_data(stock_code, start_date, end_date)
        elif _is_etf_code(stock_code):
            return self._fetch_etf_data(stock_code, start_date, end_date)
        else:
            return self._fetch_stock_data(stock_code, start_date, end_date)
    
    def _fetch_stock_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        獲取普通 A 股歷史資料

        策略：
        1. 優先嚐試東方財富介面 (ak.stock_zh_a_hist)
        2. 失敗後嘗試新浪財經介面 (ak.stock_zh_a_daily)
        3. 最後嘗試騰訊財經介面 (ak.stock_zh_a_hist_tx)
        """
        # 嘗試列表
        methods = [
            (self._fetch_stock_data_em, "東方財富"),
            (self._fetch_stock_data_sina, "新浪財經"),
            (self._fetch_stock_data_tx, "騰訊財經"),
        ]

        last_error = None

        for fetch_method, source_name in methods:
            try:
                logger.info(f"[資料來源] 嘗試使用 {source_name} 獲取 {stock_code}...")
                df = fetch_method(stock_code, start_date, end_date)

                if df is not None and not df.empty:
                    logger.info(f"[資料來源] {source_name} 獲取成功")
                    return df
            except Exception as e:
                last_error = e
                logger.warning(f"[資料來源] {source_name} 獲取失敗: {e}")
                # 繼續嘗試下一個

        # 所有都失敗
        raise DataFetchError(f"Akshare 所有渠道獲取失敗: {last_error}")

    def _fetch_stock_data_em(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        獲取普通 A 股歷史資料 (東方財富)
        資料來源：ak.stock_zh_a_hist()
        """
        import akshare as ak

        # 防封禁策略 1: 隨機 User-Agent
        self._set_random_user_agent()

        # 防封禁策略 2: 強制休眠
        self._enforce_rate_limit()

        logger.info(f"[API呼叫] ak.stock_zh_a_hist(symbol={stock_code}, ...)")

        try:
            import time as _time
            api_start = _time.time()

            df = ak.stock_zh_a_hist(
                symbol=stock_code,
                period="daily",
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq"
            )

            api_elapsed = _time.time() - api_start

            if df is not None and not df.empty:
                logger.info(f"[API返回] ak.stock_zh_a_hist 成功: {len(df)} 行, 耗時 {api_elapsed:.2f}s")
                return df
            else:
                logger.warning(f"[API返回] ak.stock_zh_a_hist 返回空資料")
                return pd.DataFrame()

        except Exception as e:
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in ['banned', 'blocked', '頻率', 'rate', '限制']):
                raise RateLimitError(f"Akshare(EM) 可能被限流: {e}") from e
            raise e

    def _fetch_stock_data_sina(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        獲取普通 A 股歷史資料 (新浪財經)
        資料來源：ak.stock_zh_a_daily()
        """
        import akshare as ak

        # 轉換程式碼格式：sh600000, sz000001, bj920748
        symbol = _to_sina_tx_symbol(stock_code)

        self._enforce_rate_limit()

        try:
            df = ak.stock_zh_a_daily(
                symbol=symbol,
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq"
            )

            # 標準化新浪資料列名
            # 新浪返回：date, open, high, low, close, volume, amount, outstanding_share, turnover
            if df is not None and not df.empty:
                # 確保日期列存在
                if 'date' in df.columns:
                    df = df.rename(columns={'date': '日期'})

                # 對映其他列以匹配 _normalize_data 的期望
                # _normalize_data 期望：日期, 開盤, 收盤, 最高, 最低, 成交量, 成交額
                rename_map = {
                    'open': '開盤', 'high': '最高', 'low': '最低',
                    'close': '收盤', 'volume': '成交量', 'amount': '成交額'
                }
                df = df.rename(columns=rename_map)

                # 計算漲跌幅（新浪介面可能不返回）
                if '收盤' in df.columns:
                    df['漲跌幅'] = df['收盤'].pct_change() * 100
                    df['漲跌幅'] = df['漲跌幅'].fillna(0)

                return df
            return pd.DataFrame()

        except Exception as e:
            raise e

    def _fetch_stock_data_tx(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        獲取普通 A 股歷史資料 (騰訊財經)
        資料來源：ak.stock_zh_a_hist_tx()
        """
        import akshare as ak

        # 轉換程式碼格式：sh600000, sz000001, bj920748
        symbol = _to_sina_tx_symbol(stock_code)

        self._enforce_rate_limit()

        try:
            df = ak.stock_zh_a_hist_tx(
                symbol=symbol,
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq"
            )

            # 標準化騰訊資料列名
            # 騰訊返回：date, open, close, high, low, volume, amount
            if df is not None and not df.empty:
                rename_map = {
                    'date': '日期', 'open': '開盤', 'high': '最高',
                    'low': '最低', 'close': '收盤', 'volume': '成交量',
                    'amount': '成交額'
                }
                df = df.rename(columns=rename_map)

                # 騰訊資料通常包含 '漲跌幅'，如果沒有則計算
                if 'pct_chg' in df.columns:
                    df = df.rename(columns={'pct_chg': '漲跌幅'})
                elif '收盤' in df.columns:
                    df['漲跌幅'] = df['收盤'].pct_change() * 100
                    df['漲跌幅'] = df['漲跌幅'].fillna(0)

                return df
            return pd.DataFrame()

        except Exception as e:
            raise e
    
    def _fetch_etf_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        獲取 ETF 基金歷史資料
        
        資料來源：ak.fund_etf_hist_em()
        
        Args:
            stock_code: ETF 程式碼，如 '512400', '159883'
            start_date: 開始日期，格式 'YYYY-MM-DD'
            end_date: 結束日期，格式 'YYYY-MM-DD'
            
        Returns:
            ETF 歷史資料 DataFrame
        """
        import akshare as ak
        
        # 防封禁策略 1: 隨機 User-Agent
        self._set_random_user_agent()
        
        # 防封禁策略 2: 強制休眠
        self._enforce_rate_limit()
        
        logger.info(f"[API呼叫] ak.fund_etf_hist_em(symbol={stock_code}, period=daily, "
                   f"start_date={start_date.replace('-', '')}, end_date={end_date.replace('-', '')}, adjust=qfq)")
        
        try:
            import time as _time
            api_start = _time.time()
            
            # 呼叫 akshare 獲取 ETF 日線資料
            df = ak.fund_etf_hist_em(
                symbol=stock_code,
                period="daily",
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq"  # 前復權
            )
            
            api_elapsed = _time.time() - api_start
            
            # 記錄返回資料摘要
            if df is not None and not df.empty:
                logger.info(f"[API返回] ak.fund_etf_hist_em 成功: 返回 {len(df)} 行資料, 耗時 {api_elapsed:.2f}s")
                logger.info(f"[API返回] 列名: {list(df.columns)}")
                logger.info(f"[API返回] 日期範圍: {df['日期'].iloc[0]} ~ {df['日期'].iloc[-1]}")
                logger.debug(f"[API返回] 最新3條資料:\n{df.tail(3).to_string()}")
            else:
                logger.warning(f"[API返回] ak.fund_etf_hist_em 返回空資料, 耗時 {api_elapsed:.2f}s")
            
            return df
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # 檢測反爬封禁
            if any(keyword in error_msg for keyword in ['banned', 'blocked', '頻率', 'rate', '限制']):
                logger.warning(f"檢測到可能被封禁: {e}")
                raise RateLimitError(f"Akshare 可能被限流: {e}") from e
            
            raise DataFetchError(f"Akshare 獲取 ETF 資料失敗: {e}") from e
    
    def _fetch_us_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        獲取美股歷史資料
        
        資料來源：ak.stock_us_daily()（新浪財經介面）
        
        Args:
            stock_code: 美股程式碼，如 'AMD', 'AAPL', 'TSLA'
            start_date: 開始日期，格式 'YYYY-MM-DD'
            end_date: 結束日期，格式 'YYYY-MM-DD'
            
        Returns:
            美股歷史資料 DataFrame
        """
        import akshare as ak
        
        # 防封禁策略 1: 隨機 User-Agent
        self._set_random_user_agent()
        
        # 防封禁策略 2: 強制休眠
        self._enforce_rate_limit()
        
        # 美股程式碼直接使用大寫
        symbol = stock_code.strip().upper()
        
        logger.info(f"[API呼叫] ak.stock_us_daily(symbol={symbol}, adjust=qfq)")
        
        try:
            import time as _time
            api_start = _time.time()
            
            # 呼叫 akshare 獲取美股日線資料
            # stock_us_daily 返回全部歷史資料，後續需要按日期過濾
            df = ak.stock_us_daily(
                symbol=symbol,
                adjust="qfq"  # 前復權
            )
            
            api_elapsed = _time.time() - api_start
            
            # 記錄返回資料摘要
            if df is not None and not df.empty:
                logger.info(f"[API返回] ak.stock_us_daily 成功: 返回 {len(df)} 行資料, 耗時 {api_elapsed:.2f}s")
                logger.info(f"[API返回] 列名: {list(df.columns)}")
                
                # 按日期過濾
                df['date'] = pd.to_datetime(df['date'])
                start_dt = pd.to_datetime(start_date)
                end_dt = pd.to_datetime(end_date)
                df = df[(df['date'] >= start_dt) & (df['date'] <= end_dt)]
                
                if not df.empty:
                    logger.info(f"[API返回] 過濾後日期範圍: {df['date'].iloc[0].strftime('%Y-%m-%d')} ~ {df['date'].iloc[-1].strftime('%Y-%m-%d')}")
                    logger.debug(f"[API返回] 最新3條資料:\n{df.tail(3).to_string()}")
                else:
                    logger.warning(f"[API返回] 過濾後資料為空，日期範圍 {start_date} ~ {end_date} 無資料")
                
                # 轉換列名為中文格式以匹配 _normalize_data
                # stock_us_daily 返回: date, open, high, low, close, volume
                rename_map = {
                    'date': '日期',
                    'open': '開盤',
                    'high': '最高',
                    'low': '最低',
                    'close': '收盤',
                    'volume': '成交量',
                }
                df = df.rename(columns=rename_map)
                
                # 計算漲跌幅（美股介面不直接返回）
                if '收盤' in df.columns:
                    df['漲跌幅'] = df['收盤'].pct_change() * 100
                    df['漲跌幅'] = df['漲跌幅'].fillna(0)
                
                # 估算成交額（美股介面不返回）
                if '成交量' in df.columns and '收盤' in df.columns:
                    df['成交額'] = df['成交量'] * df['收盤']
                else:
                    df['成交額'] = 0
                
                return df
            else:
                logger.warning(f"[API返回] ak.stock_us_daily 返回空資料, 耗時 {api_elapsed:.2f}s")
                return pd.DataFrame()
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # 檢測反爬封禁
            if any(keyword in error_msg for keyword in ['banned', 'blocked', '頻率', 'rate', '限制']):
                logger.warning(f"檢測到可能被封禁: {e}")
                raise RateLimitError(f"Akshare 可能被限流: {e}") from e
            
            raise DataFetchError(f"Akshare 獲取美股資料失敗: {e}") from e

    def _fetch_hk_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        獲取港股歷史資料
        
        資料來源：ak.stock_hk_hist()
        
        Args:
            stock_code: 港股程式碼，如 '00700', '01810'
            start_date: 開始日期，格式 'YYYY-MM-DD'
            end_date: 結束日期，格式 'YYYY-MM-DD'
            
        Returns:
            港股歷史資料 DataFrame
        """
        import akshare as ak
        
        # 防封禁策略 1: 隨機 User-Agent
        self._set_random_user_agent()
        
        # 防封禁策略 2: 強制休眠
        self._enforce_rate_limit()
        
        # 確保程式碼格式正確（5位數字）
        code = stock_code.lower().replace('hk', '').zfill(5)
        
        logger.info(f"[API呼叫] ak.stock_hk_hist(symbol={code}, period=daily, "
                   f"start_date={start_date.replace('-', '')}, end_date={end_date.replace('-', '')}, adjust=qfq)")
        
        try:
            import time as _time
            api_start = _time.time()
            
            # 呼叫 akshare 獲取港股日線資料
            df = ak.stock_hk_hist(
                symbol=code,
                period="daily",
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq"  # 前復權
            )
            
            api_elapsed = _time.time() - api_start
            
            # 記錄返回資料摘要
            if df is not None and not df.empty:
                logger.info(f"[API返回] ak.stock_hk_hist 成功: 返回 {len(df)} 行資料, 耗時 {api_elapsed:.2f}s")
                logger.info(f"[API返回] 列名: {list(df.columns)}")
                logger.info(f"[API返回] 日期範圍: {df['日期'].iloc[0]} ~ {df['日期'].iloc[-1]}")
                logger.debug(f"[API返回] 最新3條資料:\n{df.tail(3).to_string()}")
            else:
                logger.warning(f"[API返回] ak.stock_hk_hist 返回空資料, 耗時 {api_elapsed:.2f}s")
            
            return df
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # 檢測反爬封禁
            if any(keyword in error_msg for keyword in ['banned', 'blocked', '頻率', 'rate', '限制']):
                logger.warning(f"檢測到可能被封禁: {e}")
                raise RateLimitError(f"Akshare 可能被限流: {e}") from e
            
            raise DataFetchError(f"Akshare 獲取港股資料失敗: {e}") from e
    
    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        標準化 Akshare 資料
        
        Akshare 返回的列名（中文）：
        日期, 開盤, 收盤, 最高, 最低, 成交量, 成交額, 振幅, 漲跌幅, 漲跌額, 換手率
        
        需要對映到標準列名：
        date, open, high, low, close, volume, amount, pct_chg
        """
        df = df.copy()
        
        # 列名對映（Akshare 中文列名 -> 標準英文列名）
        column_mapping = {
            '日期': 'date',
            '開盤': 'open',
            '收盤': 'close',
            '最高': 'high',
            '最低': 'low',
            '成交量': 'volume',
            '成交額': 'amount',
            '漲跌幅': 'pct_chg',
        }
        
        # 重新命名列
        df = df.rename(columns=column_mapping)
        
        # 新增股票程式碼列
        df['code'] = stock_code
        
        # 只保留需要的列
        keep_cols = ['code'] + STANDARD_COLUMNS
        existing_cols = [col for col in keep_cols if col in df.columns]
        df = df[existing_cols]
        
        return df
    
    def get_realtime_quote(self, stock_code: str, source: str = "em") -> Optional[UnifiedRealtimeQuote]:
        """
        獲取實時行情資料（支援多資料來源）

        資料來源優先順序（可配置）：
        1. em: 東方財富（akshare ak.stock_zh_a_spot_em）- 資料最全，含量比/PE/PB/市值等
        2. sina: 新浪財經（akshare ak.stock_zh_a_spot）- 輕量級，基本行情
        3. tencent: 騰訊直連線口 - 單股票查詢，負載小

        Args:
            stock_code: 股票/ETF程式碼
            source: 資料來源型別，可選 "em", "sina", "tencent"

        Returns:
            UnifiedRealtimeQuote 物件，獲取失敗返回 None
        """
        circuit_breaker = get_realtime_circuit_breaker()

        # 根據程式碼型別選擇不同的獲取方法
        if _is_us_code(stock_code):
            # 美股不使用 Akshare，由 YfinanceFetcher 處理
            logger.debug(f"[API跳過] {stock_code} 是美股，Akshare 不支援美股實時行情")
            return None
        elif _is_hk_code(stock_code):
            return self._get_hk_realtime_quote(stock_code)
        elif _is_etf_code(stock_code):
            source_key = "akshare_etf"
            if not circuit_breaker.is_available(source_key):
                logger.warning(f"[熔斷] 資料來源 {source_key} 處於熔斷狀態，跳過")
                return None
            return self._get_etf_realtime_quote(stock_code)
        else:
            source_key = f"akshare_{source}"
            if not circuit_breaker.is_available(source_key):
                logger.warning(f"[熔斷] 資料來源 {source_key} 處於熔斷狀態，跳過")
                return None
            # 普通 A 股：根據 source 選擇資料來源
            if source == "sina":
                return self._get_stock_realtime_quote_sina(stock_code)
            elif source == "tencent":
                return self._get_stock_realtime_quote_tencent(stock_code)
            else:
                return self._get_stock_realtime_quote_em(stock_code)
    
    def _get_stock_realtime_quote_em(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        獲取普通 A 股實時行情資料（東方財富資料來源）
        
        資料來源：ak.stock_zh_a_spot_em()
        優點：資料最全，含量比、換手率、市盈率、市淨率、總市值、流通市值等
        缺點：全量拉取，資料量大，容易超時/限流
        """
        import akshare as ak
        circuit_breaker = get_realtime_circuit_breaker()
        source_key = "akshare_em"
        
        try:
            # 檢查快取
            current_time = time.time()
            if (_realtime_cache['data'] is not None and 
                current_time - _realtime_cache['timestamp'] < _realtime_cache['ttl']):
                df = _realtime_cache['data']
                cache_age = int(current_time - _realtime_cache['timestamp'])
                logger.debug(f"[快取命中] A股實時行情(東財) - 快取年齡 {cache_age}s/{_realtime_cache['ttl']}s")
            else:
                # 觸發全量重新整理
                logger.info(f"[快取未命中] 觸發全量重新整理 A股實時行情(東財)")
                last_error: Optional[Exception] = None
                df = None
                for attempt in range(1, 3):
                    try:
                        # 防封禁策略
                        self._set_random_user_agent()
                        self._enforce_rate_limit()

                        logger.info(f"[API呼叫] ak.stock_zh_a_spot_em() 獲取A股實時行情... (attempt {attempt}/2)")
                        import time as _time
                        api_start = _time.time()

                        df = ak.stock_zh_a_spot_em()

                        api_elapsed = _time.time() - api_start
                        logger.info(f"[API返回] ak.stock_zh_a_spot_em 成功: 返回 {len(df)} 只股票, 耗時 {api_elapsed:.2f}s")
                        circuit_breaker.record_success(source_key)
                        break
                    except Exception as e:
                        last_error = e
                        logger.warning(f"[API錯誤] ak.stock_zh_a_spot_em 獲取失敗 (attempt {attempt}/2): {e}")
                        time.sleep(min(2 ** attempt, 5))

                # 更新快取：成功快取資料；失敗也快取空資料，避免同一輪任務對同一介面反覆請求
                if df is None:
                    logger.error(f"[API錯誤] ak.stock_zh_a_spot_em 最終失敗: {last_error}")
                    circuit_breaker.record_failure(source_key, str(last_error))
                    df = pd.DataFrame()
                _realtime_cache['data'] = df
                _realtime_cache['timestamp'] = current_time
                logger.info(f"[快取更新] A股實時行情(東財) 快取已重新整理，TTL={_realtime_cache['ttl']}s")

            if df is None or df.empty:
                logger.warning(f"[實時行情] A股實時行情資料為空，跳過 {stock_code}")
                return None
            
            # 查詢指定股票
            row = df[df['程式碼'] == stock_code]
            if row.empty:
                logger.warning(f"[API返回] 未找到股票 {stock_code} 的實時行情")
                return None
            
            row = row.iloc[0]
            
            # 使用 realtime_types.py 中的統一轉換函式
            quote = UnifiedRealtimeQuote(
                code=stock_code,
                name=str(row.get('名稱', '')),
                source=RealtimeSource.AKSHARE_EM,
                price=safe_float(row.get('最新價')),
                change_pct=safe_float(row.get('漲跌幅')),
                change_amount=safe_float(row.get('漲跌額')),
                volume=safe_int(row.get('成交量')),
                amount=safe_float(row.get('成交額')),
                volume_ratio=safe_float(row.get('量比')),
                turnover_rate=safe_float(row.get('換手率')),
                amplitude=safe_float(row.get('振幅')),
                open_price=safe_float(row.get('今開')),
                high=safe_float(row.get('最高')),
                low=safe_float(row.get('最低')),
                pe_ratio=safe_float(row.get('市盈率-動態')),
                pb_ratio=safe_float(row.get('市淨率')),
                total_mv=safe_float(row.get('總市值')),
                circ_mv=safe_float(row.get('流通市值')),
                change_60d=safe_float(row.get('60日漲跌幅')),
                high_52w=safe_float(row.get('52周最高')),
                low_52w=safe_float(row.get('52周最低')),
            )
            
            logger.info(f"[實時行情-東財] {stock_code} {quote.name}: 價格={quote.price}, 漲跌={quote.change_pct}%, "
                       f"量比={quote.volume_ratio}, 換手率={quote.turnover_rate}%")
            return quote
            
        except Exception as e:
            logger.error(f"[API錯誤] 獲取 {stock_code} 實時行情(東財)失敗: {e}")
            circuit_breaker.record_failure(source_key, str(e))
            return None
    
    def _get_stock_realtime_quote_sina(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        獲取普通 A 股實時行情資料（新浪財經資料來源）
        
        資料來源：新浪財經介面（直連，單股票查詢）
        優點：單股票查詢，負載小，速度快
        缺點：資料欄位較少，無量比/PE/PB等
        
        介面格式：http://hq.sinajs.cn/list=sh600519,sz000001
        """
        circuit_breaker = get_realtime_circuit_breaker()
        source_key = "akshare_sina"
        symbol = _to_sina_tx_symbol(stock_code)
        url = f"http://{SINA_REALTIME_ENDPOINT}={symbol}"
        api_start = time.time()
        
        try:
            headers = {
                'Referer': 'http://finance.sina.com.cn',
                'User-Agent': random.choice(USER_AGENTS)
            }
            
            logger.info(
                f"[API呼叫] 新浪財經介面獲取 {stock_code} 實時行情: endpoint={SINA_REALTIME_ENDPOINT}, symbol={symbol}"
            )
            
            self._enforce_rate_limit()
            response = requests.get(url, headers=headers, timeout=10)
            response.encoding = 'gbk'
            api_elapsed = time.time() - api_start
            
            if response.status_code != 200:
                failure_message = _build_realtime_failure_message(
                    source_name="新浪",
                    endpoint=SINA_REALTIME_ENDPOINT,
                    stock_code=stock_code,
                    symbol=symbol,
                    category="http_status",
                    detail=f"HTTP {response.status_code}",
                    elapsed=api_elapsed,
                    error_type="HTTPStatus",
                )
                logger.warning(failure_message)
                circuit_breaker.record_failure(source_key, failure_message)
                return None
            
            # 解析資料：var hq_str_sh600519="貴州茅臺,1866.000,1870.000,..."
            content = response.text.strip()
            if '=""' in content or not content:
                failure_message = _build_realtime_failure_message(
                    source_name="新浪",
                    endpoint=SINA_REALTIME_ENDPOINT,
                    stock_code=stock_code,
                    symbol=symbol,
                    category="empty_response",
                    detail="empty quote payload",
                    elapsed=api_elapsed,
                    error_type="EmptyResponse",
                )
                logger.warning(failure_message)
                circuit_breaker.record_failure(source_key, failure_message)
                return None
            
            # 提取引號內的資料
            data_start = content.find('"')
            data_end = content.rfind('"')
            if data_start == -1 or data_end == -1:
                failure_message = _build_realtime_failure_message(
                    source_name="新浪",
                    endpoint=SINA_REALTIME_ENDPOINT,
                    stock_code=stock_code,
                    symbol=symbol,
                    category="malformed_payload",
                    detail="quote payload missing quotes",
                    elapsed=api_elapsed,
                    error_type="MalformedPayload",
                )
                logger.warning(failure_message)
                circuit_breaker.record_failure(source_key, failure_message)
                return None
            
            data_str = content[data_start+1:data_end]
            fields = data_str.split(',')
            
            if len(fields) < 32:
                failure_message = _build_realtime_failure_message(
                    source_name="新浪",
                    endpoint=SINA_REALTIME_ENDPOINT,
                    stock_code=stock_code,
                    symbol=symbol,
                    category="insufficient_fields",
                    detail=f"field_count={len(fields)}",
                    elapsed=api_elapsed,
                    error_type="InsufficientFields",
                )
                logger.warning(failure_message)
                circuit_breaker.record_failure(source_key, failure_message)
                return None
            
            circuit_breaker.record_success(source_key)
            
            # 新浪資料欄位順序：
            # 0:名稱 1:今開 2:昨收 3:最新價 4:最高 5:最低 6:買一價 7:賣一價
            # 8:成交量(股) 9:成交額(元) ... 30:日期 31:時間
            # 使用 realtime_types.py 中的統一轉換函式
            price = safe_float(fields[3])
            pre_close = safe_float(fields[2])
            change_pct = None
            change_amount = None
            if price and pre_close and pre_close > 0:
                change_amount = price - pre_close
                change_pct = (change_amount / pre_close) * 100
            
            quote = UnifiedRealtimeQuote(
                code=stock_code,
                name=fields[0],
                source=RealtimeSource.AKSHARE_SINA,
                price=price,
                change_pct=change_pct,
                change_amount=change_amount,
                volume=safe_int(fields[8]),  # 成交量（股）
                amount=safe_float(fields[9]),  # 成交額（元）
                open_price=safe_float(fields[1]),
                high=safe_float(fields[4]),
                low=safe_float(fields[5]),
                pre_close=pre_close,
            )
            
            logger.info(
                f"[實時行情-新浪] {stock_code} {quote.name}: endpoint={SINA_REALTIME_ENDPOINT}, "
                f"價格={quote.price}, 漲跌={quote.change_pct}, 成交量={quote.volume}, elapsed={api_elapsed:.2f}s"
            )
            return quote
            
        except Exception as e:
            api_elapsed = time.time() - api_start
            category, detail = _classify_realtime_http_error(e)
            failure_message = _build_realtime_failure_message(
                source_name="新浪",
                endpoint=SINA_REALTIME_ENDPOINT,
                stock_code=stock_code,
                symbol=symbol,
                category=category,
                detail=detail,
                elapsed=api_elapsed,
                error_type=type(e).__name__,
            )
            logger.error(failure_message)
            circuit_breaker.record_failure(source_key, failure_message)
            return None
    
    def _get_stock_realtime_quote_tencent(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        獲取普通 A 股實時行情資料（騰訊財經資料來源）
        
        資料來源：騰訊財經介面（直連，單股票查詢）
        優點：單股票查詢，負載小，包含換手率
        缺點：無量比/PE/PB等估值資料
        
        介面格式：http://qt.gtimg.cn/q=sh600519,sz000001
        """
        circuit_breaker = get_realtime_circuit_breaker()
        source_key = "akshare_tencent"
        symbol = _to_sina_tx_symbol(stock_code)
        url = f"http://{TENCENT_REALTIME_ENDPOINT}={symbol}"
        api_start = time.time()
        
        try:
            headers = {
                'Referer': 'http://finance.qq.com',
                'User-Agent': random.choice(USER_AGENTS)
            }
            
            logger.info(
                f"[API呼叫] 騰訊財經介面獲取 {stock_code} 實時行情: endpoint={TENCENT_REALTIME_ENDPOINT}, symbol={symbol}"
            )
            
            self._enforce_rate_limit()
            response = requests.get(url, headers=headers, timeout=10)
            response.encoding = 'gbk'
            api_elapsed = time.time() - api_start
            
            if response.status_code != 200:
                failure_message = _build_realtime_failure_message(
                    source_name="騰訊",
                    endpoint=TENCENT_REALTIME_ENDPOINT,
                    stock_code=stock_code,
                    symbol=symbol,
                    category="http_status",
                    detail=f"HTTP {response.status_code}",
                    elapsed=api_elapsed,
                    error_type="HTTPStatus",
                )
                logger.warning(failure_message)
                circuit_breaker.record_failure(source_key, failure_message)
                return None
            
            content = response.text.strip()
            if '=""' in content or not content:
                failure_message = _build_realtime_failure_message(
                    source_name="騰訊",
                    endpoint=TENCENT_REALTIME_ENDPOINT,
                    stock_code=stock_code,
                    symbol=symbol,
                    category="empty_response",
                    detail="empty quote payload",
                    elapsed=api_elapsed,
                    error_type="EmptyResponse",
                )
                logger.warning(failure_message)
                circuit_breaker.record_failure(source_key, failure_message)
                return None
            
            # 提取資料
            data_start = content.find('"')
            data_end = content.rfind('"')
            if data_start == -1 or data_end == -1:
                failure_message = _build_realtime_failure_message(
                    source_name="騰訊",
                    endpoint=TENCENT_REALTIME_ENDPOINT,
                    stock_code=stock_code,
                    symbol=symbol,
                    category="malformed_payload",
                    detail="quote payload missing quotes",
                    elapsed=api_elapsed,
                    error_type="MalformedPayload",
                )
                logger.warning(failure_message)
                circuit_breaker.record_failure(source_key, failure_message)
                return None
            
            data_str = content[data_start+1:data_end]
            fields = data_str.split('~')

            if len(fields) < 45:
                failure_message = _build_realtime_failure_message(
                    source_name="騰訊",
                    endpoint=TENCENT_REALTIME_ENDPOINT,
                    stock_code=stock_code,
                    symbol=symbol,
                    category="insufficient_fields",
                    detail=f"field_count={len(fields)}",
                    elapsed=api_elapsed,
                    error_type="InsufficientFields",
                )
                logger.warning(failure_message)
                circuit_breaker.record_failure(source_key, failure_message)
                return None
            
            circuit_breaker.record_success(source_key)
            
            # 騰訊資料欄位順序（完整）：
            # 1:名稱 2:程式碼 3:最新價 4:昨收 5:今開 6:成交量(手) 7:外盤 8:內盤
            # 9-28:買賣五檔 30:時間戳 31:漲跌額 32:漲跌幅(%) 33:最高 34:最低 35:收盤/成交量/成交額
            # 36:成交量(手) 37:成交額(萬) 38:換手率(%) 39:市盈率 43:振幅(%)
            # 44:流通市值(億) 45:總市值(億) 46:市淨率 47:漲停價 48:跌停價 49:量比
            # 使用 realtime_types.py 中的統一轉換函式
            quote = UnifiedRealtimeQuote(
                code=stock_code,
                name=fields[1] if len(fields) > 1 else "",
                source=RealtimeSource.TENCENT,
                price=safe_float(fields[3]),
                change_pct=safe_float(fields[32]),
                change_amount=safe_float(fields[31]) if len(fields) > 31 else None,
                volume=safe_int(fields[6]) * 100 if fields[6] else None,  # 騰訊返回的是手，轉為股
                open_price=safe_float(fields[5]),
                high=safe_float(fields[33]) if len(fields) > 33 else None,  # 修正：欄位 33 是最高價
                low=safe_float(fields[34]) if len(fields) > 34 else None,  # 修正：欄位 34 是最低價
                pre_close=safe_float(fields[4]),
                turnover_rate=safe_float(fields[38]) if len(fields) > 38 else None,
                amplitude=safe_float(fields[43]) if len(fields) > 43 else None,
                volume_ratio=safe_float(fields[49]) if len(fields) > 49 else None,  # 量比
                pe_ratio=safe_float(fields[39]) if len(fields) > 39 else None,  # 市盈率
                pb_ratio=safe_float(fields[46]) if len(fields) > 46 else None,  # 市淨率
                circ_mv=safe_float(fields[44]) * 100000000 if len(fields) > 44 and fields[44] else None,  # 流通市值(億->元)
                total_mv=safe_float(fields[45]) * 100000000 if len(fields) > 45 and fields[45] else None,  # 總市值(億->元)
            )
            
            logger.info(
                f"[實時行情-騰訊] {stock_code} {quote.name}: endpoint={TENCENT_REALTIME_ENDPOINT}, "
                f"價格={quote.price}, 漲跌={quote.change_pct}%, 量比={quote.volume_ratio}, "
                f"換手率={quote.turnover_rate}%, elapsed={api_elapsed:.2f}s"
            )
            return quote
            
        except Exception as e:
            api_elapsed = time.time() - api_start
            category, detail = _classify_realtime_http_error(e)
            failure_message = _build_realtime_failure_message(
                source_name="騰訊",
                endpoint=TENCENT_REALTIME_ENDPOINT,
                stock_code=stock_code,
                symbol=symbol,
                category=category,
                detail=detail,
                elapsed=api_elapsed,
                error_type=type(e).__name__,
            )
            logger.error(failure_message)
            circuit_breaker.record_failure(source_key, failure_message)
            return None
    
    def _get_etf_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        獲取 ETF 基金實時行情資料
        
        資料來源：ak.fund_etf_spot_em()
        包含：最新價、漲跌幅、成交量、成交額、換手率等
        
        Args:
            stock_code: ETF 程式碼
            
        Returns:
            UnifiedRealtimeQuote 物件，獲取失敗返回 None
        """
        import akshare as ak
        circuit_breaker = get_realtime_circuit_breaker()
        source_key = "akshare_etf"
        
        try:
            # 檢查快取
            current_time = time.time()
            if (_etf_realtime_cache['data'] is not None and 
                current_time - _etf_realtime_cache['timestamp'] < _etf_realtime_cache['ttl']):
                df = _etf_realtime_cache['data']
                logger.debug(f"[快取命中] 使用快取的ETF實時行情資料")
            else:
                last_error: Optional[Exception] = None
                df = None
                for attempt in range(1, 3):
                    try:
                        # 防封禁策略
                        self._set_random_user_agent()
                        self._enforce_rate_limit()

                        logger.info(f"[API呼叫] ak.fund_etf_spot_em() 獲取ETF實時行情... (attempt {attempt}/2)")
                        import time as _time
                        api_start = _time.time()

                        df = ak.fund_etf_spot_em()

                        api_elapsed = _time.time() - api_start
                        logger.info(f"[API返回] ak.fund_etf_spot_em 成功: 返回 {len(df)} 只ETF, 耗時 {api_elapsed:.2f}s")
                        circuit_breaker.record_success(source_key)
                        break
                    except Exception as e:
                        last_error = e
                        logger.warning(f"[API錯誤] ak.fund_etf_spot_em 獲取失敗 (attempt {attempt}/2): {e}")
                        time.sleep(min(2 ** attempt, 5))

                if df is None:
                    logger.error(f"[API錯誤] ak.fund_etf_spot_em 最終失敗: {last_error}")
                    circuit_breaker.record_failure(source_key, str(last_error))
                    df = pd.DataFrame()
                _etf_realtime_cache['data'] = df
                _etf_realtime_cache['timestamp'] = current_time

            if df is None or df.empty:
                logger.warning(f"[實時行情] ETF實時行情資料為空，跳過 {stock_code}")
                return None
            
            # 查詢指定 ETF
            row = df[df['程式碼'] == stock_code]
            if row.empty:
                logger.warning(f"[API返回] 未找到 ETF {stock_code} 的實時行情")
                return None
            
            row = row.iloc[0]
            
            # 使用 realtime_types.py 中的統一轉換函式
            # ETF 行情資料構建
            quote = UnifiedRealtimeQuote(
                code=stock_code,
                name=str(row.get('名稱', '')),
                source=RealtimeSource.AKSHARE_EM,
                price=safe_float(row.get('最新價')),
                change_pct=safe_float(row.get('漲跌幅')),
                change_amount=safe_float(row.get('漲跌額')),
                volume=safe_int(row.get('成交量')),
                amount=safe_float(row.get('成交額')),
                volume_ratio=safe_float(row.get('量比')),
                turnover_rate=safe_float(row.get('換手率')),
                amplitude=safe_float(row.get('振幅')),
                open_price=safe_float(row.get('開盤價')),
                high=safe_float(row.get('最高價')),
                low=safe_float(row.get('最低價')),
                total_mv=safe_float(row.get('總市值')),
                circ_mv=safe_float(row.get('流通市值')),
                high_52w=safe_float(row.get('52周最高')),
                low_52w=safe_float(row.get('52周最低')),
            )
            
            logger.info(f"[ETF實時行情] {stock_code} {quote.name}: 價格={quote.price}, 漲跌={quote.change_pct}%, "
                       f"換手率={quote.turnover_rate}%")
            return quote
            
        except Exception as e:
            logger.error(f"[API錯誤] 獲取 ETF {stock_code} 實時行情失敗: {e}")
            circuit_breaker.record_failure(source_key, str(e))
            return None
    
    def _get_hk_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        獲取港股實時行情資料
        
        資料來源：ak.stock_hk_spot_em()
        包含：最新價、漲跌幅、成交量、成交額等
        
        Args:
            stock_code: 港股程式碼
            
        Returns:
            UnifiedRealtimeQuote 物件，獲取失敗返回 None
        """
        import akshare as ak
        circuit_breaker = get_realtime_circuit_breaker()
        source_key = "akshare_hk"

        if not circuit_breaker.is_available(source_key):
            logger.warning(f"[熔斷] 資料來源 {source_key} 處於熔斷狀態，跳過")
            return None
        
        try:
            # 防封禁策略
            self._set_random_user_agent()
            self._enforce_rate_limit()
            
            # 確保程式碼格式正確（5位數字）
            raw_code = stock_code.strip().lower()
            if raw_code.endswith('.hk'):
                raw_code = raw_code[:-3]
            if raw_code.startswith('hk'):
                raw_code = raw_code[2:]
            code = raw_code.zfill(5)
            
            logger.info(f"[API呼叫] ak.stock_hk_spot_em() 獲取港股實時行情...")
            import time as _time
            api_start = _time.time()
            
            df = ak.stock_hk_spot_em()
            
            api_elapsed = _time.time() - api_start
            logger.info(f"[API返回] ak.stock_hk_spot_em 成功: 返回 {len(df)} 只港股, 耗時 {api_elapsed:.2f}s")
            circuit_breaker.record_success(source_key)
            
            # 查詢指定港股
            row = df[df['程式碼'] == code]
            if row.empty:
                logger.warning(f"[API返回] 未找到港股 {code} 的實時行情")
                return None
            
            row = row.iloc[0]
            
            # 使用 realtime_types.py 中的統一轉換函式
            # 港股行情資料構建
            quote = UnifiedRealtimeQuote(
                code=stock_code,
                name=str(row.get('名稱', '')),
                source=RealtimeSource.AKSHARE_EM,
                price=safe_float(row.get('最新價')),
                change_pct=safe_float(row.get('漲跌幅')),
                change_amount=safe_float(row.get('漲跌額')),
                volume=safe_int(row.get('成交量')),
                amount=safe_float(row.get('成交額')),
                volume_ratio=safe_float(row.get('量比')),
                turnover_rate=safe_float(row.get('換手率')),
                amplitude=safe_float(row.get('振幅')),
                pe_ratio=safe_float(row.get('市盈率')),
                pb_ratio=safe_float(row.get('市淨率')),
                total_mv=safe_float(row.get('總市值')),
                circ_mv=safe_float(row.get('流通市值')),
                high_52w=safe_float(row.get('52周最高')),
                low_52w=safe_float(row.get('52周最低')),
            )
            
            logger.info(f"[港股實時行情] {stock_code} {quote.name}: 價格={quote.price}, 漲跌={quote.change_pct}%, "
                       f"換手率={quote.turnover_rate}%")
            return quote
            
        except Exception as e:
            logger.error(f"[API錯誤] 獲取港股 {stock_code} 實時行情失敗: {e}")
            circuit_breaker.record_failure(source_key, str(e))
            return None
    
    def get_chip_distribution(self, stock_code: str) -> Optional[ChipDistribution]:
        """
        獲取籌碼分佈資料
        
        資料來源：ak.stock_cyq_em()
        包含：獲利比例、平均成本、籌碼集中度
        
        注意：ETF/指數沒有籌碼分佈資料，會直接返回 None
        
        Args:
            stock_code: 股票程式碼
            
        Returns:
            ChipDistribution 物件（最新一天的資料），獲取失敗返回 None
        """
        import akshare as ak

        # 美股沒有籌碼分佈資料（Akshare 不支援）
        if _is_us_code(stock_code):
            logger.debug(f"[API跳過] {stock_code} 是美股，無籌碼分佈資料")
            return None

        # 港股沒有籌碼分佈資料（stock_cyq_em 是 A 股專屬介面）
        if _is_hk_code(stock_code):
            logger.debug(f"[API跳過] {stock_code} 是港股，無籌碼分佈資料")
            return None

        # ETF/指數沒有籌碼分佈資料
        if _is_etf_code(stock_code):
            logger.debug(f"[API跳過] {stock_code} 是 ETF/指數，無籌碼分佈資料")
            return None
        
        try:
            # 防封禁策略
            self._set_random_user_agent()
            self._enforce_rate_limit()
            
            logger.info(f"[API呼叫] ak.stock_cyq_em(symbol={stock_code}) 獲取籌碼分佈...")
            import time as _time
            api_start = _time.time()
            
            df = ak.stock_cyq_em(symbol=stock_code)
            
            api_elapsed = _time.time() - api_start
            
            if df.empty:
                logger.warning(f"[API返回] ak.stock_cyq_em 返回空資料, 耗時 {api_elapsed:.2f}s")
                return None
            
            logger.info(f"[API返回] ak.stock_cyq_em 成功: 返回 {len(df)} 天資料, 耗時 {api_elapsed:.2f}s")
            logger.debug(f"[API返回] 籌碼資料列名: {list(df.columns)}")
            
            # 取最新一天的資料
            latest = df.iloc[-1]
            
            # 使用 realtime_types.py 中的統一轉換函式
            chip = ChipDistribution(
                code=stock_code,
                date=str(latest.get('日期', '')),
                profit_ratio=safe_float(latest.get('獲利比例')),
                avg_cost=safe_float(latest.get('平均成本')),
                cost_90_low=safe_float(latest.get('90成本-低')),
                cost_90_high=safe_float(latest.get('90成本-高')),
                concentration_90=safe_float(latest.get('90集中度')),
                cost_70_low=safe_float(latest.get('70成本-低')),
                cost_70_high=safe_float(latest.get('70成本-高')),
                concentration_70=safe_float(latest.get('70集中度')),
            )
            
            logger.info(f"[籌碼分佈] {stock_code} 日期={chip.date}: 獲利比例={chip.profit_ratio:.1%}, "
                       f"平均成本={chip.avg_cost}, 90%集中度={chip.concentration_90:.2%}, "
                       f"70%集中度={chip.concentration_70:.2%}")
            return chip
            
        except Exception as e:
            logger.error(f"[API錯誤] 獲取 {stock_code} 籌碼分佈失敗: {e}")
            return None
    
    def get_enhanced_data(self, stock_code: str, days: int = 60) -> Dict[str, Any]:
        """
        獲取增強資料（歷史K線 + 實時行情 + 籌碼分佈）
        
        Args:
            stock_code: 股票程式碼
            days: 歷史資料天數
            
        Returns:
            包含所有資料的字典
        """
        result = {
            'code': stock_code,
            'daily_data': None,
            'realtime_quote': None,
            'chip_distribution': None,
        }
        
        # 獲取日線資料
        try:
            df = self.get_daily_data(stock_code, days=days)
            result['daily_data'] = df
        except Exception as e:
            logger.error(f"獲取 {stock_code} 日線資料失敗: {e}")
        
        # 獲取實時行情
        result['realtime_quote'] = self.get_realtime_quote(stock_code)
        
        # 獲取籌碼分佈
        result['chip_distribution'] = self.get_chip_distribution(stock_code)
        
        return result

    def get_main_indices(self, region: str = "cn") -> Optional[List[Dict[str, Any]]]:
        """
        獲取主要指數實時行情 (新浪介面)，僅支援 A 股
        """
        if region != "cn":
            return None
        import akshare as ak

        # 主要指數程式碼對映
        indices_map = {
            'sh000001': '上證指數',
            'sz399001': '深證成指',
            'sz399006': '創業板指',
            'sh000688': '科創50',
            'sh000016': '上證50',
            'sh000300': '滬深300',
        }

        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()

            # 使用 akshare 獲取指數行情（新浪財經介面）
            df = ak.stock_zh_index_spot_sina()

            results = []
            if df is not None and not df.empty:
                for code, name in indices_map.items():
                    # 查詢對應指數
                    row = df[df['程式碼'] == code]
                    if row.empty:
                        # 嘗試帶字首查詢
                        row = df[df['程式碼'].str.contains(code)]

                    if not row.empty:
                        row = row.iloc[0]
                        current = safe_float(row.get('最新價', 0))
                        prev_close = safe_float(row.get('昨收', 0))
                        high = safe_float(row.get('最高', 0))
                        low = safe_float(row.get('最低', 0))

                        # 計算振幅
                        amplitude = 0.0
                        if prev_close > 0:
                            amplitude = (high - low) / prev_close * 100

                        results.append({
                            'code': code,
                            'name': name,
                            'current': current,
                            'change': safe_float(row.get('漲跌額', 0)),
                            'change_pct': safe_float(row.get('漲跌幅', 0)),
                            'open': safe_float(row.get('今開', 0)),
                            'high': high,
                            'low': low,
                            'prev_close': prev_close,
                            'volume': safe_float(row.get('成交量', 0)),
                            'amount': safe_float(row.get('成交額', 0)),
                            'amplitude': amplitude,
                        })
            return results

        except Exception as e:
            logger.error(f"[Akshare] 獲取指數行情失敗: {e}")
            return None

    def get_market_stats(self) -> Optional[Dict[str, Any]]:
        """
        獲取市場漲跌統計

        資料來源優先順序：
        1. 東財介面 (ak.stock_zh_a_spot_em)
        2. 新浪介面 (ak.stock_zh_a_spot)
        """
        import akshare as ak

        # 優先東財介面
        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()

            logger.info("[API呼叫] ak.stock_zh_a_spot_em() 獲取市場統計...")
            df = ak.stock_zh_a_spot_em()
            if df is not None and not df.empty:
                return self._calc_market_stats(df)
        except Exception as e:
            logger.warning(f"[Akshare] 東財介面獲取市場統計失敗: {e}，嘗試新浪介面")

        # 東財失敗後，嘗試新浪介面
        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()

            logger.info("[API呼叫] ak.stock_zh_a_spot() 獲取市場統計(新浪)...")
            df = ak.stock_zh_a_spot()
            if df is not None and not df.empty:
                return self._calc_market_stats(df)
        except Exception as e:
            logger.error(f"[Akshare] 新浪介面獲取市場統計也失敗: {e}")

        return None

    def _calc_market_stats(
        self,
        df: pd.DataFrame,
        ) -> Optional[Dict[str, Any]]:
        """從行情 DataFrame 計算漲跌統計。"""
        import numpy as np

        df = df.copy()
        
        # 1. 提取基礎比對資料：最新價、昨收
        # 相容不同介面返回的列名 sina/em efinance tushare xtdata
        code_col = next((c for c in ['程式碼', '股票程式碼', 'ts_code','stock_code'] if c in df.columns), None)
        name_col = next((c for c in ['名稱', '股票名稱','name','name'] if c in df.columns), None)
        close_col = next((c for c in ['最新價', '最新價', 'close','lastPrice'] if c in df.columns), None)
        pre_close_col = next((c for c in ['昨收', '昨日收盤', 'pre_close','lastClose'] if c in df.columns), None)
        amount_col = next((c for c in ['成交額', '成交額', 'amount','amount'] if c in df.columns), None) 
        
        limit_up_count = 0
        limit_down_count = 0
        up_count = 0
        down_count = 0
        flat_count = 0

        for code, name, current_price, pre_close, amount in zip(
            df[code_col], df[name_col], df[close_col], df[pre_close_col], df[amount_col]
        ):
            
            # 停牌過濾 efinance 的停牌資料有時候會缺失價格顯示為 '-'，em 顯示為none
            if pd.isna(current_price) or pd.isna(pre_close) or current_price in ['-'] or pre_close in ['-'] or amount == 0:
                continue
            
            # em、efinance 為str 需要轉換為float
            current_price = float(current_price)
            pre_close = float(pre_close)
            
            # 獲取去除字首的純數字程式碼
            pure_code = normalize_stock_code(str(code)) 

            # A. 確定每隻股票的漲跌幅比例 (使用純數字程式碼判斷)
            if is_bse_code(pure_code): 
                ratio = 0.30
            elif is_kc_cy_stock(pure_code): #pure_code.startswith(('688', '30')):
                ratio = 0.20
            elif is_st_stock(name): #'ST' in str_name:
                ratio = 0.05
            else:
                ratio = 0.10

            # B. 嚴格按照 A 股規則計算漲跌停價：昨收 * (1 ± 比例) -> 四捨五入保留2位小數
            limit_up_price = np.floor(pre_close * (1 + ratio) * 100 + 0.5) / 100.0
            limit_down_price = np.floor(pre_close * (1 - ratio) * 100 + 0.5) / 100.0

            limit_up_price_Tolerance = round(abs(pre_close * (1 + ratio) - limit_up_price), 10)
            limit_down_price_Tolerance = round(abs(pre_close * (1 - ratio) - limit_down_price), 10)

            # C. 精確比對
            if current_price > 0 :
                is_limit_up = (current_price > 0) and (abs(current_price - limit_up_price) <= limit_up_price_Tolerance)
                is_limit_down = (current_price > 0) and (abs(current_price - limit_down_price) <= limit_down_price_Tolerance)

                if is_limit_up:
                    limit_up_count += 1
                if is_limit_down:
                    limit_down_count += 1

                if current_price > pre_close:
                    up_count += 1
                elif current_price < pre_close:
                    down_count += 1
                else:
                    flat_count += 1
                
        # 統計數量
        stats = {
            'up_count': up_count,
            'down_count': down_count,
            'flat_count': flat_count,
            'limit_up_count': limit_up_count,
            'limit_down_count': limit_down_count,
            'total_amount': 0.0,
        }
        
        # 成交額統計
        if amount_col and amount_col in df.columns:
            df[amount_col] = pd.to_numeric(df[amount_col], errors='coerce')
            stats['total_amount'] = (df[amount_col].sum() / 1e8)
            
        return stats

    def get_sector_rankings(self, n: int = 5) -> Optional[Tuple[List[Dict], List[Dict]]]:
        """
        獲取行業板塊漲跌榜

        資料來源優先順序：
        1. 東財介面 (ak.stock_board_industry_name_em)
        2. 新浪介面 (ak.stock_sector_spot)
        """
        import akshare as ak

        def _get_rank_top_n(df: pd.DataFrame, change_col: str, industry_name: str, n: int) -> Tuple[list, list]:
            df[change_col] = pd.to_numeric(df[change_col], errors='coerce')
            df = df.dropna(subset=[change_col])

            # 漲幅前n
            top = df.nlargest(n, change_col)
            top_sectors = [
                {'name': row[industry_name], 'change_pct': row[change_col]}
                for _, row in top.iterrows()
            ]

            bottom = df.nsmallest(n, change_col)
            bottom_sectors = [
                {'name': row[industry_name], 'change_pct': row[change_col]}
                for _, row in bottom.iterrows()
            ]
            return top_sectors, bottom_sectors
        
        # 優先東財介面
        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()

            logger.info("[API呼叫] ak.stock_board_industry_name_em() 獲取板塊排行...")
            df = ak.stock_board_industry_name_em()
            if df is not None and not df.empty:
                change_col = '漲跌幅'
                name = '板塊名稱'
                return _get_rank_top_n(df, change_col, name, n)
            
        except Exception as e:
            logger.warning(f"[Akshare] 東財介面獲取行業板塊排行失敗: {e}，嘗試新浪介面")

        # 東財失敗後，嘗試新浪介面
        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()

            logger.info("[API呼叫] ak.stock_sector_spot() 獲取行業板塊排行(新浪)...")
            df = ak.stock_sector_spot(indicator='行業')
            if df is None or df.empty:
                return None
            change_col = '漲跌幅'
            name = '板塊'
            return _get_rank_top_n(df, change_col, name, n)
        
        except Exception as e:
            logger.error(f"[Akshare] 新浪介面獲取板塊排行也失敗: {e}")
            return None


if __name__ == "__main__":
    # 測試程式碼
    logging.basicConfig(level=logging.DEBUG)
    
    fetcher = AkshareFetcher()
    
    # 測試普通股票
    print("=" * 50)
    print("測試普通股票資料獲取")
    print("=" * 50)
    try:
        df = fetcher.get_daily_data('600519')  # 茅臺
        print(f"[股票] 獲取成功，共 {len(df)} 條資料")
        print(df.tail())
    except Exception as e:
        print(f"[股票] 獲取失敗: {e}")
    
    # 測試 ETF 基金
    print("\n" + "=" * 50)
    print("測試 ETF 基金資料獲取")
    print("=" * 50)
    try:
        df = fetcher.get_daily_data('512400')  # 有色龍頭ETF
        print(f"[ETF] 獲取成功，共 {len(df)} 條資料")
        print(df.tail())
    except Exception as e:
        print(f"[ETF] 獲取失敗: {e}")
    
    # 測試 ETF 實時行情
    print("\n" + "=" * 50)
    print("測試 ETF 實時行情獲取")
    print("=" * 50)
    try:
        quote = fetcher.get_realtime_quote('512880')  # 證券ETF
        if quote:
            print(f"[ETF實時] {quote.name}: 價格={quote.price}, 漲跌幅={quote.change_pct}%")
        else:
            print("[ETF實時] 未獲取到資料")
    except Exception as e:
        print(f"[ETF實時] 獲取失敗: {e}")
    
    # 測試港股歷史資料
    print("\n" + "=" * 50)
    print("測試港股歷史資料獲取")
    print("=" * 50)
    try:
        df = fetcher.get_daily_data('00700')  # 騰訊控股
        print(f"[港股] 獲取成功，共 {len(df)} 條資料")
        print(df.tail())
    except Exception as e:
        print(f"[港股] 獲取失敗: {e}")
    
    # 測試港股實時行情
    print("\n" + "=" * 50)
    print("測試港股實時行情獲取")
    print("=" * 50)
    try:
        quote = fetcher.get_realtime_quote('00700')  # 騰訊控股
        if quote:
            print(f"[港股實時] {quote.name}: 價格={quote.price}, 漲跌幅={quote.change_pct}%")
        else:
            print("[港股實時] 未獲取到資料")
    except Exception as e:
        print(f"[港股實時] 獲取失敗: {e}")

    # 測試市場統計
    print("\n" + "=" * 50)
    print("Testing get_market_stats (akshare)")
    print("=" * 50)
    try:
        stats = fetcher.get_market_stats()
        if stats:
            print(f"Market Stats successfully computed:")
            print(f"Up: {stats['up_count']} (Limit Up: {stats['limit_up_count']})")
            print(f"Down: {stats['down_count']} (Limit Down: {stats['limit_down_count']})")
            print(f"Flat: {stats['flat_count']}")
            print(f"Total Amount: {stats['total_amount']:.2f} 億 (Yi)")
        else:
            print("Failed to compute market stats.")
    except Exception as e:
        print(f"Failed to compute market stats: {e}")

    # 測試籌碼分佈資料
    print("\n" + "=" * 50)
    print("測試籌碼分佈資料獲取")
    print("=" * 50)
    try:
        chip = fetcher.get_chip_distribution('600519')  # 茅臺
    except Exception as e:
        print(f"[籌碼分佈] 獲取失敗: {e}")

    # 測試行業板塊排名
    print("\n" + "=" * 50)
    print("測試行業板塊排名獲取")
    print("=" * 50)
    try:
        rankings = fetcher.get_sector_rankings(n=5)
        if rankings:
            top, bottom = rankings
            print("漲幅榜 Top 5:")
            for sector in top:
                print(f"{sector['name']}: {sector['change_pct']}%")
            print("\n跌幅榜 Top 5:")
            for sector in bottom:
                print(f"{sector['name']}: {sector['change_pct']}%")
        else:
            print("未獲取到行業板塊排名資料")
    except Exception as e:
        print(f"[行業板塊排名] 獲取失敗: {e}")
