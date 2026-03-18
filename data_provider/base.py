# -*- coding: utf-8 -*-
"""
===================================
資料來源基類與管理器
===================================

設計模式：策略模式 (Strategy Pattern)
- BaseFetcher: 抽象基類，定義統一介面
- DataFetcherManager: 策略管理器，實現自動切換

防封禁策略：
1. 每個 Fetcher 內建流控邏輯
2. 失敗自動切換到下一個資料來源
3. 指數退避重試機制
"""

import logging
import random
import time
from threading import BoundedSemaphore, RLock, Thread
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Callable, Optional, List, Tuple, Dict, Any

import pandas as pd
import numpy as np
from src.data.stock_mapping import STOCK_NAME_MAP, is_meaningful_stock_name
from .fundamental_adapter import AkshareFundamentalAdapter

# 配置日誌
logger = logging.getLogger(__name__)


# === 標準化列名定義 ===
STANDARD_COLUMNS = ['date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg']


def unwrap_exception(exc: Exception) -> Exception:
    """
    Follow chained exceptions and return the deepest non-cyclic cause.
    """
    current = exc
    visited = set()

    while current is not None and id(current) not in visited:
        visited.add(id(current))
        next_exc = current.__cause__ or current.__context__
        if next_exc is None:
            break
        current = next_exc

    return current


def summarize_exception(exc: Exception) -> Tuple[str, str]:
    """
    Build a stable summary for logs while preserving the application-layer message.
    """
    root = unwrap_exception(exc)
    error_type = type(root).__name__
    message = str(exc).strip() or str(root).strip() or error_type
    return error_type, " ".join(message.split())


def normalize_stock_code(stock_code: str) -> str:
    """
    Normalize stock code by stripping exchange prefixes/suffixes.

    Accepted formats and their normalized results:
    - '600519'      -> '600519'   (already clean)
    - 'SH600519'    -> '600519'   (strip SH prefix)
    - 'SZ000001'    -> '000001'   (strip SZ prefix)
    - 'BJ920748'    -> '920748'   (strip BJ prefix, BSE)
    - 'sh600519'    -> '600519'   (case-insensitive)
    - '600519.SH'   -> '600519'   (strip .SH suffix)
    - '000001.SZ'   -> '000001'   (strip .SZ suffix)
    - '920748.BJ'   -> '920748'   (strip .BJ suffix, BSE)
    - 'HK00700'     -> 'HK00700'  (keep HK prefix for HK stocks)
    - '1810.HK'     -> 'HK01810'  (normalize HK suffix to canonical prefix form)
    - 'AAPL'        -> 'AAPL'     (keep US stock ticker as-is)

    This function is applied at the DataProviderManager layer so that
    all individual fetchers receive a clean 6-digit code (for A-shares/ETFs).
    """
    code = stock_code.strip()
    upper = code.upper()

    # Normalize HK prefix to a canonical 5-digit form (e.g. hk1810 -> HK01810)
    if upper.startswith('HK') and not upper.startswith('HK.'):
        candidate = upper[2:]
        if candidate.isdigit() and 1 <= len(candidate) <= 5:
            return f"HK{candidate.zfill(5)}"

    # Strip SH/SZ prefix (e.g. SH600519 -> 600519)
    if upper.startswith(('SH', 'SZ')) and not upper.startswith('SH.') and not upper.startswith('SZ.'):
        candidate = code[2:]
        # Only strip if the remainder looks like a valid numeric code
        if candidate.isdigit() and len(candidate) in (5, 6):
            return candidate

    # Strip BJ prefix (e.g. BJ920748 -> 920748)
    if upper.startswith('BJ') and not upper.startswith('BJ.'):
        candidate = code[2:]
        if candidate.isdigit() and len(candidate) == 6:
            return candidate

    # Strip .SH/.SZ/.BJ suffix (e.g. 600519.SH -> 600519, 920748.BJ -> 920748)
    if '.' in code:
        base, suffix = code.rsplit('.', 1)
        if suffix.upper() == 'HK' and base.isdigit() and 1 <= len(base) <= 5:
            return f"HK{base.zfill(5)}"
        if suffix.upper() in ('SH', 'SZ', 'SS', 'BJ') and base.isdigit():
            return base

    return code


ETF_PREFIXES = ("51", "52", "56", "58", "15", "16", "18")


def _is_us_market(code: str) -> bool:
    """判斷是否為美股/美股指數程式碼（不含中文前字尾）。"""
    from .us_index_mapping import is_us_stock_code, is_us_index_code

    normalized = (code or "").strip().upper()
    return is_us_index_code(normalized) or is_us_stock_code(normalized)


def _is_hk_market(code: str) -> bool:
    """
    判定是否為港股程式碼。

    支援 `HK00700` 及純 5 位數字形式（A 股 ETF/股票常見為 6 位）。
    """
    normalized = (code or "").strip().upper()
    if normalized.endswith(".HK"):
        base = normalized[:-3]
        return base.isdigit() and 1 <= len(base) <= 5
    if normalized.startswith("HK"):
        digits = normalized[2:]
        return digits.isdigit() and 1 <= len(digits) <= 5
    if normalized.isdigit() and len(normalized) == 5:
        return True
    return False


def _is_etf_code(code: str) -> bool:
    """判定 A 股 ETF 基金程式碼（保守規則）。"""
    normalized = normalize_stock_code(code)
    return (
        normalized.isdigit()
        and len(normalized) == 6
        and normalized.startswith(ETF_PREFIXES)
    )


def _market_tag(code: str) -> str:
    """返回市場標籤: cn/us/hk."""
    if _is_us_market(code):
        return "us"
    if _is_hk_market(code):
        return "hk"
    return "cn"


def is_bse_code(code: str) -> bool:
    """
    Check if the code is a Beijing Stock Exchange (BSE) A-share code.

    BSE rules:
    - Old format (pre-2024): 8xxxxx (e.g. 838163), 4xxxxx (e.g. 430047)
    - New format (2024+, post full migration Oct 2025): 920xxx+
    Note: 900xxx are Shanghai B-shares, NOT BSE — must return False.
    """
    c = (code or "").strip().split(".")[0]
    if len(c) != 6 or not c.isdigit():
        return False
    return c.startswith(("8", "4")) or c.startswith("92")

def is_st_stock(name: str) -> bool:
    """
    Check if the stock is an ST or *ST stock based on its name.

    ST stocks have special trading rules and typically a ±5% limit.
    """
    n = (name or "").upper()
    return 'ST' in n

def is_kc_cy_stock(code: str) -> bool:
    """
    Check if the stock is a STAR Market (科創板) or ChiNext (創業板) stock based on its code.

    - STAR Market: Codes starting with 688
    - ChiNext: Codes starting with 300
    Both have a ±20% limit.
    """
    c = (code or "").strip().split(".")[0]
    return c.startswith("688") or c.startswith("30")


def canonical_stock_code(code: str) -> str:
    """
    Return the canonical (uppercase) form of a stock code.

    This is a display/storage layer concern, distinct from normalize_stock_code
    which strips exchange prefixes. Apply at system input boundaries to ensure
    consistent case across BOT, WEB UI, API, and CLI paths (Issue #355).

    Examples:
        'aapl'    -> 'AAPL'
        'AAPL'    -> 'AAPL'
        '600519'  -> '600519'  (digits are unchanged)
        'hk00700' -> 'HK00700'
    """
    return (code or "").strip().upper()


class DataFetchError(Exception):
    """資料獲取異常基類"""
    pass


class RateLimitError(DataFetchError):
    """API 速率限制異常"""
    pass


class DataSourceUnavailableError(DataFetchError):
    """資料來源不可用異常"""
    pass


class BaseFetcher(ABC):
    """
    資料來源抽象基類
    
    職責：
    1. 定義統一的資料獲取介面
    2. 提供資料標準化方法
    3. 實現通用的技術指標計算
    
    子類實現：
    - _fetch_raw_data(): 從具體資料來源獲取原始資料
    - _normalize_data(): 將原始資料轉換為標準格式
    """
    
    name: str = "BaseFetcher"
    priority: int = 99  # 優先順序數字越小越優先
    
    @abstractmethod
    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        從資料來源獲取原始資料（子類必須實現）
        
        Args:
            stock_code: 股票程式碼，如 '600519', '000001'
            start_date: 開始日期，格式 'YYYY-MM-DD'
            end_date: 結束日期，格式 'YYYY-MM-DD'
            
        Returns:
            原始資料 DataFrame（列名因資料來源而異）
        """
        pass
    
    @abstractmethod
    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        標準化資料列名（子類必須實現）

        將不同資料來源的列名統一為：
        ['date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg']
        """
        pass

    def get_main_indices(self, region: str = "cn") -> Optional[List[Dict[str, Any]]]:
        """
        獲取主要指數實時行情

        Args:
            region: 市場區域，cn=A股 us=美股

        Returns:
            List[Dict]: 指數列表，每個元素為字典，包含:
                - code: 指數程式碼
                - name: 指數名稱
                - current: 當前點位
                - change: 漲跌點數
                - change_pct: 漲跌幅(%)
                - volume: 成交量
                - amount: 成交額
        """
        return None

    def get_market_stats(self) -> Optional[Dict[str, Any]]:
        """
        獲取市場漲跌統計

        Returns:
            Dict: 包含:
                - up_count: 上漲家數
                - down_count: 下跌家數
                - flat_count: 平盤家數
                - limit_up_count: 漲停家數
                - limit_down_count: 跌停家數
                - total_amount: 兩市成交額
        """
        return None

    def get_sector_rankings(self, n: int = 5) -> Optional[Tuple[List[Dict], List[Dict]]]:
        """
        獲取板塊漲跌榜

        Args:
            n: 返回前n個

        Returns:
            Tuple: (領漲板塊列表, 領跌板塊列表)
        """
        return None

    def get_daily_data(
        self,
        stock_code: str, 
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        days: int = 30
    ) -> pd.DataFrame:
        """
        獲取日線資料（統一入口）
        
        流程：
        1. 計算日期範圍
        2. 呼叫子類獲取原始資料
        3. 標準化列名
        4. 計算技術指標
        
        Args:
            stock_code: 股票程式碼
            start_date: 開始日期（可選）
            end_date: 結束日期（可選，預設今天）
            days: 獲取天數（當 start_date 未指定時使用）
            
        Returns:
            標準化的 DataFrame，包含技術指標
        """
        # 計算日期範圍
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')
        
        if start_date is None:
            # 預設獲取最近 30 個交易日（按日曆日估算，多取一些）
            from datetime import timedelta
            start_dt = datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=days * 2)
            start_date = start_dt.strftime('%Y-%m-%d')

        request_start = time.time()
        logger.info(f"[{self.name}] 開始獲取 {stock_code} 日線資料: 範圍={start_date} ~ {end_date}")
        
        try:
            # Step 1: 獲取原始資料
            raw_df = self._fetch_raw_data(stock_code, start_date, end_date)
            
            if raw_df is None or raw_df.empty:
                raise DataFetchError(f"[{self.name}] 未獲取到 {stock_code} 的資料")
            
            # Step 2: 標準化列名
            df = self._normalize_data(raw_df, stock_code)
            
            # Step 3: 資料清洗
            df = self._clean_data(df)
            
            # Step 4: 計算技術指標
            df = self._calculate_indicators(df)

            elapsed = time.time() - request_start
            logger.info(
                f"[{self.name}] {stock_code} 獲取成功: 範圍={start_date} ~ {end_date}, "
                f"rows={len(df)}, elapsed={elapsed:.2f}s"
            )
            return df
            
        except Exception as e:
            elapsed = time.time() - request_start
            error_type, error_reason = summarize_exception(e)
            logger.error(
                f"[{self.name}] {stock_code} 獲取失敗: 範圍={start_date} ~ {end_date}, "
                f"error_type={error_type}, elapsed={elapsed:.2f}s, reason={error_reason}"
            )
            raise DataFetchError(f"[{self.name}] {stock_code}: {error_reason}") from e
    
    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        資料清洗
        
        處理：
        1. 確保日期列格式正確
        2. 數值型別轉換
        3. 去除空值行
        4. 按日期排序
        """
        df = df.copy()
        
        # 確保日期列為 datetime 型別
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
        
        # 數值列型別轉換
        numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 去除關鍵列為空的行
        df = df.dropna(subset=['close', 'volume'])
        
        # 按日期升序排序
        df = df.sort_values('date', ascending=True).reset_index(drop=True)
        
        return df
    
    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        計算技術指標
        
        計算指標：
        - MA5, MA10, MA20: 移動平均線
        - Volume_Ratio: 量比（今日成交量 / 5日平均成交量）
        """
        df = df.copy()
        
        # 移動平均線
        df['ma5'] = df['close'].rolling(window=5, min_periods=1).mean()
        df['ma10'] = df['close'].rolling(window=10, min_periods=1).mean()
        df['ma20'] = df['close'].rolling(window=20, min_periods=1).mean()
        
        # 量比：當日成交量 / 5日平均成交量
        # 注意：此處的 volume_ratio 是“日線成交量 / 前5日均量(shift 1)”的相對倍數，
        # 與部分交易軟體口徑的“分時量比（同一時刻對比）”不同，含義更接近“放量倍數”。
        # 該行為目前保留（按需求不改邏輯）。
        avg_volume_5 = df['volume'].rolling(window=5, min_periods=1).mean()
        df['volume_ratio'] = df['volume'] / avg_volume_5.shift(1)
        df['volume_ratio'] = df['volume_ratio'].fillna(1.0)
        
        # 保留2位小數
        for col in ['ma5', 'ma10', 'ma20', 'volume_ratio']:
            if col in df.columns:
                df[col] = df[col].round(2)
        
        return df
    
    @staticmethod
    def random_sleep(min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
        """
        智慧隨機休眠（Jitter）
        
        防封禁策略：模擬人類行為的隨機延遲
        在請求之間加入不規則的等待時間
        """
        sleep_time = random.uniform(min_seconds, max_seconds)
        logger.debug(f"隨機休眠 {sleep_time:.2f} 秒...")
        time.sleep(sleep_time)


class DataFetcherManager:
    """
    資料來源策略管理器
    
    職責：
    1. 管理多個資料來源（按優先順序排序）
    2. 自動故障切換（Failover）
    3. 提供統一的資料獲取介面
    
    切換策略：
    - 優先使用高優先順序資料來源
    - 失敗後自動切換到下一個
    - 所有資料來源都失敗時丟擲異常
    """
    
    def __init__(self, fetchers: Optional[List[BaseFetcher]] = None):
        """
        初始化管理器
        
        Args:
            fetchers: 資料來源列表（可選，預設按優先順序自動建立）
        """
        self._fetchers: List[BaseFetcher] = []
        
        if fetchers:
            # 按優先順序排序
            self._fetchers = sorted(fetchers, key=lambda f: f.priority)
        else:
            # 預設資料來源將在首次使用時延遲載入
            self._init_default_fetchers()
        self._fundamental_adapter = AkshareFundamentalAdapter()
        self._fundamental_cache: Dict[str, Dict[str, Any]] = {}
        self._fundamental_cache_lock = RLock()
        self._fundamental_timeout_worker_limit = 8
        self._fundamental_timeout_slots = BoundedSemaphore(self._fundamental_timeout_worker_limit)

    def _get_fundamental_cache_key(self, stock_code: str, budget_seconds: Optional[float] = None) -> str:
        """生成基本面快取 key（包含預算分桶以避免低預算結果汙染高預算請求）。"""
        normalized_code = normalize_stock_code(stock_code)
        if budget_seconds is None:
            return f"{normalized_code}|budget=default"
        try:
            budget = max(0.0, float(budget_seconds))
        except (TypeError, ValueError):
            budget = 0.0
        # 100ms bucket to balance cache reuse and scenario isolation.
        budget_bucket = int(round(budget * 10))
        return f"{normalized_code}|budget={budget_bucket}"

    def _prune_fundamental_cache(self, ttl_seconds: int, max_entries: int) -> None:
        """Prune expired and overflow fundamental cache items."""
        with self._fundamental_cache_lock:
            if not self._fundamental_cache:
                return

            now_ts = time.time()
            if ttl_seconds > 0:
                cache_items = list(self._fundamental_cache.items())
                expired_keys = [
                    key
                    for key, value in cache_items
                    if now_ts - float(value.get("ts", 0)) > ttl_seconds
                ]
                for key in expired_keys:
                    self._fundamental_cache.pop(key, None)

            if max_entries > 0 and len(self._fundamental_cache) > max_entries:
                overflow = len(self._fundamental_cache) - max_entries
                sorted_items = sorted(
                    list(self._fundamental_cache.items()),
                    key=lambda item: float(item[1].get("ts", 0)),
                )
                for key, _ in sorted_items[:overflow]:
                    self._fundamental_cache.pop(key, None)

    @staticmethod
    def _is_missing_board_value(value: Any) -> bool:
        """Return True when a board field value should be treated as missing."""
        if value is None:
            return True
        try:
            if pd.isna(value):
                return True
        except Exception:
            pass
        text = str(value).strip()
        return text == "" or text.lower() in {"nan", "none", "null", "na", "n/a"}

    @staticmethod
    def _normalize_belong_boards(raw_data: Any) -> List[Dict[str, Any]]:
        """Normalize belong-board results from heterogeneous providers."""
        if DataFetcherManager._is_missing_board_value(raw_data):
            return []

        normalized: List[Dict[str, Any]] = []
        dedupe = set()

        if isinstance(raw_data, pd.DataFrame):
            if raw_data.empty:
                return []
            name_col = next(
                (
                    col
                    for col in raw_data.columns
                    if str(col) in {"板塊名稱", "板塊", "所屬板塊", "板塊名", "name", "industry"}
                ),
                None,
            )
            code_col = next(
                (
                    col
                    for col in raw_data.columns
                    if str(col) in {"板塊程式碼", "程式碼", "code"}
                ),
                None,
            )
            type_col = next(
                (
                    col
                    for col in raw_data.columns
                    if str(col) in {"板塊型別", "類別", "type"}
                ),
                None,
            )
            if name_col is None:
                return []
            for _, row in raw_data.iterrows():
                board_name_raw = row.get(name_col, "")
                if DataFetcherManager._is_missing_board_value(board_name_raw):
                    continue
                board_name = str(board_name_raw).strip()
                if board_name in dedupe:
                    continue
                dedupe.add(board_name)
                item = {"name": board_name}
                if code_col is not None:
                    board_code_raw = row.get(code_col, "")
                    if not DataFetcherManager._is_missing_board_value(board_code_raw):
                        item["code"] = str(board_code_raw).strip()
                if type_col is not None:
                    board_type_raw = row.get(type_col, "")
                    if not DataFetcherManager._is_missing_board_value(board_type_raw):
                        item["type"] = str(board_type_raw).strip()
                normalized.append(item)
            return normalized

        if isinstance(raw_data, dict):
            raw_data = [raw_data]

        if isinstance(raw_data, (list, tuple, set)):
            for item in raw_data:
                if isinstance(item, dict):
                    board_name_raw = (
                        item.get("name")
                        or item.get("board_name")
                        or item.get("板塊名稱")
                        or item.get("板塊")
                        or item.get("所屬板塊")
                        or item.get("板塊名")
                        or item.get("industry")
                        or item.get("行業")
                    )
                    if DataFetcherManager._is_missing_board_value(board_name_raw):
                        continue
                    board_name = str(board_name_raw).strip()
                    if board_name in dedupe:
                        continue
                    dedupe.add(board_name)
                    normalized_item: Dict[str, Any] = {"name": board_name}
                    code_raw = (
                        item.get("code")
                        or item.get("板塊程式碼")
                        or item.get("程式碼")
                    )
                    if not DataFetcherManager._is_missing_board_value(code_raw):
                        normalized_item["code"] = str(code_raw).strip()
                    type_raw = (
                        item.get("type")
                        or item.get("板塊型別")
                        or item.get("類別")
                    )
                    if not DataFetcherManager._is_missing_board_value(type_raw):
                        normalized_item["type"] = str(type_raw).strip()
                    normalized.append(normalized_item)
                    continue
                if DataFetcherManager._is_missing_board_value(item):
                    continue
                board_name = str(item).strip()
                if board_name in dedupe:
                    continue
                dedupe.add(board_name)
                normalized.append({"name": board_name})
            return normalized

        if not DataFetcherManager._is_missing_board_value(raw_data):
            board_name = str(raw_data).strip()
            return [{"name": board_name}]
        return []
    
    def _init_default_fetchers(self) -> None:
        """
        初始化預設資料來源列表

        優先順序動態調整邏輯：
        - 如果配置了 TUSHARE_TOKEN：Tushare 優先順序提升為 0（最高）
        - 否則按預設優先順序：
          0. EfinanceFetcher (Priority 0) - 最高優先順序
          1. AkshareFetcher (Priority 1)
          2. PytdxFetcher (Priority 2) - 通達信
          2. TushareFetcher (Priority 2)
          3. BaostockFetcher (Priority 3)
          4. YfinanceFetcher (Priority 4)
        """
        from .efinance_fetcher import EfinanceFetcher
        from .akshare_fetcher import AkshareFetcher
        from .tushare_fetcher import TushareFetcher
        from .pytdx_fetcher import PytdxFetcher
        from .baostock_fetcher import BaostockFetcher
        from .yfinance_fetcher import YfinanceFetcher
        # 建立所有資料來源例項（優先順序在各 Fetcher 的 __init__ 中確定）
        efinance = EfinanceFetcher()
        akshare = AkshareFetcher()
        tushare = TushareFetcher()  # 會根據 Token 配置自動調整優先順序
        pytdx = PytdxFetcher()      # 通達信資料來源（可配 PYTDX_HOST/PYTDX_PORT）
        baostock = BaostockFetcher()
        yfinance = YfinanceFetcher()

        # 初始化資料來源列表
        self._fetchers = [
            efinance,
            akshare,
            tushare,
            pytdx,
            baostock,
            yfinance,
        ]

        # 按優先順序排序（Tushare 如果配置了 Token 且初始化成功，優先順序為 0）
        self._fetchers.sort(key=lambda f: f.priority)

        # 構建優先順序說明
        priority_info = ", ".join([f"{f.name}(P{f.priority})" for f in self._fetchers])
        logger.info(f"已初始化 {len(self._fetchers)} 個資料來源（按優先順序）: {priority_info}")
    
    def add_fetcher(self, fetcher: BaseFetcher) -> None:
        """新增資料來源並重新排序"""
        self._fetchers.append(fetcher)
        self._fetchers.sort(key=lambda f: f.priority)
    
    def get_daily_data(
        self, 
        stock_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        days: int = 30
    ) -> Tuple[pd.DataFrame, str]:
        """
        獲取日線資料（自動切換資料來源）
        
        故障切換策略：
        1. 美股指數/美股股票直接路由到 YfinanceFetcher
        2. 其他程式碼從最高優先順序資料來源開始嘗試
        3. 捕獲異常後自動切換到下一個
        4. 記錄每個資料來源的失敗原因
        5. 所有資料來源失敗後丟擲詳細異常
        
        Args:
            stock_code: 股票程式碼
            start_date: 開始日期
            end_date: 結束日期
            days: 獲取天數
            
        Returns:
            Tuple[DataFrame, str]: (資料, 成功的資料來源名稱)
            
        Raises:
            DataFetchError: 所有資料來源都失敗時丟擲
        """
        from .us_index_mapping import is_us_index_code, is_us_stock_code

        # Normalize code (strip SH/SZ prefix etc.)
        stock_code = normalize_stock_code(stock_code)

        errors = []
        total_fetchers = len(self._fetchers)
        request_start = time.time()

        # 快速路徑：美股指數與美股股票直接路由到 YfinanceFetcher
        if is_us_index_code(stock_code) or is_us_stock_code(stock_code):
            for attempt, fetcher in enumerate(self._fetchers, start=1):
                if fetcher.name == "YfinanceFetcher":
                    try:
                        logger.info(
                            f"[資料來源嘗試 {attempt}/{total_fetchers}] [{fetcher.name}] "
                            f"美股/美股指數 {stock_code} 直接路由..."
                        )
                        df = fetcher.get_daily_data(
                            stock_code=stock_code,
                            start_date=start_date,
                            end_date=end_date,
                            days=days,
                        )
                        if df is not None and not df.empty:
                            elapsed = time.time() - request_start
                            logger.info(
                                f"[資料來源完成] {stock_code} 使用 [{fetcher.name}] 獲取成功: "
                                f"rows={len(df)}, elapsed={elapsed:.2f}s"
                            )
                            return df, fetcher.name
                    except Exception as e:
                        error_type, error_reason = summarize_exception(e)
                        error_msg = f"[{fetcher.name}] ({error_type}) {error_reason}"
                        logger.warning(
                            f"[資料來源失敗 {attempt}/{total_fetchers}] [{fetcher.name}] {stock_code}: "
                            f"error_type={error_type}, reason={error_reason}"
                        )
                        errors.append(error_msg)
                    break
            # YfinanceFetcher failed or not found
            error_summary = f"美股/美股指數 {stock_code} 獲取失敗:\n" + "\n".join(errors)
            elapsed = time.time() - request_start
            logger.error(f"[資料來源終止] {stock_code} 獲取失敗: elapsed={elapsed:.2f}s\n{error_summary}")
            raise DataFetchError(error_summary)

        for attempt, fetcher in enumerate(self._fetchers, start=1):
            try:
                logger.info(f"[資料來源嘗試 {attempt}/{total_fetchers}] [{fetcher.name}] 獲取 {stock_code}...")
                df = fetcher.get_daily_data(
                    stock_code=stock_code,
                    start_date=start_date,
                    end_date=end_date,
                    days=days
                )
                
                if df is not None and not df.empty:
                    elapsed = time.time() - request_start
                    logger.info(
                        f"[資料來源完成] {stock_code} 使用 [{fetcher.name}] 獲取成功: "
                        f"rows={len(df)}, elapsed={elapsed:.2f}s"
                    )
                    return df, fetcher.name
                    
            except Exception as e:
                error_type, error_reason = summarize_exception(e)
                error_msg = f"[{fetcher.name}] ({error_type}) {error_reason}"
                logger.warning(
                    f"[資料來源失敗 {attempt}/{total_fetchers}] [{fetcher.name}] {stock_code}: "
                    f"error_type={error_type}, reason={error_reason}"
                )
                errors.append(error_msg)
                if attempt < total_fetchers:
                    next_fetcher = self._fetchers[attempt]
                    logger.info(f"[資料來源切換] {stock_code}: [{fetcher.name}] -> [{next_fetcher.name}]")
                # 繼續嘗試下一個資料來源
                continue
        
        # 所有資料來源都失敗
        error_summary = f"所有資料來源獲取 {stock_code} 失敗:\n" + "\n".join(errors)
        elapsed = time.time() - request_start
        logger.error(f"[資料來源終止] {stock_code} 獲取失敗: elapsed={elapsed:.2f}s\n{error_summary}")
        raise DataFetchError(error_summary)
    
    @property
    def available_fetchers(self) -> List[str]:
        """返回可用資料來源名稱列表"""
        return [f.name for f in self._fetchers]
    
    def prefetch_realtime_quotes(self, stock_codes: List[str]) -> int:
        """
        批次預取實時行情資料（在分析開始前呼叫）
        
        策略：
        1. 檢查優先順序中是否包含全量拉取資料來源（efinance/akshare_em）
        2. 如果不包含，跳過預取（新浪/騰訊是單股票查詢，無需預取）
        3. 如果自選股數量 >= 5 且使用全量資料來源，則預取填充快取
        
        這樣做的好處：
        - 使用新浪/騰訊時：每隻股票獨立查詢，無全量拉取問題
        - 使用 efinance/東財時：預取一次，後續快取命中
        
        Args:
            stock_codes: 待分析的股票程式碼列表
            
        Returns:
            預取的股票數量（0 表示跳過預取）
        """
        # Normalize all codes
        stock_codes = [normalize_stock_code(c) for c in stock_codes]

        from src.config import get_config

        config = get_config()

        # Issue #455: PREFETCH_REALTIME_QUOTES=false 可禁用預取，避免全市場拉取
        if not getattr(config, "prefetch_realtime_quotes", True):
            logger.debug("[預取] PREFETCH_REALTIME_QUOTES=false，跳過批次預取")
            return 0

        # 如果實時行情被禁用，跳過預取
        if not config.enable_realtime_quote:
            logger.debug("[預取] 實時行情功能已禁用，跳過預取")
            return 0
        
        # 檢查優先順序中是否包含全量拉取資料來源
        # 注意：新增全量介面（如 tushare_realtime）時需同步更新此列表
        # 全量介面特徵：一次 API 呼叫拉取全市場 5000+ 股票資料
        priority = config.realtime_source_priority.lower()
        bulk_sources = ['efinance', 'akshare_em', 'tushare']  # 全量介面列表
        
        # 如果優先順序中前兩個都不是全量資料來源，跳過預取
        # 因為新浪/騰訊是單股票查詢，不需要預取
        priority_list = [s.strip() for s in priority.split(',')]
        first_bulk_source_index = None
        for i, source in enumerate(priority_list):
            if source in bulk_sources:
                first_bulk_source_index = i
                break
        
        # 如果沒有全量資料來源，或者全量資料來源排在第 3 位之後，跳過預取
        if first_bulk_source_index is None or first_bulk_source_index >= 2:
            logger.info(f"[預取] 當前優先順序使用輕量級資料來源(sina/tencent)，無需預取")
            return 0
        
        # 如果股票數量少於 5 個，不進行批次預取（逐個查詢更高效）
        if len(stock_codes) < 5:
            logger.info(f"[預取] 股票數量 {len(stock_codes)} < 5，跳過批次預取")
            return 0
        
        logger.info(f"[預取] 開始批次預取實時行情，共 {len(stock_codes)} 只股票...")
        
        # 嘗試透過 efinance 或 akshare 預取
        # 只需要呼叫一次 get_realtime_quote，快取機制會自動拉取全市場資料
        try:
            # 用第一隻股票觸發全量拉取
            first_code = stock_codes[0]
            quote = self.get_realtime_quote(first_code)
            
            if quote:
                logger.info(f"[預取] 批次預取完成，快取已填充")
                return len(stock_codes)
            else:
                logger.warning(f"[預取] 批次預取失敗，將使用逐個查詢模式")
                return 0
                
        except Exception as e:
            logger.error(f"[預取] 批次預取異常: {e}")
            return 0
    
    def get_realtime_quote(self, stock_code: str):
        """
        獲取實時行情資料（自動故障切換）
        
        故障切換策略（按配置的優先順序）：
        1. 美股：使用 YfinanceFetcher.get_realtime_quote()
        2. EfinanceFetcher.get_realtime_quote()
        3. AkshareFetcher.get_realtime_quote(source="em")  - 東財
        4. AkshareFetcher.get_realtime_quote(source="sina") - 新浪
        5. AkshareFetcher.get_realtime_quote(source="tencent") - 騰訊
        6. 返回 None（降級兜底）
        
        Args:
            stock_code: 股票程式碼
            
        Returns:
            UnifiedRealtimeQuote 物件，所有資料來源都失敗則返回 None
        """
        # Normalize code (strip SH/SZ prefix etc.)
        stock_code = normalize_stock_code(stock_code)

        from .akshare_fetcher import _is_us_code
        from .us_index_mapping import is_us_index_code
        from src.config import get_config

        config = get_config()

        # 如果實時行情功能被禁用，直接返回 None
        if not config.enable_realtime_quote:
            logger.debug(f"[實時行情] 功能已禁用，跳過 {stock_code}")
            return None

        # 美股指數由 YfinanceFetcher 處理（在美股股票檢查之前）
        if is_us_index_code(stock_code):
            for fetcher in self._fetchers:
                if fetcher.name == "YfinanceFetcher":
                    if hasattr(fetcher, 'get_realtime_quote'):
                        try:
                            quote = fetcher.get_realtime_quote(stock_code)
                            if quote is not None:
                                logger.info(f"[實時行情] 美股指數 {stock_code} 成功獲取 (來源: yfinance)")
                                return quote
                        except Exception as e:
                            logger.warning(f"[實時行情] 美股指數 {stock_code} 獲取失敗: {e}")
                    break
            logger.warning(f"[實時行情] 美股指數 {stock_code} 無可用資料來源")
            return None

        # 美股單獨處理，使用 YfinanceFetcher
        if _is_us_code(stock_code):
            for fetcher in self._fetchers:
                if fetcher.name == "YfinanceFetcher":
                    if hasattr(fetcher, 'get_realtime_quote'):
                        try:
                            quote = fetcher.get_realtime_quote(stock_code)
                            if quote is not None:
                                logger.info(f"[實時行情] 美股 {stock_code} 成功獲取 (來源: yfinance)")
                                return quote
                        except Exception as e:
                            logger.warning(f"[實時行情] 美股 {stock_code} 獲取失敗: {e}")
                    break
            logger.warning(f"[實時行情] 美股 {stock_code} 無可用資料來源")
            return None

        # 港股實時行情只走港股專用入口，避免按 A 股 source_priority
        # 反覆觸發同一個 ak.stock_hk_spot_em() 介面。
        if _is_hk_market(stock_code):
            for fetcher in self._fetchers:
                if fetcher.name != "AkshareFetcher":
                    continue
                if not hasattr(fetcher, 'get_realtime_quote'):
                    break
                try:
                    quote = fetcher.get_realtime_quote(stock_code, source="hk")
                    if quote is not None and quote.has_basic_data():
                        logger.info(f"[實時行情] 港股 {stock_code} 成功獲取 (來源: akshare_hk)")
                        return quote
                except Exception as e:
                    logger.warning(f"[實時行情] 港股 {stock_code} 獲取失敗: {e}")
                break

            logger.warning(f"[實時行情] 港股 {stock_code} 無可用資料來源")
            return None
        
        # 獲取配置的資料來源優先順序
        source_priority = config.realtime_source_priority.split(',')
        
        errors = []
        # primary_quote holds the first successful result; we may supplement
        # missing fields (volume_ratio, turnover_rate, etc.) from later sources.
        primary_quote = None
        
        for source in source_priority:
            source = source.strip().lower()
            
            try:
                quote = None
                
                if source == "efinance":
                    # 嘗試 EfinanceFetcher
                    for fetcher in self._fetchers:
                        if fetcher.name == "EfinanceFetcher":
                            if hasattr(fetcher, 'get_realtime_quote'):
                                quote = fetcher.get_realtime_quote(stock_code)
                            break
                
                elif source == "akshare_em":
                    # 嘗試 AkshareFetcher 東財資料來源
                    for fetcher in self._fetchers:
                        if fetcher.name == "AkshareFetcher":
                            if hasattr(fetcher, 'get_realtime_quote'):
                                quote = fetcher.get_realtime_quote(stock_code, source="em")
                            break
                
                elif source == "akshare_sina":
                    # 嘗試 AkshareFetcher 新浪資料來源
                    for fetcher in self._fetchers:
                        if fetcher.name == "AkshareFetcher":
                            if hasattr(fetcher, 'get_realtime_quote'):
                                quote = fetcher.get_realtime_quote(stock_code, source="sina")
                            break
                
                elif source in ("tencent", "akshare_qq"):
                    # 嘗試 AkshareFetcher 騰訊資料來源
                    for fetcher in self._fetchers:
                        if fetcher.name == "AkshareFetcher":
                            if hasattr(fetcher, 'get_realtime_quote'):
                                quote = fetcher.get_realtime_quote(stock_code, source="tencent")
                            break
                
                elif source == "tushare":
                    # 嘗試 TushareFetcher（需要 Tushare Pro 積分）
                    for fetcher in self._fetchers:
                        if fetcher.name == "TushareFetcher":
                            if hasattr(fetcher, 'get_realtime_quote'):
                                quote = fetcher.get_realtime_quote(stock_code)
                            break
                
                if quote is not None and quote.has_basic_data():
                    if primary_quote is None:
                        # First successful source becomes primary
                        primary_quote = quote
                        logger.info(f"[實時行情] {stock_code} 成功獲取 (來源: {source})")
                        # If all key supplementary fields are present, return early
                        if not self._quote_needs_supplement(primary_quote):
                            return primary_quote
                        # Otherwise, continue to try later sources for missing fields
                        logger.debug(f"[實時行情] {stock_code} 部分欄位缺失，嘗試從後續資料來源補充")
                        supplement_attempts = 0
                    else:
                        # Supplement missing fields from this source (limit attempts)
                        supplement_attempts += 1
                        if supplement_attempts > 1:
                            logger.debug(f"[實時行情] {stock_code} 補充嘗試已達上限，停止繼續")
                            break
                        merged = self._merge_quote_fields(primary_quote, quote)
                        if merged:
                            logger.info(f"[實時行情] {stock_code} 從 {source} 補充了缺失欄位: {merged}")
                        # Stop supplementing once all key fields are filled
                        if not self._quote_needs_supplement(primary_quote):
                            break
                    
            except Exception as e:
                error_msg = f"[{source}] 失敗: {str(e)}"
                logger.warning(error_msg)
                errors.append(error_msg)
                continue
        
        # Return primary even if some fields are still missing
        if primary_quote is not None:
            return primary_quote

        # 所有資料來源都失敗，返回 None（降級兜底）
        if errors:
            logger.warning(f"[實時行情] {stock_code} 所有資料來源均失敗，降級處理: {'; '.join(errors)}")
        else:
            logger.warning(f"[實時行情] {stock_code} 無可用資料來源")
        
        return None

    # Fields worth supplementing from secondary sources when the primary
    # source returns None for them. Ordered by importance.
    _SUPPLEMENT_FIELDS = [
        'volume_ratio', 'turnover_rate',
        'pe_ratio', 'pb_ratio', 'total_mv', 'circ_mv',
        'amplitude',
    ]

    @classmethod
    def _quote_needs_supplement(cls, quote) -> bool:
        """Check if any key supplementary field is still None."""
        for f in cls._SUPPLEMENT_FIELDS:
            if getattr(quote, f, None) is None:
                return True
        return False

    @classmethod
    def _merge_quote_fields(cls, primary, secondary) -> list:
        """
        Copy non-None fields from *secondary* into *primary* where
        *primary* has None. Returns list of field names that were filled.
        """
        filled = []
        for f in cls._SUPPLEMENT_FIELDS:
            if getattr(primary, f, None) is None:
                val = getattr(secondary, f, None)
                if val is not None:
                    setattr(primary, f, val)
                    filled.append(f)
        return filled

    def get_chip_distribution(self, stock_code: str):
        """
        獲取籌碼分佈資料（帶熔斷和多資料來源降級）

        策略：
        1. 檢查配置開關
        2. 檢查熔斷器狀態
        3. 依次嘗試多個資料來源：資料來源優先順序與獲取daily的資料優先順序一致
        4. 所有資料來源失敗則返回 None（降級兜底）

        Args:
            stock_code: 股票程式碼

        Returns:
            ChipDistribution 物件，失敗則返回 None
        """
        # Normalize code (strip SH/SZ prefix etc.)
        stock_code = normalize_stock_code(stock_code)

        from .realtime_types import get_chip_circuit_breaker
        from src.config import get_config

        config = get_config()

        # 如果籌碼分佈功能被禁用，直接返回 None
        if not config.enable_chip_distribution:
            logger.debug(f"[籌碼分佈] 功能已禁用，跳過 {stock_code}")
            return None

        circuit_breaker = get_chip_circuit_breaker()

        # 直接遍歷管理器已經按 priority 排好序的資料來源列表
        for fetcher in self._fetchers:
            # 只處理實現了籌碼分佈邏輯的資料來源
            if not hasattr(fetcher, 'get_chip_distribution'):
                continue
            
            fetcher_name = fetcher.name
            # 動態生成熔斷器的 key，例如 "TushareFetcher" -> "tushare_chip"
            source_key = f"{fetcher_name.replace('Fetcher', '').lower()}_chip"

            # 檢查熔斷器狀態
            if not circuit_breaker.is_available(source_key):
                logger.debug(f"[熔斷] {fetcher_name} 籌碼介面處於熔斷狀態，嘗試下一個")
                continue

            try:
                chip = fetcher.get_chip_distribution(stock_code)
                if chip is not None:
                    circuit_breaker.record_success(source_key)
                    logger.info(f"[籌碼分佈] {stock_code} 成功獲取 (來源: {fetcher_name})")
                    return chip
            except Exception as e:
                logger.warning(f"[籌碼分佈] {fetcher_name} 獲取 {stock_code} 失敗: {e}")
                circuit_breaker.record_failure(source_key, str(e))
                continue

        logger.warning(f"[籌碼分佈] {stock_code} 所有資料來源均失敗")
        return None

    def get_stock_name(self, stock_code: str, allow_realtime: bool = True) -> Optional[str]:
        """
        獲取股票中文名稱（自動切換資料來源）
        
        嘗試從多個資料來源獲取股票名稱：
        1. 先從實時行情快取中獲取（如果有）
        2. 依次嘗試各個資料來源的 get_stock_name 方法
        3. 最後嘗試讓大模型透過搜尋獲取（需要外部呼叫）
        
        Args:
            stock_code: 股票程式碼
            allow_realtime: Whether to query realtime quote first. Set False when
                caller only wants lightweight prefetch without triggering heavy
                realtime source calls.
            
        Returns:
            股票中文名稱，所有資料來源都失敗則返回 None
        """
        # Normalize code (strip SH/SZ prefix etc.)
        stock_code = normalize_stock_code(stock_code)
        static_name = STOCK_NAME_MAP.get(stock_code)

        # 1. 先檢查快取
        if hasattr(self, '_stock_name_cache') and stock_code in self._stock_name_cache:
            return self._stock_name_cache[stock_code]
        
        # 初始化快取
        if not hasattr(self, '_stock_name_cache'):
            self._stock_name_cache = {}
        
        # 2. 嘗試從實時行情中獲取（最快，可按需禁用）
        if allow_realtime:
            quote = self.get_realtime_quote(stock_code)
            if quote and hasattr(quote, 'name') and is_meaningful_stock_name(getattr(quote, 'name', ''), stock_code):
                name = quote.name
                self._stock_name_cache[stock_code] = name
                logger.info(f"[股票名稱] 從實時行情獲取: {stock_code} -> {name}")
                return name

        if is_meaningful_stock_name(static_name, stock_code):
            self._stock_name_cache[stock_code] = static_name
            return static_name

        # 3. 依次嘗試各個資料來源
        for fetcher in self._fetchers:
            if hasattr(fetcher, 'get_stock_name'):
                try:
                    name = fetcher.get_stock_name(stock_code)
                    if is_meaningful_stock_name(name, stock_code):
                        self._stock_name_cache[stock_code] = name
                        logger.info(f"[股票名稱] 從 {fetcher.name} 獲取: {stock_code} -> {name}")
                        return name
                except Exception as e:
                    logger.debug(f"[股票名稱] {fetcher.name} 獲取失敗: {e}")
                    continue

        # 4. 所有資料來源都失敗
        logger.warning(f"[股票名稱] 所有資料來源都無法獲取 {stock_code} 的名稱")
        return ""

    def get_belong_boards(self, stock_code: str) -> List[Dict[str, Any]]:
        """
        Get stock membership boards through capability probing.

        Keep this at manager layer to avoid changing BaseFetcher abstraction.
        """
        stock_code = normalize_stock_code(stock_code)
        if _market_tag(stock_code) != "cn":
            return []
        for fetcher in self._fetchers:
            if not hasattr(fetcher, "get_belong_board"):
                continue
            try:
                raw_data = fetcher.get_belong_board(stock_code)
                boards = self._normalize_belong_boards(raw_data)
                if boards:
                    logger.info(f"[{fetcher.name}] 獲取所屬板塊成功: {stock_code}, count={len(boards)}")
                    return boards
            except Exception as e:
                logger.debug(f"[{fetcher.name}] 獲取所屬板塊失敗: {e}")
                continue
        return []

    def prefetch_stock_names(self, stock_codes: List[str], use_bulk: bool = False) -> None:
        """
        Pre-fetch stock names into cache before parallel analysis (Issue #455).

        When use_bulk=False, only calls get_stock_name per code (no get_stock_list),
        avoiding full-market fetch. Sequential execution to avoid rate limits.

        Args:
            stock_codes: Stock codes to prefetch.
            use_bulk: If True, may use get_stock_list (full fetch). Default False.
        """
        if not stock_codes:
            return
        stock_codes = [normalize_stock_code(c) for c in stock_codes]
        if use_bulk:
            self.batch_get_stock_names(stock_codes)
            return
        for code in stock_codes:
            # Skip realtime lookup to avoid triggering expensive full-market quote
            # requests during the prefetch phase.
            self.get_stock_name(code, allow_realtime=False)

    def batch_get_stock_names(self, stock_codes: List[str]) -> Dict[str, str]:
        """
        批次獲取股票中文名稱
        
        先嚐試從支援批次查詢的資料來源獲取股票列表，
        然後再逐個查詢缺失的股票名稱。
        
        Args:
            stock_codes: 股票程式碼列表
            
        Returns:
            {股票程式碼: 股票名稱} 字典
        """
        result = {}
        missing_codes = set(stock_codes)
        
        # 1. 先檢查快取
        if not hasattr(self, '_stock_name_cache'):
            self._stock_name_cache = {}
        
        for code in stock_codes:
            if code in self._stock_name_cache:
                result[code] = self._stock_name_cache[code]
                missing_codes.discard(code)
        
        if not missing_codes:
            return result
        
        # 2. 嘗試批次獲取股票列表
        for fetcher in self._fetchers:
            if hasattr(fetcher, 'get_stock_list') and missing_codes:
                try:
                    stock_list = fetcher.get_stock_list()
                    if stock_list is not None and not stock_list.empty:
                        for _, row in stock_list.iterrows():
                            code = row.get('code')
                            name = row.get('name')
                            if code and name:
                                self._stock_name_cache[code] = name
                                if code in missing_codes:
                                    result[code] = name
                                    missing_codes.discard(code)
                        
                        if not missing_codes:
                            break
                        
                        logger.info(f"[股票名稱] 從 {fetcher.name} 批次獲取完成，剩餘 {len(missing_codes)} 個待查")
                except Exception as e:
                    logger.debug(f"[股票名稱] {fetcher.name} 批次獲取失敗: {e}")
                    continue
        
        # 3. 逐個獲取剩餘的
        for code in list(missing_codes):
            name = self.get_stock_name(code)
            if name:
                result[code] = name
                missing_codes.discard(code)
        
        logger.info(f"[股票名稱] 批次獲取完成，成功 {len(result)}/{len(stock_codes)}")
        return result

    def get_main_indices(self, region: str = "cn") -> List[Dict[str, Any]]:
        """獲取主要指數實時行情（自動切換資料來源）"""
        for fetcher in self._fetchers:
            try:
                data = fetcher.get_main_indices(region=region)
                if data:
                    logger.info(f"[{fetcher.name}] 獲取指數行情成功")
                    return data
            except Exception as e:
                logger.warning(f"[{fetcher.name}] 獲取指數行情失敗: {e}")
                continue
        return []

    def get_market_stats(self) -> Dict[str, Any]:
        """獲取市場漲跌統計（自動切換資料來源）"""
        for fetcher in self._fetchers:
            try:
                data = fetcher.get_market_stats()
                if data:
                    logger.info(f"[{fetcher.name}] 獲取市場統計成功")
                    return data
            except Exception as e:
                logger.warning(f"[{fetcher.name}] 獲取市場統計失敗: {e}")
                continue
        return {}

    def _run_with_timeout(
        self,
        task: Callable[[], Any],
        timeout_seconds: float,
        task_name: str,
    ) -> Tuple[Optional[Any], Optional[str], int]:
        """
        Execute a task in a short-lived thread and enforce a timeout.

        Returns:
            (result, error, duration_ms)
        """
        start = time.time()
        timeout_value = max(0.0, timeout_seconds)
        if timeout_value <= 0:
            return None, f"{task_name} timeout", 0
        result_holder: Dict[str, Any] = {}
        error_holder: Dict[str, Exception] = {}

        if not self._fundamental_timeout_slots.acquire(blocking=False):
            return None, f"{task_name} timeout worker pool exhausted", int(timeout_value * 1000)

        def runner() -> None:
            try:
                result_holder["value"] = task()
            except Exception as exc:
                error_holder["value"] = exc
            finally:
                try:
                    self._fundamental_timeout_slots.release()
                except ValueError:
                    pass

        worker = Thread(target=runner, daemon=True, name=f"fundamental-{task_name}")
        try:
            worker.start()
        except Exception as exc:
            try:
                self._fundamental_timeout_slots.release()
            except ValueError:
                pass
            return None, str(exc), int((time.time() - start) * 1000)
        worker.join(timeout=timeout_value)
        if worker.is_alive():
            return None, f"{task_name} timeout", int(timeout_value * 1000)
        if "value" in error_holder:
            return None, str(error_holder["value"]), int((time.time() - start) * 1000)
        return result_holder.get("value"), None, int((time.time() - start) * 1000)

    def _run_with_retry(
        self,
        task: Callable[[], Any],
        timeout_seconds: float,
        task_name: str,
    ) -> Tuple[Optional[Any], Optional[str], int]:
        """
        Execute a task with bounded budget and best-effort retries.

        Returns:
            (result, error, total_duration_ms)
        """
        config = self._get_fundamental_config()
        attempts = max(1, int(config.fundamental_retry_max))
        remaining_seconds = max(0.0, float(timeout_seconds))
        total_cost_ms = 0
        last_error: Optional[str] = None

        for _ in range(attempts):
            if remaining_seconds <= 0:
                break
            result, err, cost_ms = self._run_with_timeout(task, remaining_seconds, task_name)
            total_cost_ms += cost_ms
            remaining_seconds = max(0.0, remaining_seconds - cost_ms / 1000)
            if err is None:
                return result, None, total_cost_ms
            last_error = err
            if remaining_seconds <= 0:
                break

        return None, last_error, total_cost_ms

    def _get_fundamental_config(self):
        from src.config import get_config
        return get_config()

    @staticmethod
    def _normalize_source_chain(
        entries: Any,
        provider: str,
        result: str,
        duration_ms: int,
    ) -> List[Dict[str, Any]]:
        """Normalize free-form source chain entries to structured dict list."""
        if entries is None:
            return [{"provider": provider, "result": result, "duration_ms": duration_ms}]

        normalized: List[Dict[str, Any]] = []
        if not isinstance(entries, (list, tuple)):
            entries = [entries]

        for item in entries:
            if isinstance(item, dict):
                normalized.append({
                    "provider": str(item.get("provider") or provider),
                    "result": str(item.get("result") or result),
                    "duration_ms": int(item.get("duration_ms", duration_ms)),
                })
                continue

            if item is None:
                continue

            provider_name = str(item)
            normalized.append({
                "provider": provider_name,
                "result": result,
                "duration_ms": duration_ms,
            })

        if not normalized:
            return [{"provider": provider, "result": result, "duration_ms": duration_ms}]

        return normalized

    @staticmethod
    def _block_status(payload: Dict[str, Any], available: bool = True) -> str:
        if not available:
            return "not_supported"
        if not payload:
            return "partial"
        return "ok"

    @staticmethod
    def _build_fundamental_block(
        status: str,
        payload: Optional[Dict[str, Any]] = None,
        source_chain: Optional[List[Dict[str, Any]]] = None,
        errors: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return {
            "status": status,
            "coverage": {"status": status},
            "source_chain": source_chain or [],
            "errors": errors or [],
            "data": payload or {},
        }

    @staticmethod
    def _has_meaningful_payload(payload: Any) -> bool:
        if payload is None:
            return False
        if isinstance(payload, str):
            normalized = payload.strip().lower()
            return normalized not in ("", "-", "nan", "none", "null", "n/a", "na")
        if isinstance(payload, dict):
            return any(DataFetcherManager._has_meaningful_payload(v) for v in payload.values())
        if isinstance(payload, (list, tuple, set)):
            return any(DataFetcherManager._has_meaningful_payload(v) for v in payload)
        try:
            if pd.isna(payload):
                return False
        except Exception:
            pass
        return True

    @staticmethod
    def _infer_block_status(payload: Any, fallback_status: str) -> str:
        if DataFetcherManager._has_meaningful_payload(payload):
            return "ok"
        if fallback_status in ("failed", "partial", "not_supported"):
            return fallback_status
        return "partial"

    @staticmethod
    def _should_cache_fundamental_context(context: Any) -> bool:
        if not isinstance(context, dict):
            return False
        status = str(context.get("status", "")).strip().lower()
        if status == "ok":
            return True
        if status == "failed":
            return False
        for block in (
            "valuation",
            "growth",
            "earnings",
            "institution",
            "capital_flow",
            "dragon_tiger",
            "boards",
        ):
            payload = context.get(block, {})
            if isinstance(payload, dict) and DataFetcherManager._has_meaningful_payload(payload.get("data")):
                return True
        return False

    def _build_market_not_supported(self, market: str, reason: str) -> Dict[str, Any]:
        blocks = {
            "valuation": self._build_fundamental_block(
                "partial" if market == "etf" else "not_supported",
                {},
                [{"provider": "fundamental_pipeline", "result": "not_supported", "duration_ms": 0}],
                [reason],
            ),
            "growth": self._build_fundamental_block(
                "not_supported",
                {},
                [{"provider": "fundamental_pipeline", "result": "not_supported", "duration_ms": 0}],
                [reason],
            ),
            "earnings": self._build_fundamental_block(
                "not_supported",
                {},
                [{"provider": "fundamental_pipeline", "result": "not_supported", "duration_ms": 0}],
                [reason],
            ),
            "institution": self._build_fundamental_block(
                "not_supported",
                {},
                [{"provider": "fundamental_pipeline", "result": "not_supported", "duration_ms": 0}],
                [reason],
            ),
            "capital_flow": self._build_fundamental_block(
                "not_supported",
                {},
                [{"provider": "fundamental_pipeline", "result": "not_supported", "duration_ms": 0}],
                [reason],
            ),
            "dragon_tiger": self._build_fundamental_block(
                "not_supported",
                {},
                [{"provider": "fundamental_pipeline", "result": "not_supported", "duration_ms": 0}],
                [reason],
            ),
            "boards": self._build_fundamental_block(
                "not_supported",
                {},
                [{"provider": "fundamental_pipeline", "result": "not_supported", "duration_ms": 0}],
                [reason],
            ),
        }
        return {
            "market": market,
            "status": "partial" if market == "etf" else "not_supported",
            "coverage": {
                block: blocks[block]["status"] for block in blocks
            },
            "source_chain": [{"provider": "fundamental_pipeline", "result": "not_supported", "duration_ms": 0}],
            "errors": [reason],
            **blocks,
        }

    def build_failed_fundamental_context(self, stock_code: str, reason: str) -> Dict[str, Any]:
        """Build a consistent failed-context payload for caller-side fallback."""
        market = _market_tag(stock_code)
        block_names = (
            "valuation",
            "growth",
            "earnings",
            "institution",
            "capital_flow",
            "dragon_tiger",
            "boards",
        )
        blocks = {
            block: self._build_fundamental_block(
                "failed",
                {},
                [{"provider": "fundamental_pipeline", "result": "failed", "duration_ms": 0}],
                [reason],
            )
            for block in block_names
        }
        return {
            "market": market,
            "status": "failed",
            "coverage": {block: "failed" for block in block_names},
            "source_chain": [{"provider": "fundamental_pipeline", "result": "failed", "duration_ms": 0}],
            "errors": [reason],
            **blocks,
        }

    def get_fundamental_context(
        self,
        stock_code: str,
        budget_seconds: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Aggregate fundamental blocks with fail-open semantics.
        """
        from src.config import get_config

        config = get_config()
        if not config.enable_fundamental_pipeline:
            return self._build_market_not_supported(
                market=_market_tag(stock_code),
                reason="fundamental pipeline disabled",
            )

        stock_code = normalize_stock_code(stock_code)
        market = _market_tag(stock_code)
        is_etf = _is_etf_code(stock_code)
        if market in {"us", "hk"}:
            return self._build_market_not_supported(
                market=market,
                reason="market not supported",
            )

        stage_timeout = float(
            budget_seconds if budget_seconds is not None else config.fundamental_stage_timeout_seconds
        )
        stage_timeout = max(0.0, stage_timeout)
        fetch_timeout = float(config.fundamental_fetch_timeout_seconds)
        fetch_timeout = max(0.0, fetch_timeout)

        cache_ttl = int(config.fundamental_cache_ttl_seconds)
        cache_max_entries = max(0, int(getattr(config, "fundamental_cache_max_entries", 256)))
        cache_key = self._get_fundamental_cache_key(stock_code, stage_timeout)
        if cache_ttl > 0:
            self._prune_fundamental_cache(cache_ttl, cache_max_entries)
            with self._fundamental_cache_lock:
                cache_item = self._fundamental_cache.get(cache_key)
                if cache_item:
                    age = time.time() - float(cache_item.get("ts", 0))
                    if age <= cache_ttl:
                        return cache_item.get("context", {})

        remaining_seconds = stage_timeout
        result_ctx: Dict[str, Any] = {
            "market": market,
            "valuation": {},
            "growth": {},
            "earnings": {},
            "institution": {},
            "capital_flow": {},
            "dragon_tiger": {},
            "boards": {},
            "coverage": {},
            "source_chain": [],
            "errors": [],
        }

        start_ts = time.time()

        def _consume_budget(consumed_ms: int) -> None:
            nonlocal remaining_seconds
            remaining_seconds = max(0.0, remaining_seconds - consumed_ms / 1000.0)

        valuation_timeout = min(fetch_timeout, remaining_seconds)
        if valuation_timeout > 0:
            quote_payload, valuation_err, valuation_ms = self._run_with_retry(
                lambda: self.get_realtime_quote(stock_code),
                valuation_timeout,
                "fundamental_valuation",
            )
            _consume_budget(valuation_ms)
        else:
            quote_payload, valuation_err, valuation_ms = None, "fundamental stage timeout", 0

        valuation_payload = {
            "pe_ratio": getattr(quote_payload, "pe_ratio", None) if quote_payload else None,
            "pb_ratio": getattr(quote_payload, "pb_ratio", None) if quote_payload else None,
            "total_mv": getattr(quote_payload, "total_mv", None) if quote_payload else None,
            "circ_mv": getattr(quote_payload, "circ_mv", None) if quote_payload else None,
        }
        valuation_status = self._infer_block_status(
            valuation_payload,
            "partial" if quote_payload is not None else "not_supported",
        )
        if valuation_status == "partial" and valuation_err and not self._has_meaningful_payload(valuation_payload):
            valuation_status = "failed"
        result_ctx["valuation"] = self._build_fundamental_block(
            valuation_status,
            valuation_payload,
            self._normalize_source_chain(
                [{"provider": "realtime_quote", "result": valuation_status, "duration_ms": valuation_ms}],
                "realtime_quote",
                valuation_status,
                valuation_ms,
            ),
            [valuation_err] if valuation_err else [],
        )

        # growth / earnings / institution (one AkShare call)
        if remaining_seconds <= 0:
            bundle_status = "failed"
            bundle_payload: Dict[str, Any] = {}
            bundle_errors = ["fundamental stage timeout"]
            bundle_ms = 0
        else:
            bundle_timeout = min(fetch_timeout, remaining_seconds)
            bundle_payload, bundle_err_msg, bundle_ms = self._run_with_retry(
                lambda: self._fundamental_adapter.get_fundamental_bundle(stock_code),
                bundle_timeout,
                "fundamental_bundle",
            )
            _consume_budget(bundle_ms)
            if not isinstance(bundle_payload, dict):
                bundle_status = "failed"
                bundle_payload = {}
                bundle_errors = ["fundamental_bundle failed"]
                if bundle_err_msg:
                    bundle_errors.append(bundle_err_msg)
            else:
                bundle_status = str(bundle_payload.get("status", "not_supported"))
                bundle_errors = [bundle_err_msg] if bundle_err_msg else []

        bundle_chain = self._normalize_source_chain(
            bundle_payload.get("source_chain", []),
            "fundamental_bundle",
            bundle_status,
            bundle_ms,
        ) if isinstance(bundle_payload, dict) else self._normalize_source_chain(
            None,
            "fundamental_bundle",
            bundle_status,
            bundle_ms,
        )
        growth_payload = bundle_payload.get("growth", {}) if isinstance(bundle_payload, dict) else {}
        earnings_payload = bundle_payload.get("earnings", {}) if isinstance(bundle_payload, dict) else {}
        institution_payload = bundle_payload.get("institution", {}) if isinstance(bundle_payload, dict) else {}
        if not isinstance(growth_payload, dict):
            growth_payload = {}
        else:
            growth_payload = dict(growth_payload)
        if not isinstance(earnings_payload, dict):
            earnings_payload = {}
        else:
            earnings_payload = dict(earnings_payload)
        if not isinstance(institution_payload, dict):
            institution_payload = {}
        else:
            institution_payload = dict(institution_payload)

        # Derive TTM dividend yield from already-fetched quote price; avoid extra quote calls.
        earnings_extra_errors: List[str] = []
        dividend_payload = earnings_payload.get("dividend")
        if isinstance(dividend_payload, dict):
            dividend_payload = dict(dividend_payload)
            ttm_cash_raw = dividend_payload.get("ttm_cash_dividend_per_share")
            ttm_cash = None
            if ttm_cash_raw is not None:
                try:
                    ttm_cash = float(ttm_cash_raw)
                except (TypeError, ValueError):
                    earnings_extra_errors.append("invalid_ttm_cash_dividend_per_share")
            if isinstance(quote_payload, dict):
                latest_price_raw = quote_payload.get("price")
            else:
                latest_price_raw = getattr(quote_payload, "price", None) if quote_payload else None
            latest_price = None
            if latest_price_raw is not None:
                try:
                    latest_price = float(latest_price_raw)
                except (TypeError, ValueError):
                    latest_price = None
            ttm_yield = None
            if ttm_cash is not None:
                if latest_price is not None and latest_price > 0:
                    ttm_yield = round(ttm_cash / latest_price * 100.0, 4)
                else:
                    earnings_extra_errors.append("invalid_price_for_ttm_dividend_yield")

            dividend_payload["ttm_dividend_yield_pct"] = ttm_yield
            if ttm_yield is not None:
                dividend_payload["yield_formula"] = "ttm_cash_dividend_per_share / latest_price * 100"
            earnings_payload["dividend"] = dividend_payload

        adapter_errors = list(bundle_payload.get("errors", [])) if isinstance(bundle_payload, dict) else []
        adapter_errors.extend(bundle_errors)
        growth_errors = list(adapter_errors)
        earnings_errors = list(adapter_errors)
        earnings_errors.extend(earnings_extra_errors)
        institution_errors = list(adapter_errors)

        growth_status = self._infer_block_status(growth_payload, bundle_status)
        earnings_status = self._infer_block_status(earnings_payload, bundle_status)
        institution_status = self._infer_block_status(institution_payload, bundle_status)

        result_ctx["growth"] = self._build_fundamental_block(
            growth_status,
            growth_payload,
            bundle_chain,
            growth_errors,
        )
        result_ctx["earnings"] = self._build_fundamental_block(
            earnings_status,
            earnings_payload,
            bundle_chain,
            earnings_errors,
        )
        result_ctx["institution"] = self._build_fundamental_block(
            institution_status,
            institution_payload,
            bundle_chain,
            institution_errors,
        )

        # capital flow
        if is_etf:
            result_ctx["capital_flow"] = self._build_fundamental_block(
                "not_supported",
                {},
                [{"provider": "fundamental_pipeline", "result": "not_supported", "duration_ms": 0}],
                ["etf not fully supported"],
            )
            result_ctx["dragon_tiger"] = self._build_fundamental_block(
                "not_supported",
                {},
                [{"provider": "fundamental_pipeline", "result": "not_supported", "duration_ms": 0}],
                ["etf not fully supported"],
            )
            result_ctx["boards"] = self._build_fundamental_block(
                "not_supported",
                {},
                [{"provider": "fundamental_pipeline", "result": "not_supported", "duration_ms": 0}],
                ["etf not fully supported"],
            )
            result_ctx["status"] = "partial"
        else:
            capital_flow_budget = min(fetch_timeout, remaining_seconds)
            capital_flow_start = time.time()
            result_ctx["capital_flow"] = self.get_capital_flow_context(
                stock_code,
                budget_seconds=capital_flow_budget,
            )
            _consume_budget(int((time.time() - capital_flow_start) * 1000))

            dragon_tiger_budget = min(fetch_timeout, remaining_seconds)
            dragon_tiger_start = time.time()
            result_ctx["dragon_tiger"] = self.get_dragon_tiger_context(
                stock_code,
                budget_seconds=dragon_tiger_budget,
            )
            _consume_budget(int((time.time() - dragon_tiger_start) * 1000))

            result_ctx["boards"] = self.get_board_context(
                stock_code,
                budget_seconds=min(fetch_timeout, remaining_seconds),
            )

        block_statuses = {
            "valuation": result_ctx["valuation"].get("status", "not_supported"),
            "growth": result_ctx["growth"].get("status", "not_supported"),
            "earnings": result_ctx["earnings"].get("status", "not_supported"),
            "institution": result_ctx["institution"].get("status", "not_supported"),
            "capital_flow": result_ctx["capital_flow"].get("status", "not_supported"),
            "dragon_tiger": result_ctx["dragon_tiger"].get("status", "not_supported"),
            "boards": result_ctx["boards"].get("status", "not_supported"),
        }
        result_ctx["coverage"] = block_statuses
        for block in (
            "valuation",
            "growth",
            "earnings",
            "institution",
            "capital_flow",
            "dragon_tiger",
            "boards",
        ):
            result_ctx["errors"].extend(result_ctx[block].get("errors", []))
            result_ctx["source_chain"].extend(result_ctx[block].get("source_chain", []))

        if is_etf:
            # Keep ETF downgrade semantics for overall status even when valuation is available.
            result_ctx["status"] = (
                "not_supported" if all(value == "not_supported" for value in block_statuses.values()) else "partial"
            )
        elif all(value == "not_supported" for value in block_statuses.values()):
            result_ctx["status"] = "not_supported"
        elif "failed" in block_statuses.values() or "partial" in block_statuses.values():
            result_ctx["status"] = "partial"
        else:
            result_ctx["status"] = "ok"

        result_ctx["elapsed_ms"] = int((time.time() - start_ts) * 1000)
        if cache_ttl > 0 and self._should_cache_fundamental_context(result_ctx):
            with self._fundamental_cache_lock:
                self._fundamental_cache[cache_key] = {
                    "ts": time.time(),
                    "context": result_ctx,
                }
            self._prune_fundamental_cache(cache_ttl, cache_max_entries)
        return result_ctx

    def get_capital_flow_context(self, stock_code: str, budget_seconds: Optional[float] = None) -> Dict[str, Any]:
        """資金流向塊（fail-open）。"""
        from src.config import get_config

        config = get_config()
        stock_code = normalize_stock_code(stock_code)
        timeout = float(budget_seconds if budget_seconds is not None else config.fundamental_fetch_timeout_seconds)
        if _market_tag(stock_code) != "cn" or _is_etf_code(stock_code):
            return self._build_fundamental_block(
                "not_supported",
                {},
                [{"provider": "fundamental_pipeline", "result": "not_supported", "duration_ms": 0}],
                ["not supported"],
            )

        if timeout <= 0:
            return self._build_fundamental_block(
                "failed",
                {},
                [{"provider": "fundamental_pipeline", "result": "failed", "duration_ms": 0}],
                ["fundamental stage timeout"],
            )
        payload, err, cost_ms = self._run_with_retry(
            lambda: self._fundamental_adapter.get_capital_flow(stock_code),
            timeout,
            "capital_flow",
        )
        if not isinstance(payload, dict):
            return self._build_fundamental_block(
                "failed",
                {},
                [{"provider": "fundamental_pipeline", "result": "failed", "duration_ms": cost_ms}],
                [err or "capital_flow failed"],
            )

        stock_flow = payload.get("stock_flow") or {}
        sector_rankings = payload.get("sector_rankings") or {}
        has_stock_flow = False
        if isinstance(stock_flow, dict):
            has_stock_flow = any(v is not None for v in stock_flow.values())
        has_sector_rankings = bool(sector_rankings.get("top")) or bool(sector_rankings.get("bottom"))
        adapter_status = str(payload.get("status", "not_supported"))
        if has_stock_flow or has_sector_rankings:
            capital_flow_status = "ok"
        elif adapter_status == "not_supported":
            capital_flow_status = "not_supported"
        else:
            capital_flow_status = "partial"

        return self._build_fundamental_block(
            capital_flow_status,
            {
                "stock_flow": payload.get("stock_flow", {}),
                "sector_rankings": payload.get("sector_rankings", {}),
            },
            self._normalize_source_chain(
                payload.get("source_chain", []),
                "capital_flow",
                capital_flow_status,
                cost_ms,
            ),
            list(payload.get("errors", [])) + ([err] if err else []),
        )

    def get_dragon_tiger_context(self, stock_code: str, budget_seconds: Optional[float] = None) -> Dict[str, Any]:
        """龍虎榜塊（fail-open）。"""
        from src.config import get_config

        config = get_config()
        stock_code = normalize_stock_code(stock_code)
        timeout = float(budget_seconds if budget_seconds is not None else config.fundamental_fetch_timeout_seconds)
        if _market_tag(stock_code) != "cn" or _is_etf_code(stock_code):
            return self._build_fundamental_block(
                "not_supported",
                {},
                [{"provider": "fundamental_pipeline", "result": "not_supported", "duration_ms": 0}],
                ["not supported"],
            )

        if timeout <= 0:
            return self._build_fundamental_block(
                "failed",
                {},
                [{"provider": "fundamental_pipeline", "result": "failed", "duration_ms": 0}],
                ["fundamental stage timeout"],
            )
        payload, err, cost_ms = self._run_with_retry(
            lambda: self._fundamental_adapter.get_dragon_tiger_flag(stock_code),
            timeout,
            "dragon_tiger",
        )
        if not isinstance(payload, dict):
            return self._build_fundamental_block(
                "failed",
                {},
                [{"provider": "fundamental_pipeline", "result": "failed", "duration_ms": cost_ms}],
                [err or "dragon_tiger failed"],
            )
        return self._build_fundamental_block(
            (payload.get("status") if isinstance(payload.get("status"), str) else "partial"),
            {
                "is_on_list": bool(payload.get("is_on_list", False)),
                "recent_count": int(payload.get("recent_count", 0)),
                "latest_date": payload.get("latest_date"),
            },
            self._normalize_source_chain(
                payload.get("source_chain", []),
                "dragon_tiger",
                str(payload.get("status", "ok")),
                cost_ms,
            ),
            list(payload.get("errors", [])) + ([err] if err else []),
        )

    def get_board_context(self, stock_code: str, budget_seconds: Optional[float] = None) -> Dict[str, Any]:
        """板塊榜單塊（fail-open）。"""
        from src.config import get_config

        config = get_config()
        stock_code = normalize_stock_code(stock_code)
        timeout = float(budget_seconds if budget_seconds is not None else config.fundamental_fetch_timeout_seconds)
        if _market_tag(stock_code) != "cn" or _is_etf_code(stock_code):
            return self._build_fundamental_block(
                "not_supported",
                {},
                [{"provider": "fundamental_pipeline", "result": "not_supported", "duration_ms": 0}],
                ["not supported"],
            )

        if timeout <= 0:
            return self._build_fundamental_block(
                "failed",
                {},
                [{"provider": "fundamental_pipeline", "result": "failed", "duration_ms": 0}],
                ["fundamental stage timeout"],
            )

        def task() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], str]:
            return self._get_sector_rankings_with_meta(5)

        rankings, err, cost_ms = self._run_with_retry(task, timeout, "boards")
        if isinstance(rankings, tuple) and len(rankings) == 4:
            top, bottom, chain, chain_error = rankings
            if chain_error and not err:
                err = chain_error
            if not top and not bottom:
                return self._build_fundamental_block(
                    "failed",
                    {},
                    chain if chain else [{"provider": "sector_rankings", "result": "failed", "duration_ms": cost_ms}],
                    [err or "boards empty from all sources"],
                )
            board_status = "ok" if top and bottom else "partial"
            return self._build_fundamental_block(
                board_status,
                {"top": top or [], "bottom": bottom or []},
                chain if chain else self._normalize_source_chain(
                    ["sector_rankings"],
                    "boards",
                    board_status,
                    cost_ms,
                ),
                [err] if err else [],
            )

        return self._build_fundamental_block(
            "failed",
            {},
            [{"provider": "sector_rankings", "result": "failed", "duration_ms": cost_ms}],
            [err or "boards failed"],
        )

    def _get_sector_rankings_with_meta(
            self,
            n: int = 5,
        ) -> Tuple[List[Dict], List[Dict], List[Dict[str, Any]], str]:
            """Get sector rankings with ordered fallback chain metadata."""
            source_chain: List[Dict[str, Any]] = []
            last_error = ""

            # 直接遍歷管理器已經按 priority 排好序的資料來源列表
            for fetcher in self._fetchers:
                if not hasattr(fetcher, 'get_sector_rankings'):
                    continue

                start = time.time()
                try:
                    data = fetcher.get_sector_rankings(n)
                    duration_ms = int((time.time() - start) * 1000)
                    if data and data[0] is not None and data[1] is not None:
                        source_chain.append(
                            {
                                "provider": fetcher.name,
                                "result": "ok",
                                "duration_ms": duration_ms,
                            }
                        )
                        logger.info(f"[{fetcher.name}] 獲取板塊排行成功")
                        return data[0], data[1], source_chain, ""

                    last_error = f"{fetcher.name}返回空結果"
                    source_chain.append(
                        {
                            "provider": fetcher.name,
                            "result": "empty",
                            "duration_ms": duration_ms,
                            "error": last_error,
                        }
                    )
                except Exception as e:
                    error_type, error_reason = summarize_exception(e)
                    last_error = f"{fetcher.name} ({error_type}) {error_reason}"
                    duration_ms = int((time.time() - start) * 1000)
                    source_chain.append(
                        {
                            "provider": fetcher.name,
                            "result": "failed",
                            "duration_ms": duration_ms,
                            "error": error_reason,
                        }
                    )
                    logger.warning(f"[{fetcher.name}] 獲取板塊排行失敗: {error_reason}")

            return [], [], source_chain, last_error

    def get_sector_rankings(self, n: int = 5) -> Tuple[List[Dict], List[Dict]]:
        """獲取板塊漲跌榜（自動切換資料來源）"""
        # 按需求固定回退順序：Akshare(EM) -> Akshare(Sina) -> Tushare -> Efinance
        top, bottom, _, last_error = self._get_sector_rankings_with_meta(n)
        if top or bottom:
            return top, bottom
        logger.warning(f"[板塊排行] 所有資料來源均失敗，最終錯誤: {last_error}")
        return [], []
