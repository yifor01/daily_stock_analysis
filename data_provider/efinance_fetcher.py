# -*- coding: utf-8 -*-
"""
===================================
EfinanceFetcher - 優先資料來源 (Priority 0)
===================================

資料來源：東方財富爬蟲（透過 efinance 庫）
特點：免費、無需 Token、資料全面、API 簡潔
倉庫：https://github.com/Micro-sheep/efinance

與 AkshareFetcher 類似，但 efinance 庫：
1. API 更簡潔易用
2. 支援批次獲取資料
3. 更穩定的介面封裝

防封禁策略：
1. 每次請求前隨機休眠 1.5-3.0 秒
2. 隨機輪換 User-Agent
3. 使用 tenacity 實現指數退避重試
4. 熔斷器機制：連續失敗後自動冷卻
"""

import logging
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

import pandas as pd
import requests  # 引入 requests 以捕獲異常
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

# Timeout (seconds) for efinance library calls that go through eastmoney APIs
# with no built-in timeout.  Prevents indefinite hangs when hosts are unreachable.
try:
    _EF_CALL_TIMEOUT = int(os.environ.get("EFINANCE_CALL_TIMEOUT", "30"))
except (ValueError, TypeError):
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "EFINANCE_CALL_TIMEOUT is not a valid integer, using default 30s"
    )
    _EF_CALL_TIMEOUT = 30

from patch.eastmoney_patch import eastmoney_patch
from src.config import get_config
from .base import BaseFetcher, DataFetchError, RateLimitError, STANDARD_COLUMNS,is_bse_code, is_st_stock, is_kc_cy_stock, normalize_stock_code
from .realtime_types import (
    UnifiedRealtimeQuote, RealtimeSource,
    get_realtime_circuit_breaker,
    safe_float, safe_int  # 使用統一的型別轉換函式
)


# 保留舊的型別別名，用於向後相容
@dataclass
class EfinanceRealtimeQuote:
    """
    實時行情資料（來自 efinance）- 向後相容別名
    
    新程式碼建議使用 UnifiedRealtimeQuote
    """
    code: str
    name: str = ""
    price: float = 0.0           # 最新價
    change_pct: float = 0.0      # 漲跌幅(%)
    change_amount: float = 0.0   # 漲跌額
    
    # 量價指標
    volume: int = 0              # 成交量
    amount: float = 0.0          # 成交額
    turnover_rate: float = 0.0   # 換手率(%)
    amplitude: float = 0.0       # 振幅(%)
    
    # 價格區間
    high: float = 0.0            # 最高價
    low: float = 0.0             # 最低價
    open_price: float = 0.0      # 開盤價
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        return {
            'code': self.code,
            'name': self.name,
            'price': self.price,
            'change_pct': self.change_pct,
            'change_amount': self.change_amount,
            'volume': self.volume,
            'amount': self.amount,
            'turnover_rate': self.turnover_rate,
            'amplitude': self.amplitude,
            'high': self.high,
            'low': self.low,
            'open': self.open_price,
        }


logger = logging.getLogger(__name__)

EASTMONEY_HISTORY_ENDPOINT = "push2his.eastmoney.com/api/qt/stock/kline/get"


# User-Agent 池，用於隨機輪換
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]


# 快取實時行情資料（避免重複請求）
# TTL 設為 10 分鐘 (600秒)：批次分析場景下避免重複拉取
_realtime_cache: Dict[str, Any] = {
    'data': None,
    'timestamp': 0,
    'ttl': 600  # 10分鐘快取有效期
}

# ETF 實時行情快取（與股票分開快取）
_etf_realtime_cache: Dict[str, Any] = {
    'data': None,
    'timestamp': 0,
    'ttl': 600  # 10分鐘快取有效期
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
    return stock_code.startswith(etf_prefixes) and len(stock_code) == 6


def _is_us_code(stock_code: str) -> bool:
    """
    判斷程式碼是否為美股
    
    美股程式碼規則：
    - 1-5個大寫字母，如 'AAPL', 'TSLA'
    - 可能包含 '.'，如 'BRK.B'
    """
    code = stock_code.strip().upper()
    return bool(re.match(r'^[A-Z]{1,5}(\.[A-Z])?$', code))


def _ef_call_with_timeout(func, *args, timeout=None, **kwargs):
    """Run an efinance library call in a thread with a timeout.

    efinance internally uses requests/urllib3 with no timeout, so when
    eastmoney hosts are unreachable the call can hang for many minutes.
    This helper caps the *calling thread's* wait time.  Note: Python threads
    cannot be forcibly killed, so the worker thread may continue running in
    the background until the OS-level TCP timeout fires or the process exits.
    This is acceptable — the calling thread returns promptly on timeout.
    """
    if timeout is None:
        timeout = _EF_CALL_TIMEOUT
    # Do NOT use 'with ThreadPoolExecutor(...)' here: the context manager calls
    # shutdown(wait=True) on __exit__, which would re-block on the hung thread.
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(func, *args, **kwargs)
        return future.result(timeout=timeout)
    finally:
        # wait=False: calling thread returns immediately; worker cleans up later
        executor.shutdown(wait=False)


def _classify_eastmoney_error(exc: Exception) -> Tuple[str, str]:
    """
    Classify Eastmoney request failures into stable log categories.
    """
    message = str(exc).strip()
    lowered = message.lower()

    remote_disconnect_keywords = (
        'remotedisconnected',
        'remote end closed connection without response',
        'connection aborted',
        'connection broken',
        'protocolerror',
    )
    timeout_keywords = (
        'timeout',
        'timed out',
        'readtimeout',
        'connecttimeout',
    )
    rate_limit_keywords = (
        'banned',
        'blocked',
        '頻率',
        'rate limit',
        'too many requests',
        '429',
        '限制',
        'forbidden',
        '403',
    )

    if any(keyword in lowered for keyword in remote_disconnect_keywords):
        return "remote_disconnect", message
    if isinstance(exc, (TimeoutError, requests.exceptions.Timeout)) or any(
        keyword in lowered for keyword in timeout_keywords
    ):
        return "timeout", message
    if any(keyword in lowered for keyword in rate_limit_keywords):
        return "rate_limit_or_anti_bot", message
    if isinstance(exc, requests.exceptions.RequestException):
        return "request_error", message
    return "unknown_request_error", message


class EfinanceFetcher(BaseFetcher):
    """
    Efinance 資料來源實現
    
    優先順序：0（最高，優先於 AkshareFetcher）
    資料來源：東方財富網（透過 efinance 庫封裝）
    倉庫：https://github.com/Micro-sheep/efinance
    
    主要 API：
    - ef.stock.get_quote_history(): 獲取歷史 K 線資料
    - ef.stock.get_base_info(): 獲取股票基本資訊
    - ef.stock.get_realtime_quotes(): 獲取實時行情
    
    關鍵策略：
    - 每次請求前隨機休眠 1.5-3.0 秒
    - 隨機 User-Agent 輪換
    - 失敗後指數退避重試（最多3次）
    """
    
    name = "EfinanceFetcher"
    priority = int(os.getenv("EFINANCE_PRIORITY", "0"))  # 最高優先順序，排在 AkshareFetcher 之前
    
    def __init__(self, sleep_min: float = 1.5, sleep_max: float = 3.0):
        """
        初始化 EfinanceFetcher
        
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

    @staticmethod
    def _build_history_failure_message(
        stock_code: str,
        beg_date: str,
        end_date: str,
        exc: Exception,
        elapsed: float,
        is_etf: bool = False,
    ) -> Tuple[str, str]:
        category, detail = _classify_eastmoney_error(exc)
        instrument_type = "ETF" if is_etf else "stock"
        message = (
            "Eastmoney 歷史K線介面失敗: "
            f"endpoint={EASTMONEY_HISTORY_ENDPOINT}, stock_code={stock_code}, "
            f"market_type={instrument_type}, range={beg_date}~{end_date}, "
            f"category={category}, error_type={type(exc).__name__}, elapsed={elapsed:.2f}s, detail={detail}"
        )
        return category, message

    def _set_random_user_agent(self) -> None:
        """
        設定隨機 User-Agent
        
        透過修改 requests Session 的 headers 實現
        這是關鍵的反爬策略之一
        """
        try:
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
        stop=stop_after_attempt(1),  # 減少到1次，避免觸發限流
        wait=wait_exponential(multiplier=1, min=4, max=60),  # 保持等待時間設定
        retry=retry_if_exception_type((
            ConnectionError,
            TimeoutError,
            requests.exceptions.RequestException,
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError
        )),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        從 efinance 獲取原始資料
        
        根據程式碼型別自動選擇 API：
        - 美股：不支援，丟擲異常讓 DataFetcherManager 切換到其他資料來源
        - 普通股票：使用 ef.stock.get_quote_history()
        - ETF 基金：使用 ef.stock.get_quote_history()（ETF 是交易所證券，使用股票 K 線介面）
        
        流程：
        1. 判斷程式碼型別（美股/股票/ETF）
        2. 設定隨機 User-Agent
        3. 執行速率限制（隨機休眠）
        4. 呼叫對應的 efinance API
        5. 處理返回資料
        """
        # 美股不支援，丟擲異常讓 DataFetcherManager 切換到 AkshareFetcher/YfinanceFetcher
        if _is_us_code(stock_code):
            raise DataFetchError(f"EfinanceFetcher 不支援美股 {stock_code}，請使用 AkshareFetcher 或 YfinanceFetcher")
        
        # 根據程式碼型別選擇不同的獲取方法
        if _is_etf_code(stock_code):
            return self._fetch_etf_data(stock_code, start_date, end_date)
        else:
            return self._fetch_stock_data(stock_code, start_date, end_date)
    
    def _fetch_stock_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        獲取普通 A 股歷史資料
        
        資料來源：ef.stock.get_quote_history()
        
        API 引數說明：
        - stock_codes: 股票程式碼
        - beg: 開始日期，格式 'YYYYMMDD'
        - end: 結束日期，格式 'YYYYMMDD'
        - klt: 週期，101=日線
        - fqt: 復權方式，1=前復權
        """
        import efinance as ef
        
        # 防封禁策略 1: 隨機 User-Agent
        self._set_random_user_agent()
        
        # 防封禁策略 2: 強制休眠
        self._enforce_rate_limit()
        
        # 格式化日期（efinance 使用 YYYYMMDD 格式）
        beg_date = start_date.replace('-', '')
        end_date_fmt = end_date.replace('-', '')
        
        logger.info(f"[API呼叫] ef.stock.get_quote_history(stock_codes={stock_code}, "
                   f"beg={beg_date}, end={end_date_fmt}, klt=101, fqt=1)")
        
        api_start = time.time()
        try:
            # 呼叫 efinance 獲取 A 股日線資料
            # klt=101 獲取日線資料
            # fqt=1 獲取前復權資料
            df = _ef_call_with_timeout(
                ef.stock.get_quote_history,
                stock_codes=stock_code,
                beg=beg_date,
                end=end_date_fmt,
                klt=101,  # 日線
                fqt=1,    # 前復權
                timeout=60,
            )
            
            api_elapsed = time.time() - api_start
            
            # 記錄返回資料摘要
            if df is not None and not df.empty:
                logger.info(
                    "[API返回] Eastmoney 歷史K線成功: "
                    f"endpoint={EASTMONEY_HISTORY_ENDPOINT}, stock_code={stock_code}, "
                    f"range={beg_date}~{end_date_fmt}, rows={len(df)}, elapsed={api_elapsed:.2f}s"
                )
                logger.info(f"[API返回] 列名: {list(df.columns)}")
                if '日期' in df.columns:
                    logger.info(f"[API返回] 日期範圍: {df['日期'].iloc[0]} ~ {df['日期'].iloc[-1]}")
                logger.debug(f"[API返回] 最新3條資料:\n{df.tail(3).to_string()}")
            else:
                logger.warning(
                    "[API返回] Eastmoney 歷史K線為空: "
                    f"endpoint={EASTMONEY_HISTORY_ENDPOINT}, stock_code={stock_code}, "
                    f"range={beg_date}~{end_date_fmt}, elapsed={api_elapsed:.2f}s"
                )
            
            return df
            
        except Exception as e:
            api_elapsed = time.time() - api_start
            category, failure_message = self._build_history_failure_message(
                stock_code=stock_code,
                beg_date=beg_date,
                end_date=end_date_fmt,
                exc=e,
                elapsed=api_elapsed,
            )

            if category == "rate_limit_or_anti_bot":
                logger.warning(failure_message)
                raise RateLimitError(f"efinance 可能被限流: {failure_message}") from e

            logger.error(failure_message)
            raise DataFetchError(f"efinance 獲取資料失敗: {failure_message}") from e
    
    def _fetch_etf_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        獲取 ETF 基金歷史資料

        Exchange-traded ETFs have OHLCV data just like regular stocks, so we use
        ef.stock.get_quote_history (the stock K-line API) which returns full
        open/high/low/close/volume data.

        Previously this method used ef.fund.get_quote_history which only returns
        NAV data (單位淨值/累計淨值) without volume or OHLC, causing:
        - Issue #541: 'got an unexpected keyword argument beg'
        - Issue #527: ETF volume/turnover always showing 0

        Args:
            stock_code: ETF code, e.g. '512400', '159883', '515120'
            start_date: Start date, format 'YYYY-MM-DD'
            end_date: End date, format 'YYYY-MM-DD'

        Returns:
            ETF historical OHLCV DataFrame
        """
        import efinance as ef

        # Anti-ban strategy 1: random User-Agent
        self._set_random_user_agent()

        # Anti-ban strategy 2: enforce rate limit
        self._enforce_rate_limit()

        # Format dates (efinance uses YYYYMMDD)
        beg_date = start_date.replace('-', '')
        end_date_fmt = end_date.replace('-', '')

        logger.info(f"[API呼叫] ef.stock.get_quote_history(stock_codes={stock_code}, "
                     f"beg={beg_date}, end={end_date_fmt}, klt=101, fqt=1)  [ETF]")

        api_start = time.time()
        try:
            # ETFs are exchange-traded securities; use the stock API to get full OHLCV data
            df = _ef_call_with_timeout(
                ef.stock.get_quote_history,
                stock_codes=stock_code,
                beg=beg_date,
                end=end_date_fmt,
                klt=101,  # daily
                fqt=1,    # forward-adjusted
                timeout=60,
            )

            api_elapsed = time.time() - api_start

            if df is not None and not df.empty:
                logger.info(
                    "[API返回] Eastmoney 歷史K線成功 [ETF]: "
                    f"endpoint={EASTMONEY_HISTORY_ENDPOINT}, stock_code={stock_code}, "
                    f"range={beg_date}~{end_date_fmt}, rows={len(df)}, elapsed={api_elapsed:.2f}s"
                )
                logger.info(f"[API返回] 列名: {list(df.columns)}")
                if '日期' in df.columns:
                    logger.info(f"[API返回] 日期範圍: {df['日期'].iloc[0]} ~ {df['日期'].iloc[-1]}")
                logger.debug(f"[API返回] 最新3條資料:\n{df.tail(3).to_string()}")
            else:
                logger.warning(
                    "[API返回] Eastmoney 歷史K線為空 [ETF]: "
                    f"endpoint={EASTMONEY_HISTORY_ENDPOINT}, stock_code={stock_code}, "
                    f"range={beg_date}~{end_date_fmt}, elapsed={api_elapsed:.2f}s"
                )

            return df

        except Exception as e:
            api_elapsed = time.time() - api_start
            category, failure_message = self._build_history_failure_message(
                stock_code=stock_code,
                beg_date=beg_date,
                end_date=end_date_fmt,
                exc=e,
                elapsed=api_elapsed,
                is_etf=True,
            )

            if category == "rate_limit_or_anti_bot":
                logger.warning(failure_message)
                raise RateLimitError(f"efinance 可能被限流: {failure_message}") from e

            logger.error(failure_message)
            raise DataFetchError(f"efinance 獲取 ETF 資料失敗: {failure_message}") from e
    
    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        標準化 efinance 資料
        
        efinance 返回的列名（中文）：
        股票名稱, 股票程式碼, 日期, 開盤, 收盤, 最高, 最低, 成交量, 成交額, 振幅, 漲跌幅, 漲跌額, 換手率
        
        需要對映到標準列名：
        date, open, high, low, close, volume, amount, pct_chg
        """
        df = df.copy()
        
        # Column mapping (efinance Chinese column names -> standard English column names)
        column_mapping = {
            '日期': 'date',
            '開盤': 'open',
            '收盤': 'close',
            '最高': 'high',
            '最低': 'low',
            '成交量': 'volume',
            '成交額': 'amount',
            '漲跌幅': 'pct_chg',
            '股票程式碼': 'code',
            '股票名稱': 'name',
        }
        
        # 重新命名列
        df = df.rename(columns=column_mapping)
        
        # Fallback: if OHLC columns are missing (e.g. very old data path), fill from close
        if 'close' in df.columns and 'open' not in df.columns:
            df['open'] = df['close']
            df['high'] = df['close']
            df['low'] = df['close']
            
        # Fill volume and amount if missing
        if 'volume' not in df.columns:
            df['volume'] = 0
        if 'amount' not in df.columns:
            df['amount'] = 0

        
        # 如果沒有 code 列，手動新增
        if 'code' not in df.columns:
            df['code'] = stock_code
        
        # 只保留需要的列
        keep_cols = ['code'] + STANDARD_COLUMNS
        existing_cols = [col for col in keep_cols if col in df.columns]
        df = df[existing_cols]
        
        return df
    
    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        獲取實時行情資料
        
        資料來源：ef.stock.get_realtime_quotes()
        ETF 資料來源：ef.stock.get_realtime_quotes(['ETF'])
        
        Args:
            stock_code: 股票程式碼
            
        Returns:
            UnifiedRealtimeQuote 物件，獲取失敗返回 None
        """
        # ETF 需要單獨請求 ETF 實時行情介面
        if _is_etf_code(stock_code):
            return self._get_etf_realtime_quote(stock_code)

        import efinance as ef
        circuit_breaker = get_realtime_circuit_breaker()
        source_key = "efinance"
        
        # 檢查熔斷器狀態
        if not circuit_breaker.is_available(source_key):
            logger.warning(f"[熔斷] 資料來源 {source_key} 處於熔斷狀態，跳過")
            return None
        
        try:
            # 檢查快取
            current_time = time.time()
            if (_realtime_cache['data'] is not None and 
                current_time - _realtime_cache['timestamp'] < _realtime_cache['ttl']):
                df = _realtime_cache['data']
                cache_age = int(current_time - _realtime_cache['timestamp'])
                logger.debug(f"[快取命中] 實時行情(efinance) - 快取年齡 {cache_age}s/{_realtime_cache['ttl']}s")
            else:
                # 觸發全量重新整理
                logger.info(f"[快取未命中] 觸發全量重新整理 實時行情(efinance)")
                # 防封禁策略
                self._set_random_user_agent()
                self._enforce_rate_limit()
                
                logger.info(f"[API呼叫] ef.stock.get_realtime_quotes() 獲取實時行情...")
                import time as _time
                api_start = _time.time()
                
                # efinance 的實時行情 API (with timeout to avoid indefinite hangs)
                df = _ef_call_with_timeout(ef.stock.get_realtime_quotes)
                
                api_elapsed = _time.time() - api_start
                logger.info(f"[API返回] ef.stock.get_realtime_quotes 成功: 返回 {len(df)} 只股票, 耗時 {api_elapsed:.2f}s")
                circuit_breaker.record_success(source_key)
                
                # 更新快取
                _realtime_cache['data'] = df
                _realtime_cache['timestamp'] = current_time
                logger.info(f"[快取更新] 實時行情(efinance) 快取已重新整理，TTL={_realtime_cache['ttl']}s")
            
            # 查詢指定股票
            # efinance 返回的列名可能是 '股票程式碼' 或 'code'
            code_col = '股票程式碼' if '股票程式碼' in df.columns else 'code'
            row = df[df[code_col] == stock_code]
            if row.empty:
                logger.warning(f"[API返回] 未找到股票 {stock_code} 的實時行情")
                return None
            
            row = row.iloc[0]
            
            # 使用 realtime_types.py 中的統一轉換函式
            # 獲取列名（可能是中文或英文）
            name_col = '股票名稱' if '股票名稱' in df.columns else 'name'
            price_col = '最新價' if '最新價' in df.columns else 'price'
            pct_col = '漲跌幅' if '漲跌幅' in df.columns else 'pct_chg'
            chg_col = '漲跌額' if '漲跌額' in df.columns else 'change'
            vol_col = '成交量' if '成交量' in df.columns else 'volume'
            amt_col = '成交額' if '成交額' in df.columns else 'amount'
            turn_col = '換手率' if '換手率' in df.columns else 'turnover_rate'
            amp_col = '振幅' if '振幅' in df.columns else 'amplitude'
            high_col = '最高' if '最高' in df.columns else 'high'
            low_col = '最低' if '最低' in df.columns else 'low'
            open_col = '開盤' if '開盤' in df.columns else 'open'
            # efinance 也返回量比、市盈率、市值等欄位
            vol_ratio_col = '量比' if '量比' in df.columns else 'volume_ratio'
            pe_col = '市盈率' if '市盈率' in df.columns else 'pe_ratio'
            total_mv_col = '總市值' if '總市值' in df.columns else 'total_mv'
            circ_mv_col = '流通市值' if '流通市值' in df.columns else 'circ_mv'
            
            quote = UnifiedRealtimeQuote(
                code=stock_code,
                name=str(row.get(name_col, '')),
                source=RealtimeSource.EFINANCE,
                price=safe_float(row.get(price_col)),
                change_pct=safe_float(row.get(pct_col)),
                change_amount=safe_float(row.get(chg_col)),
                volume=safe_int(row.get(vol_col)),
                amount=safe_float(row.get(amt_col)),
                turnover_rate=safe_float(row.get(turn_col)),
                amplitude=safe_float(row.get(amp_col)),
                high=safe_float(row.get(high_col)),
                low=safe_float(row.get(low_col)),
                open_price=safe_float(row.get(open_col)),
                volume_ratio=safe_float(row.get(vol_ratio_col)),  # 量比
                pe_ratio=safe_float(row.get(pe_col)),  # 市盈率
                total_mv=safe_float(row.get(total_mv_col)),  # 總市值
                circ_mv=safe_float(row.get(circ_mv_col)),  # 流通市值
            )
            
            logger.info(f"[實時行情-efinance] {stock_code} {quote.name}: 價格={quote.price}, 漲跌={quote.change_pct}%, "
                       f"量比={quote.volume_ratio}, 換手率={quote.turnover_rate}%")
            return quote
            
        except FuturesTimeoutError:
            logger.warning(f"[超時] ef.stock.get_realtime_quotes() 超過 {_EF_CALL_TIMEOUT}s，跳過 {stock_code}")
            circuit_breaker.record_failure(source_key, "timeout")
            return None
        except Exception as e:
            logger.error(f"[API錯誤] 獲取 {stock_code} 實時行情(efinance)失敗: {e}")
            circuit_breaker.record_failure(source_key, str(e))
            return None

    def _get_etf_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        獲取 ETF 實時行情

        efinance 預設實時介面僅返回股票資料，ETF 需要顯式傳入 ['ETF']。
        """
        import efinance as ef
        circuit_breaker = get_realtime_circuit_breaker()
        source_key = "efinance_etf"

        if not circuit_breaker.is_available(source_key):
            logger.warning(f"[熔斷] 資料來源 {source_key} 處於熔斷狀態，跳過")
            return None

        try:
            current_time = time.time()
            if (
                _etf_realtime_cache['data'] is not None and
                current_time - _etf_realtime_cache['timestamp'] < _etf_realtime_cache['ttl']
            ):
                df = _etf_realtime_cache['data']
                cache_age = int(current_time - _etf_realtime_cache['timestamp'])
                logger.debug(f"[快取命中] ETF實時行情(efinance) - 快取年齡 {cache_age}s/{_etf_realtime_cache['ttl']}s")
            else:
                self._set_random_user_agent()
                self._enforce_rate_limit()

                logger.info("[API呼叫] ef.stock.get_realtime_quotes(['ETF']) 獲取ETF實時行情...")
                import time as _time
                api_start = _time.time()
                df = _ef_call_with_timeout(ef.stock.get_realtime_quotes, ['ETF'])
                api_elapsed = _time.time() - api_start

                if df is not None and not df.empty:
                    logger.info(f"[API返回] ETF 實時行情成功: {len(df)} 條, 耗時 {api_elapsed:.2f}s")
                    circuit_breaker.record_success(source_key)
                else:
                    logger.warning(f"[API返回] ETF 實時行情為空, 耗時 {api_elapsed:.2f}s")
                    df = pd.DataFrame()

                _etf_realtime_cache['data'] = df
                _etf_realtime_cache['timestamp'] = current_time

            if df is None or df.empty:
                logger.warning(f"[實時行情] ETF實時行情資料為空(efinance)，跳過 {stock_code}")
                return None

            code_col = '股票程式碼' if '股票程式碼' in df.columns else 'code'
            code_series = df[code_col].astype(str).str.zfill(6)
            target_code = str(stock_code).strip().zfill(6)
            row = df[code_series == target_code]
            if row.empty:
                logger.warning(f"[API返回] 未找到 ETF {stock_code} 的實時行情(efinance)")
                return None

            row = row.iloc[0]
            name_col = '股票名稱' if '股票名稱' in df.columns else 'name'
            price_col = '最新價' if '最新價' in df.columns else 'price'
            pct_col = '漲跌幅' if '漲跌幅' in df.columns else 'pct_chg'
            chg_col = '漲跌額' if '漲跌額' in df.columns else 'change'
            vol_col = '成交量' if '成交量' in df.columns else 'volume'
            amt_col = '成交額' if '成交額' in df.columns else 'amount'
            turn_col = '換手率' if '換手率' in df.columns else 'turnover_rate'
            amp_col = '振幅' if '振幅' in df.columns else 'amplitude'
            high_col = '最高' if '最高' in df.columns else 'high'
            low_col = '最低' if '最低' in df.columns else 'low'
            open_col = '開盤' if '開盤' in df.columns else 'open'

            quote = UnifiedRealtimeQuote(
                code=target_code,
                name=str(row.get(name_col, '')),
                source=RealtimeSource.EFINANCE,
                price=safe_float(row.get(price_col)),
                change_pct=safe_float(row.get(pct_col)),
                change_amount=safe_float(row.get(chg_col)),
                volume=safe_int(row.get(vol_col)),
                amount=safe_float(row.get(amt_col)),
                turnover_rate=safe_float(row.get(turn_col)),
                amplitude=safe_float(row.get(amp_col)),
                high=safe_float(row.get(high_col)),
                low=safe_float(row.get(low_col)),
                open_price=safe_float(row.get(open_col)),
            )

            logger.info(
                f"[ETF實時行情-efinance] {target_code} {quote.name}: "
                f"價格={quote.price}, 漲跌={quote.change_pct}%, 換手率={quote.turnover_rate}%"
            )
            return quote
        except Exception as e:
            logger.error(f"[API錯誤] 獲取 ETF {stock_code} 實時行情(efinance)失敗: {e}")
            circuit_breaker.record_failure(source_key, str(e))
            return None

    def get_main_indices(self, region: str = "cn") -> Optional[List[Dict[str, Any]]]:
        """
        獲取主要指數實時行情 (efinance)，僅支援 A 股
        """
        if region != "cn":
            return None
        import efinance as ef

        indices_map = {
            '000001': ('上證指數', 'sh000001'),
            '399001': ('深證成指', 'sz399001'),
            '399006': ('創業板指', 'sz399006'),
            '000688': ('科創50', 'sh000688'),
            '000016': ('上證50', 'sh000016'),
            '000300': ('滬深300', 'sh000300'),
        }

        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()

            logger.info("[API呼叫] ef.stock.get_realtime_quotes(['滬深系列指數']) 獲取指數行情...")
            import time as _time
            api_start = _time.time()
            df = _ef_call_with_timeout(ef.stock.get_realtime_quotes, ['滬深系列指數'])
            api_elapsed = _time.time() - api_start

            if df is None or df.empty:
                logger.warning(f"[API返回] 指數行情為空, 耗時 {api_elapsed:.2f}s")
                return None

            logger.info(f"[API返回] 指數行情成功: {len(df)} 條, 耗時 {api_elapsed:.2f}s")
            code_col = '股票程式碼' if '股票程式碼' in df.columns else 'code'
            code_series = df[code_col].astype(str).str.zfill(6)

            results: List[Dict[str, Any]] = []
            for code, (name, full_code) in indices_map.items():
                row = df[code_series == code]
                if row.empty:
                    continue
                item = row.iloc[0]

                price_col = '最新價' if '最新價' in df.columns else 'price'
                pct_col = '漲跌幅' if '漲跌幅' in df.columns else 'pct_chg'
                chg_col = '漲跌額' if '漲跌額' in df.columns else 'change'
                open_col = '開盤' if '開盤' in df.columns else 'open'
                high_col = '最高' if '最高' in df.columns else 'high'
                low_col = '最低' if '最低' in df.columns else 'low'
                vol_col = '成交量' if '成交量' in df.columns else 'volume'
                amt_col = '成交額' if '成交額' in df.columns else 'amount'
                amp_col = '振幅' if '振幅' in df.columns else 'amplitude'

                current = safe_float(item.get(price_col, 0))
                change_amount = safe_float(item.get(chg_col, 0))

                results.append({
                    'code': full_code,
                    'name': name,
                    'current': current,
                    'change': change_amount,
                    'change_pct': safe_float(item.get(pct_col, 0)),
                    'open': safe_float(item.get(open_col, 0)),
                    'high': safe_float(item.get(high_col, 0)),
                    'low': safe_float(item.get(low_col, 0)),
                    'prev_close': current - change_amount if current or change_amount else 0,
                    'volume': safe_float(item.get(vol_col, 0)),
                    'amount': safe_float(item.get(amt_col, 0)),
                    'amplitude': safe_float(item.get(amp_col, 0)),
                })

            if results:
                logger.info(f"[efinance] 獲取到 {len(results)} 個指數行情")
            return results if results else None
        except Exception as e:
            logger.error(f"[efinance] 獲取指數行情失敗: {e}")
            return None

    def get_market_stats(self) -> Optional[Dict[str, Any]]:
        """
        獲取市場漲跌統計 (efinance)
        """
        import efinance as ef

        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()

            current_time = time.time()
            if (
                _realtime_cache['data'] is not None and
                current_time - _realtime_cache['timestamp'] < _realtime_cache['ttl']
            ):
                df = _realtime_cache['data']
            else:
                logger.info("[API呼叫] ef.stock.get_realtime_quotes() 獲取市場統計...")
                df = _ef_call_with_timeout(ef.stock.get_realtime_quotes)
                _realtime_cache['data'] = df
                _realtime_cache['timestamp'] = current_time

            if df is None or df.empty:
                logger.warning("[API返回] 市場統計資料為空")
                return None

            return self._calc_market_stats(df)
        except Exception as e:
            logger.error(f"[efinance] 獲取市場統計失敗: {e}")
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
        獲取板塊漲跌榜 (efinance)
        """
        import efinance as ef

        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()

            logger.info("[API呼叫] ef.stock.get_realtime_quotes(['行業板塊']) 獲取板塊行情...")
            df = _ef_call_with_timeout(ef.stock.get_realtime_quotes, ['行業板塊'])
            if df is None or df.empty:
                logger.warning("[efinance] 板塊行情資料為空")
                return None

            change_col = '漲跌幅' if '漲跌幅' in df.columns else 'pct_chg'
            name_col = '股票名稱' if '股票名稱' in df.columns else 'name'
            if change_col not in df.columns or name_col not in df.columns:
                return None

            df[change_col] = pd.to_numeric(df[change_col], errors='coerce')
            df = df.dropna(subset=[change_col])
            top = df.nlargest(n, change_col)
            bottom = df.nsmallest(n, change_col)

            top_sectors = [
                {'name': str(row[name_col]), 'change_pct': float(row[change_col])}
                for _, row in top.iterrows()
            ]
            bottom_sectors = [
                {'name': str(row[name_col]), 'change_pct': float(row[change_col])}
                for _, row in bottom.iterrows()
            ]
            return top_sectors, bottom_sectors
        except Exception as e:
            logger.error(f"[efinance] 獲取板塊排行失敗: {e}")
            return None
    
    def get_base_info(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        獲取股票基本資訊
        
        資料來源：ef.stock.get_base_info()
        包含：市盈率、市淨率、所處行業、總市值、流通市值、ROE、淨利率等
        
        Args:
            stock_code: 股票程式碼
            
        Returns:
            包含基本資訊的字典，獲取失敗返回 None
        """
        import efinance as ef
        
        try:
            # 防封禁策略
            self._set_random_user_agent()
            self._enforce_rate_limit()
            
            logger.info(f"[API呼叫] ef.stock.get_base_info(stock_codes={stock_code}) 獲取基本資訊...")
            import time as _time
            api_start = _time.time()
            
            info = _ef_call_with_timeout(ef.stock.get_base_info, stock_code)
            
            api_elapsed = _time.time() - api_start
            logger.info(f"[API返回] ef.stock.get_base_info 成功, 耗時 {api_elapsed:.2f}s")
            
            if info is None:
                logger.warning(f"[API返回] 未獲取到 {stock_code} 的基本資訊")
                return None
            
            # 轉換為字典
            if isinstance(info, pd.Series):
                return info.to_dict()
            elif isinstance(info, pd.DataFrame):
                if not info.empty:
                    return info.iloc[0].to_dict()
            
            return None
            
        except Exception as e:
            logger.error(f"[API錯誤] 獲取 {stock_code} 基本資訊失敗: {e}")
            return None
    
    def get_belong_board(self, stock_code: str) -> Optional[pd.DataFrame]:
        """
        獲取股票所屬板塊
        
        資料來源：ef.stock.get_belong_board()
        
        Args:
            stock_code: 股票程式碼
            
        Returns:
            所屬板塊 DataFrame，獲取失敗返回 None
        """
        import efinance as ef
        
        try:
            # 防封禁策略
            self._set_random_user_agent()
            self._enforce_rate_limit()
            
            logger.info(f"[API呼叫] ef.stock.get_belong_board(stock_code={stock_code}) 獲取所屬板塊...")
            import time as _time
            api_start = _time.time()
            
            df = _ef_call_with_timeout(ef.stock.get_belong_board, stock_code)
            
            api_elapsed = _time.time() - api_start
            
            if df is not None and not df.empty:
                logger.info(f"[API返回] ef.stock.get_belong_board 成功: 返回 {len(df)} 個板塊, 耗時 {api_elapsed:.2f}s")
                return df
            else:
                logger.warning(f"[API返回] 未獲取到 {stock_code} 的板塊資訊")
                return None
            
        except FuturesTimeoutError:
            logger.warning(f"[超時] ef.stock.get_belong_board({stock_code}) 超過 {_EF_CALL_TIMEOUT}s，跳過")
            return None
        except Exception as e:
            logger.error(f"[API錯誤] 獲取 {stock_code} 所屬板塊失敗: {e}")
            return None
    
    def get_enhanced_data(self, stock_code: str, days: int = 60) -> Dict[str, Any]:
        """
        獲取增強資料（歷史K線 + 實時行情 + 基本資訊）
        
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
            'base_info': None,
            'belong_board': None,
        }
        
        # 獲取日線資料
        try:
            df = self.get_daily_data(stock_code, days=days)
            result['daily_data'] = df
        except Exception as e:
            logger.error(f"獲取 {stock_code} 日線資料失敗: {e}")
        
        # 獲取實時行情
        result['realtime_quote'] = self.get_realtime_quote(stock_code)
        
        # 獲取基本資訊
        result['base_info'] = self.get_base_info(stock_code)
        
        # 獲取所屬板塊
        result['belong_board'] = self.get_belong_board(stock_code)
        
        return result


if __name__ == "__main__":
    # 測試程式碼
    logging.basicConfig(level=logging.DEBUG)
    
    fetcher = EfinanceFetcher()
    
    # 測試普通股票
    print("=" * 50)
    print("測試普通股票資料獲取 (efinance)")
    print("=" * 50)
    try:
        df = fetcher.get_daily_data('600519')  # 茅臺
        print(f"[股票] 獲取成功，共 {len(df)} 條資料")
        print(df.tail())
    except Exception as e:
        print(f"[股票] 獲取失敗: {e}")
    
    # 測試 ETF 基金
    print("\n" + "=" * 50)
    print("測試 ETF 基金資料獲取 (efinance)")
    print("=" * 50)
    try:
        df = fetcher.get_daily_data('512400')  # 有色龍頭ETF
        print(f"[ETF] 獲取成功，共 {len(df)} 條資料")
        print(df.tail())
    except Exception as e:
        print(f"[ETF] 獲取失敗: {e}")
    
    # 測試實時行情
    print("\n" + "=" * 50)
    print("測試實時行情獲取 (efinance)")
    print("=" * 50)
    try:
        quote = fetcher.get_realtime_quote('600519')
        if quote:
            print(f"[實時行情] {quote.name}: 價格={quote.price}, 漲跌幅={quote.change_pct}%")
        else:
            print("[實時行情] 未獲取到資料")
    except Exception as e:
        print(f"[實時行情] 獲取失敗: {e}")
    
    # 測試基本資訊
    print("\n" + "=" * 50)
    print("測試基本資訊獲取 (efinance)")
    print("=" * 50)
    try:
        info = fetcher.get_base_info('600519')
        if info:
            print(f"[基本資訊] 市盈率={info.get('市盈率(動)', 'N/A')}, 市淨率={info.get('市淨率', 'N/A')}")
        else:
            print("[基本資訊] 未獲取到資料")
    except Exception as e:
        print(f"[基本資訊] 獲取失敗: {e}")

    # 測試市場統計 
    print("\n" + "=" * 50)
    print("Testing get_market_stats (efinance)")
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
