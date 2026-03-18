# -*- coding: utf-8 -*-
"""
===================================
A股自選股智慧分析系統 - 搜尋服務模組
===================================

職責：
1. 提供統一的新聞搜尋介面
2. 支援 Bocha、Tavily、Brave、SerpAPI、SearXNG 多種搜尋引擎
3. 多 Key 負載均衡和故障轉移
4. 搜尋結果快取和格式化
"""

import logging
import random
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import List, Dict, Any, Optional, Tuple
from itertools import cycle
import requests
from newspaper import Article, Config
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from data_provider.us_index_mapping import is_us_index_code
from src.config import (
    NEWS_STRATEGY_WINDOWS,
    normalize_news_strategy_profile,
    resolve_news_window_days,
)

logger = logging.getLogger(__name__)

# Transient network errors (retryable)
_SEARCH_TRANSIENT_EXCEPTIONS = (
    requests.exceptions.SSLError,
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(_SEARCH_TRANSIENT_EXCEPTIONS),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
def _post_with_retry(url: str, *, headers: Dict[str, str], json: Dict[str, Any], timeout: int) -> requests.Response:
    """POST with retry on transient SSL/network errors."""
    return requests.post(url, headers=headers, json=json, timeout=timeout)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(_SEARCH_TRANSIENT_EXCEPTIONS),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _get_with_retry(
    url: str, *, headers: Dict[str, str], params: Dict[str, Any], timeout: int
) -> requests.Response:
    """GET with retry on transient SSL/network errors."""
    return requests.get(url, headers=headers, params=params, timeout=timeout)


def fetch_url_content(url: str, timeout: int = 5) -> str:
    """
    獲取 URL 網頁正文內容 (使用 newspaper3k)
    """
    try:
        # 配置 newspaper3k
        config = Config()
        config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        config.request_timeout = timeout
        config.fetch_images = False  # 不下載圖片
        config.memoize_articles = False # 不快取

        article = Article(url, config=config, language='zh') # 預設中文，但也支援其他
        article.download()
        article.parse()

        # 獲取正文
        text = article.text.strip()

        # 簡單的後處理，去除空行
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        text = '\n'.join(lines)

        return text[:1500]  # 限制返回長度（比 bs4 稍微多一點，因為 newspaper 解析更乾淨）
    except Exception as e:
        logger.debug(f"Fetch content failed for {url}: {e}")

    return ""


@dataclass
class SearchResult:
    """搜尋結果資料類"""
    title: str
    snippet: str  # 摘要
    url: str
    source: str  # 來源網站
    published_date: Optional[str] = None
    
    def to_text(self) -> str:
        """轉換為文字格式"""
        date_str = f" ({self.published_date})" if self.published_date else ""
        return f"【{self.source}】{self.title}{date_str}\n{self.snippet}"


@dataclass 
class SearchResponse:
    """搜尋響應"""
    query: str
    results: List[SearchResult]
    provider: str  # 使用的搜尋引擎
    success: bool = True
    error_message: Optional[str] = None
    search_time: float = 0.0  # 搜尋耗時（秒）
    
    def to_context(self, max_results: int = 5) -> str:
        """將搜尋結果轉換為可用於 AI 分析的上下文"""
        if not self.success or not self.results:
            return f"搜尋 '{self.query}' 未找到相關結果。"
        
        lines = [f"【{self.query} 搜尋結果】（來源：{self.provider}）"]
        for i, result in enumerate(self.results[:max_results], 1):
            lines.append(f"\n{i}. {result.to_text()}")
        
        return "\n".join(lines)


class BaseSearchProvider(ABC):
    """搜尋引擎基類"""
    
    def __init__(self, api_keys: List[str], name: str):
        """
        初始化搜尋引擎
        
        Args:
            api_keys: API Key 列表（支援多個 key 負載均衡）
            name: 搜尋引擎名稱
        """
        self._api_keys = api_keys
        self._name = name
        self._key_cycle = cycle(api_keys) if api_keys else None
        self._key_usage: Dict[str, int] = {key: 0 for key in api_keys}
        self._key_errors: Dict[str, int] = {key: 0 for key in api_keys}
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def is_available(self) -> bool:
        """檢查是否有可用的 API Key"""
        return bool(self._api_keys)
    
    def _get_next_key(self) -> Optional[str]:
        """
        獲取下一個可用的 API Key（負載均衡）
        
        策略：輪詢 + 跳過錯誤過多的 key
        """
        if not self._key_cycle:
            return None
        
        # 最多嘗試所有 key
        for _ in range(len(self._api_keys)):
            key = next(self._key_cycle)
            # 跳過錯誤次數過多的 key（超過 3 次）
            if self._key_errors.get(key, 0) < 3:
                return key
        
        # 所有 key 都有問題，重置錯誤計數並返回第一個
        logger.warning(f"[{self._name}] 所有 API Key 都有錯誤記錄，重置錯誤計數")
        self._key_errors = {key: 0 for key in self._api_keys}
        return self._api_keys[0] if self._api_keys else None
    
    def _record_success(self, key: str) -> None:
        """記錄成功使用"""
        self._key_usage[key] = self._key_usage.get(key, 0) + 1
        # 成功後減少錯誤計數
        if key in self._key_errors and self._key_errors[key] > 0:
            self._key_errors[key] -= 1
    
    def _record_error(self, key: str) -> None:
        """記錄錯誤"""
        self._key_errors[key] = self._key_errors.get(key, 0) + 1
        logger.warning(f"[{self._name}] API Key {key[:8]}... 錯誤計數: {self._key_errors[key]}")
    
    @abstractmethod
    def _do_search(self, query: str, api_key: str, max_results: int, days: int = 7) -> SearchResponse:
        """執行搜尋（子類實現）"""
        pass
    
    def search(self, query: str, max_results: int = 5, days: int = 7) -> SearchResponse:
        """
        執行搜尋
        
        Args:
            query: 搜尋關鍵詞
            max_results: 最大返回結果數
            days: 搜尋最近幾天的時間範圍（預設7天）
            
        Returns:
            SearchResponse 物件
        """
        api_key = self._get_next_key()
        if not api_key:
            return SearchResponse(
                query=query,
                results=[],
                provider=self._name,
                success=False,
                error_message=f"{self._name} 未配置 API Key"
            )
        
        start_time = time.time()
        try:
            response = self._do_search(query, api_key, max_results, days=days)
            response.search_time = time.time() - start_time
            
            if response.success:
                self._record_success(api_key)
                logger.info(f"[{self._name}] 搜尋 '{query}' 成功，返回 {len(response.results)} 條結果，耗時 {response.search_time:.2f}s")
            else:
                self._record_error(api_key)
            
            return response
            
        except Exception as e:
            self._record_error(api_key)
            elapsed = time.time() - start_time
            logger.error(f"[{self._name}] 搜尋 '{query}' 失敗: {e}")
            return SearchResponse(
                query=query,
                results=[],
                provider=self._name,
                success=False,
                error_message=str(e),
                search_time=elapsed
            )


class TavilySearchProvider(BaseSearchProvider):
    """
    Tavily 搜尋引擎
    
    特點：
    - 專為 AI/LLM 最佳化的搜尋 API
    - 免費版每月 1000 次請求
    - 返回結構化的搜尋結果
    
    文件：https://docs.tavily.com/
    """
    
    def __init__(self, api_keys: List[str]):
        super().__init__(api_keys, "Tavily")
    
    def _do_search(self, query: str, api_key: str, max_results: int, days: int = 7) -> SearchResponse:
        """執行 Tavily 搜尋"""
        try:
            from tavily import TavilyClient
        except ImportError:
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message="tavily-python 未安裝，請執行: pip install tavily-python"
            )
        
        try:
            client = TavilyClient(api_key=api_key)
            
            # 執行搜尋（最佳化：使用advanced深度、限制最近幾天）
            response = client.search(
                query=query,
                search_depth="advanced",  # advanced 獲取更多結果
                max_results=max_results,
                include_answer=False,
                include_raw_content=False,
                days=days,  # 搜尋最近天數的內容
            )
            
            # 記錄原始響應到日誌
            logger.info(f"[Tavily] 搜尋完成，query='{query}', 返回 {len(response.get('results', []))} 條結果")
            logger.debug(f"[Tavily] 原始響應: {response}")
            
            # 解析結果
            results = []
            for item in response.get('results', []):
                results.append(SearchResult(
                    title=item.get('title', ''),
                    snippet=item.get('content', '')[:500],  # 擷取前500字
                    url=item.get('url', ''),
                    source=self._extract_domain(item.get('url', '')),
                    published_date=item.get('published_date'),
                ))
            
            return SearchResponse(
                query=query,
                results=results,
                provider=self.name,
                success=True,
            )
            
        except Exception as e:
            error_msg = str(e)
            # 檢查是否是配額問題
            if 'rate limit' in error_msg.lower() or 'quota' in error_msg.lower():
                error_msg = f"API 配額已用盡: {error_msg}"
            
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=error_msg
            )
    
    @staticmethod
    def _extract_domain(url: str) -> str:
        """從 URL 提取域名作為來源"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.replace('www.', '')
            return domain or '未知來源'
        except Exception:
            return '未知來源'


class SerpAPISearchProvider(BaseSearchProvider):
    """
    SerpAPI 搜尋引擎
    
    特點：
    - 支援 Google、Bing、百度等多種搜尋引擎
    - 免費版每月 100 次請求
    - 返回真實的搜尋結果
    
    文件：https://serpapi.com/baidu-search-api?utm_source=github_daily_stock_analysis
    """
    
    def __init__(self, api_keys: List[str]):
        super().__init__(api_keys, "SerpAPI")
    
    def _do_search(self, query: str, api_key: str, max_results: int, days: int = 7) -> SearchResponse:
        """執行 SerpAPI 搜尋"""
        try:
            from serpapi import GoogleSearch
        except ImportError:
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message="google-search-results 未安裝，請執行: pip install google-search-results"
            )
        
        try:
            # 確定時間範圍引數 tbs
            tbs = "qdr:w"  # 預設一週
            if days <= 1:
                tbs = "qdr:d"  # 過去24小時
            elif days <= 7:
                tbs = "qdr:w"  # 過去一週
            elif days <= 30:
                tbs = "qdr:m"  # 過去一月
            else:
                tbs = "qdr:y"  # 過去一年

            # 使用 Google 搜尋 (獲取 Knowledge Graph, Answer Box 等)
            params = {
                "engine": "google",
                "q": query,
                "api_key": api_key,
                "google_domain": "google.com.hk", # 使用香港谷歌，中文支援較好
                "hl": "zh-cn",  # 中文介面
                "gl": "cn",     # 中國地區偏好
                "tbs": tbs,     # 時間範圍限制
                "num": max_results # 請求的結果數量，注意：Google API有時不嚴格遵守
            }
            
            search = GoogleSearch(params)
            response = search.get_dict()
            
            # 記錄原始響應到日誌
            logger.debug(f"[SerpAPI] 原始響應 keys: {response.keys()}")
            
            # 解析結果
            results = []
            
            # 1. 解析 Knowledge Graph (知識圖譜)
            kg = response.get('knowledge_graph', {})
            if kg:
                title = kg.get('title', '知識圖譜')
                desc = kg.get('description', '')
                
                # 提取額外屬性
                details = []
                for key in ['type', 'founded', 'headquarters', 'employees', 'ceo']:
                    val = kg.get(key)
                    if val:
                        details.append(f"{key}: {val}")
                        
                snippet = f"{desc}\n" + " | ".join(details) if details else desc
                
                results.append(SearchResult(
                    title=f"[知識圖譜] {title}",
                    snippet=snippet,
                    url=kg.get('source', {}).get('link', ''),
                    source="Google Knowledge Graph"
                ))
                
            # 2. 解析 Answer Box (精選回答/行情卡片)
            ab = response.get('answer_box', {})
            if ab:
                ab_title = ab.get('title', '精選回答')
                ab_snippet = ""
                
                # 財經類回答
                if ab.get('type') == 'finance_results':
                    stock = ab.get('stock', '')
                    price = ab.get('price', '')
                    currency = ab.get('currency', '')
                    movement = ab.get('price_movement', {})
                    mv_val = movement.get('percentage', 0)
                    mv_dir = movement.get('movement', '')
                    
                    ab_title = f"[行情卡片] {stock}"
                    ab_snippet = f"價格: {price} {currency}\n漲跌: {mv_dir} {mv_val}%"
                    
                    # 提取表格資料
                    if 'table' in ab:
                        table_data = []
                        for row in ab['table']:
                            if 'name' in row and 'value' in row:
                                table_data.append(f"{row['name']}: {row['value']}")
                        if table_data:
                            ab_snippet += "\n" + "; ".join(table_data)
                            
                # 普通文字回答
                elif 'snippet' in ab:
                    ab_snippet = ab.get('snippet', '')
                    list_items = ab.get('list', [])
                    if list_items:
                        ab_snippet += "\n" + "\n".join([f"- {item}" for item in list_items])
                
                elif 'answer' in ab:
                    ab_snippet = ab.get('answer', '')
                    
                if ab_snippet:
                    results.append(SearchResult(
                        title=f"[精選回答] {ab_title}",
                        snippet=ab_snippet,
                        url=ab.get('link', '') or ab.get('displayed_link', ''),
                        source="Google Answer Box"
                    ))

            # 3. 解析 Related Questions (相關問題)
            rqs = response.get('related_questions', [])
            for rq in rqs[:3]: # 取前3個
                question = rq.get('question', '')
                snippet = rq.get('snippet', '')
                link = rq.get('link', '')
                
                if question and snippet:
                     results.append(SearchResult(
                        title=f"[相關問題] {question}",
                        snippet=snippet,
                        url=link,
                        source="Google Related Questions"
                     ))

            # 4. 解析 Organic Results (自然搜尋結果)
            organic_results = response.get('organic_results', [])

            for item in organic_results[:max_results]:
                link = item.get('link', '')
                snippet = item.get('snippet', '')

                # 增強：如果需要，解析網頁正文
                # 策略：如果摘要太短，或者為了獲取更多資訊，可以請求網頁
                # 這裡我們對所有結果嘗試獲取正文，但為了效能，僅獲取前1000字元
                content = ""
                if link:
                   try:
                       fetched_content = fetch_url_content(link, timeout=5)
                       if fetched_content:
                           # 如果獲取到了正文，將其拼接到 snippet 中，或者替換 snippet
                           # 這裡選擇拼接，保留原摘要
                           content = fetched_content
                           if len(content) > 500:
                               snippet = f"{snippet}\n\n【網頁詳情】\n{content[:500]}..."
                           else:
                               snippet = f"{snippet}\n\n【網頁詳情】\n{content}"
                   except Exception as e:
                       logger.debug(f"[SerpAPI] Fetch content failed: {e}")

                results.append(SearchResult(
                    title=item.get('title', ''),
                    snippet=snippet[:1000], # 限制總長度
                    url=link,
                    source=item.get('source', self._extract_domain(link)),
                    published_date=item.get('date'),
                ))

            return SearchResponse(
                query=query,
                results=results,
                provider=self.name,
                success=True,
            )
            
        except Exception as e:
            error_msg = str(e)
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=error_msg
            )
    
    @staticmethod
    def _extract_domain(url: str) -> str:
        """從 URL 提取域名"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc.replace('www.', '') or '未知來源'
        except Exception:
            return '未知來源'


class BochaSearchProvider(BaseSearchProvider):
    """
    博查搜尋引擎
    
    特點：
    - 專為AI最佳化的中文搜尋API
    - 結果準確、摘要完整
    - 支援時間範圍過濾和AI摘要
    - 相容Bing Search API格式
    
    文件：https://bocha-ai.feishu.cn/wiki/RXEOw02rFiwzGSkd9mUcqoeAnNK
    """
    
    def __init__(self, api_keys: List[str]):
        super().__init__(api_keys, "Bocha")
    
    def _do_search(self, query: str, api_key: str, max_results: int, days: int = 7) -> SearchResponse:
        """執行博查搜尋"""
        try:
            import requests
        except ImportError:
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message="requests 未安裝，請執行: pip install requests"
            )
        
        try:
            # API 端點
            url = "https://api.bocha.cn/v1/web-search"
            
            # 請求頭
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
            
            # 確定時間範圍
            freshness = "oneWeek"
            if days <= 1:
                freshness = "oneDay"
            elif days <= 7:
                freshness = "oneWeek"
            elif days <= 30:
                freshness = "oneMonth"
            else:
                freshness = "oneYear"

            # 請求引數（嚴格按照API文件）
            payload = {
                "query": query,
                "freshness": freshness,  # 動態時間範圍
                "summary": True,  # 啟用AI摘要
                "count": min(max_results, 50)  # 最大50條
            }
            
            # 執行搜尋（帶瞬時 SSL/網路錯誤重試）
            response = _post_with_retry(url, headers=headers, json=payload, timeout=10)
            
            # 檢查HTTP狀態碼
            if response.status_code != 200:
                # 嘗試解析錯誤資訊
                try:
                    if response.headers.get('content-type', '').startswith('application/json'):
                        error_data = response.json()
                        error_message = error_data.get('message', response.text)
                    else:
                        error_message = response.text
                except Exception:
                    error_message = response.text
                
                # 根據錯誤碼處理
                if response.status_code == 403:
                    error_msg = f"餘額不足: {error_message}"
                elif response.status_code == 401:
                    error_msg = f"API KEY無效: {error_message}"
                elif response.status_code == 400:
                    error_msg = f"請求引數錯誤: {error_message}"
                elif response.status_code == 429:
                    error_msg = f"請求頻率達到限制: {error_message}"
                else:
                    error_msg = f"HTTP {response.status_code}: {error_message}"
                
                logger.warning(f"[Bocha] 搜尋失敗: {error_msg}")
                
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message=error_msg
                )
            
            # 解析響應
            try:
                data = response.json()
            except ValueError as e:
                error_msg = f"響應JSON解析失敗: {str(e)}"
                logger.error(f"[Bocha] {error_msg}")
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message=error_msg
                )
            
            # 檢查響應code
            if data.get('code') != 200:
                error_msg = data.get('msg') or f"API返回錯誤碼: {data.get('code')}"
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message=error_msg
                )
            
            # 記錄原始響應到日誌
            logger.info(f"[Bocha] 搜尋完成，query='{query}'")
            logger.debug(f"[Bocha] 原始響應: {data}")
            
            # 解析搜尋結果
            results = []
            web_pages = data.get('data', {}).get('webPages', {})
            value_list = web_pages.get('value', [])
            
            for item in value_list[:max_results]:
                # 優先使用summary（AI摘要），fallback到snippet
                snippet = item.get('summary') or item.get('snippet', '')
                
                # 擷取摘要長度
                if snippet:
                    snippet = snippet[:500]
                
                results.append(SearchResult(
                    title=item.get('name', ''),
                    snippet=snippet,
                    url=item.get('url', ''),
                    source=item.get('siteName') or self._extract_domain(item.get('url', '')),
                    published_date=item.get('datePublished'),  # UTC+8格式，無需轉換
                ))
            
            logger.info(f"[Bocha] 成功解析 {len(results)} 條結果")
            
            return SearchResponse(
                query=query,
                results=results,
                provider=self.name,
                success=True,
            )
            
        except requests.exceptions.Timeout:
            error_msg = "請求超時"
            logger.error(f"[Bocha] {error_msg}")
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=error_msg
            )
        except requests.exceptions.RequestException as e:
            error_msg = f"網路請求失敗: {str(e)}"
            logger.error(f"[Bocha] {error_msg}")
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=error_msg
            )
        except Exception as e:
            error_msg = f"未知錯誤: {str(e)}"
            logger.error(f"[Bocha] {error_msg}")
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=error_msg
            )
    
    @staticmethod
    def _extract_domain(url: str) -> str:
        """從 URL 提取域名作為來源"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.replace('www.', '')
            return domain or '未知來源'
        except Exception:
            return '未知來源'


class MiniMaxSearchProvider(BaseSearchProvider):
    """
    MiniMax Web Search (Coding Plan API)

    Features:
    - Backed by MiniMax Coding Plan subscription
    - Returns structured organic results with title/link/snippet/date
    - No native time-range parameter; time filtering is done via query
      augmentation and client-side date filtering
    - Circuit-breaker protection: 3 consecutive failures -> 300s cooldown

    API endpoint: POST https://api.minimaxi.com/v1/coding_plan/search
    """

    API_ENDPOINT = "https://api.minimaxi.com/v1/coding_plan/search"

    # Circuit-breaker settings
    _CB_FAILURE_THRESHOLD = 3
    _CB_COOLDOWN_SECONDS = 300  # 5 minutes

    def __init__(self, api_keys: List[str]):
        super().__init__(api_keys, "MiniMax")
        # Circuit breaker state
        self._consecutive_failures = 0
        self._circuit_open_until: float = 0.0

    @property
    def is_available(self) -> bool:
        """Check availability considering circuit breaker state."""
        if not super().is_available:
            return False
        if self._consecutive_failures >= self._CB_FAILURE_THRESHOLD:
            if time.time() < self._circuit_open_until:
                return False
            # Cooldown expired -> half-open, allow one probe
        return True

    def _record_success(self, key: str) -> None:
        super()._record_success(key)
        # Reset circuit breaker on success
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0

    def _record_error(self, key: str) -> None:
        super()._record_error(key)
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._CB_FAILURE_THRESHOLD:
            self._circuit_open_until = time.time() + self._CB_COOLDOWN_SECONDS
            logger.warning(
                f"[MiniMax] Circuit breaker OPEN – "
                f"{self._consecutive_failures} consecutive failures, "
                f"cooldown {self._CB_COOLDOWN_SECONDS}s"
            )

    # ------------------------------------------------------------------
    # Time-range helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _time_hint(days: int, is_chinese: bool = True) -> str:
        """Build a time-hint string to append to the search query."""
        if is_chinese:
            if days <= 1:
                return "今天"
            elif days <= 3:
                return "最近三天"
            elif days <= 7:
                return "最近一週"
            else:
                return "最近一個月"
        else:
            if days <= 1:
                return "today"
            elif days <= 3:
                return "past 3 days"
            elif days <= 7:
                return "past week"
            else:
                return "past month"

    @staticmethod
    def _is_within_days(date_str: Optional[str], days: int) -> bool:
        """Check whether *date_str* falls within the last *days* days.

        Accepts common formats: ``2025-06-01``, ``2025/06/01``,
        ``Jun 1, 2025``, ISO-8601 with timezone, etc.
        Returns True when date_str is None or unparseable (keep the result).
        """
        if not date_str:
            return True
        try:
            from dateutil import parser as dateutil_parser
            dt = dateutil_parser.parse(date_str, fuzzy=True)
            from datetime import timedelta, timezone
            now = datetime.now(timezone.utc) if dt.tzinfo else datetime.now()
            return (now - dt) <= timedelta(days=days + 1)  # +1 buffer
        except Exception:
            return True  # Keep result when date is unparseable

    # ------------------------------------------------------------------

    def _do_search(self, query: str, api_key: str, max_results: int, days: int = 7) -> SearchResponse:
        """Execute MiniMax web search."""
        try:
            # Detect language hint from query (simple heuristic)
            has_cjk = any('\u4e00' <= ch <= '\u9fff' for ch in query)
            time_hint = self._time_hint(days, is_chinese=has_cjk)
            augmented_query = f"{query} {time_hint}"

            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
                'MM-API-Source': 'Minimax-MCP',
            }
            payload = {"q": augmented_query}

            response = _post_with_retry(
                self.API_ENDPOINT, headers=headers, json=payload, timeout=15
            )

            # HTTP error handling
            if response.status_code != 200:
                error_msg = self._parse_http_error(response)
                logger.warning(f"[MiniMax] Search failed: {error_msg}")
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message=error_msg,
                )

            data = response.json()

            # Check base_resp status
            base_resp = data.get('base_resp', {})
            if base_resp.get('status_code', 0) != 0:
                error_msg = base_resp.get('status_msg', 'Unknown API error')
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message=error_msg,
                )

            logger.info(f"[MiniMax] Search done, query='{query}'")
            logger.debug(f"[MiniMax] Raw response keys: {list(data.keys())}")

            # Parse organic results
            results: List[SearchResult] = []
            for item in data.get('organic', []):
                date_val = item.get('date')

                # Client-side time filtering
                if not self._is_within_days(date_val, days):
                    continue

                results.append(SearchResult(
                    title=item.get('title', ''),
                    snippet=(item.get('snippet', '') or '')[:500],
                    url=item.get('link', ''),
                    source=self._extract_domain(item.get('link', '')),
                    published_date=date_val,
                ))

                if len(results) >= max_results:
                    break

            logger.info(f"[MiniMax] Parsed {len(results)} results (after time filter)")

            return SearchResponse(
                query=query,
                results=results,
                provider=self.name,
                success=True,
            )

        except requests.exceptions.Timeout:
            error_msg = "Request timeout"
            logger.error(f"[MiniMax] {error_msg}")
            return SearchResponse(
                query=query, results=[], provider=self.name,
                success=False, error_message=error_msg,
            )
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error: {e}"
            logger.error(f"[MiniMax] {error_msg}")
            return SearchResponse(
                query=query, results=[], provider=self.name,
                success=False, error_message=error_msg,
            )
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            logger.error(f"[MiniMax] {error_msg}")
            return SearchResponse(
                query=query, results=[], provider=self.name,
                success=False, error_message=error_msg,
            )

    @staticmethod
    def _parse_http_error(response) -> str:
        """Parse HTTP error response from MiniMax API."""
        try:
            ct = response.headers.get('content-type', '')
            if 'json' in ct:
                err = response.json()
                base_resp = err.get('base_resp', {})
                msg = base_resp.get('status_msg') or err.get('message') or str(err)
                return msg
            return response.text[:200]
        except Exception:
            return f"HTTP {response.status_code}: {response.text[:200]}"

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Extract domain from URL as source label."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.replace('www.', '')
            return domain or '未知來源'
        except Exception:
            return '未知來源'


class BraveSearchProvider(BaseSearchProvider):
    """
    Brave Search 搜尋引擎

    特點：
    - 隱私優先的獨立搜尋引擎
    - 索引超過300億頁面
    - 免費層可用
    - 支援時間範圍過濾

    文件：https://brave.com/search/api/
    """

    API_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_keys: List[str]):
        super().__init__(api_keys, "Brave")

    def _do_search(self, query: str, api_key: str, max_results: int, days: int = 7) -> SearchResponse:
        """執行 Brave 搜尋"""
        try:
            # 請求頭
            headers = {
                'X-Subscription-Token': api_key,
                'Accept': 'application/json'
            }

            # 確定時間範圍（freshness 引數）
            if days <= 1:
                freshness = "pd"  # Past day (24小時)
            elif days <= 7:
                freshness = "pw"  # Past week
            elif days <= 30:
                freshness = "pm"  # Past month
            else:
                freshness = "py"  # Past year

            # 請求引數
            params = {
                "q": query,
                "count": min(max_results, 20),  # Brave 最大支援20條
                "freshness": freshness,
                "search_lang": "en",  # 英文內容（US股票優先）
                "country": "US",  # 美國區域偏好
                "safesearch": "moderate"
            }

            # 執行搜尋（GET 請求）
            response = requests.get(
                self.API_ENDPOINT,
                headers=headers,
                params=params,
                timeout=10
            )

            # 檢查HTTP狀態碼
            if response.status_code != 200:
                error_msg = self._parse_error(response)
                logger.warning(f"[Brave] 搜尋失敗: {error_msg}")
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message=error_msg
                )

            # 解析響應
            try:
                data = response.json()
            except ValueError as e:
                error_msg = f"響應JSON解析失敗: {str(e)}"
                logger.error(f"[Brave] {error_msg}")
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message=error_msg
                )

            logger.info(f"[Brave] 搜尋完成，query='{query}'")
            logger.debug(f"[Brave] 原始響應: {data}")

            # 解析搜尋結果
            results = []
            web_data = data.get('web', {})
            web_results = web_data.get('results', [])

            for item in web_results[:max_results]:
                # 解析釋出日期（ISO 8601 格式）
                published_date = None
                age = item.get('age') or item.get('page_age')
                if age:
                    try:
                        # 轉換 ISO 格式為簡單日期字串
                        dt = datetime.fromisoformat(age.replace('Z', '+00:00'))
                        published_date = dt.strftime('%Y-%m-%d')
                    except (ValueError, AttributeError):
                        published_date = age  # 解析失敗時使用原始值

                results.append(SearchResult(
                    title=item.get('title', ''),
                    snippet=item.get('description', '')[:500],  # 擷取到500字元
                    url=item.get('url', ''),
                    source=self._extract_domain(item.get('url', '')),
                    published_date=published_date
                ))

            logger.info(f"[Brave] 成功解析 {len(results)} 條結果")

            return SearchResponse(
                query=query,
                results=results,
                provider=self.name,
                success=True
            )

        except requests.exceptions.Timeout:
            error_msg = "請求超時"
            logger.error(f"[Brave] {error_msg}")
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=error_msg
            )
        except requests.exceptions.RequestException as e:
            error_msg = f"網路請求失敗: {str(e)}"
            logger.error(f"[Brave] {error_msg}")
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=error_msg
            )
        except Exception as e:
            error_msg = f"未知錯誤: {str(e)}"
            logger.error(f"[Brave] {error_msg}")
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=error_msg
            )

    def _parse_error(self, response) -> str:
        """解析錯誤響應"""
        try:
            if response.headers.get('content-type', '').startswith('application/json'):
                error_data = response.json()
                # Brave API 返回的錯誤格式
                if 'message' in error_data:
                    return error_data['message']
                if 'error' in error_data:
                    return error_data['error']
                return str(error_data)
            return response.text[:200]
        except Exception:
            return f"HTTP {response.status_code}: {response.text[:200]}"

    @staticmethod
    def _extract_domain(url: str) -> str:
        """從 URL 提取域名作為來源"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.replace('www.', '')
            return domain or '未知來源'
        except Exception:
            return '未知來源'


class SearXNGSearchProvider(BaseSearchProvider):
    """
    SearXNG search engine (self-hosted, no quota).

    Uses base_urls as "keys" for load balancing. Requires format: json in settings.yml.
    """

    def __init__(self, base_urls: List[str]):
        super().__init__(base_urls, "SearXNG")

    @staticmethod
    def _parse_http_error(response) -> str:
        """Parse HTTP error details for easier diagnostics."""
        try:
            raw_content_type = response.headers.get("content-type", "")
            content_type = raw_content_type if isinstance(raw_content_type, str) else ""
            if "json" in content_type:
                error_data = response.json()
                if isinstance(error_data, dict):
                    message = error_data.get("error") or error_data.get("message")
                    if message:
                        return str(message)
                return str(error_data)
            raw_text = getattr(response, "text", "")
            body = raw_text.strip() if isinstance(raw_text, str) else ""
            return body[:200] if body else f"HTTP {response.status_code}"
        except Exception:
            raw_text = getattr(response, "text", "")
            body = raw_text if isinstance(raw_text, str) else ""
            return f"HTTP {response.status_code}: {body[:200]}"

    def _do_search(  # type: ignore[override]
        self, query: str, base_url: str, max_results: int, days: int = 7
    ) -> SearchResponse:
        """Execute SearXNG search."""
        try:
            base = base_url.rstrip("/")
            search_url = base if base.endswith("/search") else base + "/search"

            if days <= 1:
                time_range = "day"
            elif days <= 7:
                time_range = "week"
            elif days <= 30:
                time_range = "month"
            else:
                time_range = "year"

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            params = {
                "q": query,
                "format": "json",
                "time_range": time_range,
                "pageno": 1,
            }

            response = _get_with_retry(search_url, headers=headers, params=params, timeout=10)

            if response.status_code != 200:
                error_msg = self._parse_http_error(response)
                if response.status_code == 403:
                    error_msg = (
                        f"{error_msg}；SearXNG 例項可能未啟用 JSON 輸出（請檢查 settings.yml），"
                        "或例項/代理拒絕了本次訪問"
                    )
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message=error_msg,
                )

            try:
                data = response.json()
            except Exception:
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message="響應JSON解析失敗",
                )

            if not isinstance(data, dict):
                return SearchResponse(
                    query=query,
                    results=[],
                    provider=self.name,
                    success=False,
                    error_message="響應格式無效",
                )

            raw = data.get("results", [])
            if not isinstance(raw, list):
                raw = []

            results = []
            for item in raw:
                if not isinstance(item, dict):
                    continue
                url_val = item.get("url")
                if not url_val:
                    continue
                raw_published_date = item.get("publishedDate")

                snippet = (item.get("content") or item.get("description") or "")[:500]
                published_date = None
                if raw_published_date:
                    try:
                        dt = datetime.fromisoformat(raw_published_date.replace("Z", "+00:00"))
                        published_date = dt.strftime("%Y-%m-%d")
                    except (ValueError, AttributeError):
                        published_date = raw_published_date

                results.append(
                    SearchResult(
                        title=item.get("title", ""),
                        snippet=snippet,
                        url=url_val,
                        source=self._extract_domain(url_val),
                        published_date=published_date,
                    )
                )
                if len(results) >= max_results:
                    break

            return SearchResponse(query=query, results=results, provider=self.name, success=True)

        except requests.exceptions.Timeout:
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message="請求超時",
            )
        except requests.exceptions.RequestException as e:
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=f"網路請求失敗: {e}",
            )
        except Exception as e:
            return SearchResponse(
                query=query,
                results=[],
                provider=self.name,
                success=False,
                error_message=f"未知錯誤: {e}",
            )

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Extract domain from URL as source label."""
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            domain = parsed.netloc.replace("www.", "")
            return domain or "未知來源"
        except Exception:
            return "未知來源"


class SearchService:
    """
    搜尋服務
    
    功能：
    1. 管理多個搜尋引擎
    2. 自動故障轉移
    3. 結果聚合和格式化
    4. 資料來源失敗時的增強搜尋（股價、走勢等）
    5. 港股/美股自動使用英文搜尋關鍵詞
    """
    
    # 增強搜尋關鍵詞模板（A股 中文）
    ENHANCED_SEARCH_KEYWORDS = [
        "{name} 股票 今日 股價",
        "{name} {code} 最新 行情 走勢",
        "{name} 股票 分析 走勢圖",
        "{name} K線 技術分析",
        "{name} {code} 漲跌 成交量",
    ]

    # 增強搜尋關鍵詞模板（港股/美股 英文）
    ENHANCED_SEARCH_KEYWORDS_EN = [
        "{name} stock price today",
        "{name} {code} latest quote trend",
        "{name} stock analysis chart",
        "{name} technical analysis",
        "{name} {code} performance volume",
    ]
    NEWS_OVERSAMPLE_FACTOR = 2
    NEWS_OVERSAMPLE_MAX = 10
    FUTURE_TOLERANCE_DAYS = 1
    
    def __init__(
        self,
        bocha_keys: Optional[List[str]] = None,
        tavily_keys: Optional[List[str]] = None,
        brave_keys: Optional[List[str]] = None,
        serpapi_keys: Optional[List[str]] = None,
        minimax_keys: Optional[List[str]] = None,
        searxng_base_urls: Optional[List[str]] = None,
        news_max_age_days: int = 3,
        news_strategy_profile: str = "short",
    ):
        """
        初始化搜尋服務

        Args:
            bocha_keys: 博查搜尋 API Key 列表
            tavily_keys: Tavily API Key 列表
            brave_keys: Brave Search API Key 列表
            serpapi_keys: SerpAPI Key 列表
            minimax_keys: MiniMax API Key 列表
            searxng_base_urls: SearXNG 例項地址列表（自建無配額兜底）
            news_max_age_days: 新聞最大時效（天）
            news_strategy_profile: 新聞視窗策略檔位（ultra_short/short/medium/long）
        """
        self._providers: List[BaseSearchProvider] = []
        self.news_max_age_days = max(1, news_max_age_days)
        raw_profile = (news_strategy_profile or "short").strip().lower()
        self.news_strategy_profile = normalize_news_strategy_profile(news_strategy_profile)
        if raw_profile != self.news_strategy_profile:
            logger.warning(
                "NEWS_STRATEGY_PROFILE '%s' 無效，已回退為 'short'",
                news_strategy_profile,
            )
        self.news_window_days = resolve_news_window_days(
            news_max_age_days=self.news_max_age_days,
            news_strategy_profile=self.news_strategy_profile,
        )
        self.news_profile_days = NEWS_STRATEGY_WINDOWS.get(
            self.news_strategy_profile,
            NEWS_STRATEGY_WINDOWS["short"],
        )

        # 初始化搜尋引擎（按優先順序排序）
        # 1. Bocha 優先（中文搜尋最佳化，AI摘要）
        if bocha_keys:
            self._providers.append(BochaSearchProvider(bocha_keys))
            logger.info(f"已配置 Bocha 搜尋，共 {len(bocha_keys)} 個 API Key")

        # 2. Tavily（免費額度更多，每月 1000 次）
        if tavily_keys:
            self._providers.append(TavilySearchProvider(tavily_keys))
            logger.info(f"已配置 Tavily 搜尋，共 {len(tavily_keys)} 個 API Key")

        # 3. Brave Search（隱私優先，全球覆蓋）
        if brave_keys:
            self._providers.append(BraveSearchProvider(brave_keys))
            logger.info(f"已配置 Brave 搜尋，共 {len(brave_keys)} 個 API Key")

        # 4. SerpAPI 作為備選（每月 100 次）
        if serpapi_keys:
            self._providers.append(SerpAPISearchProvider(serpapi_keys))
            logger.info(f"已配置 SerpAPI 搜尋，共 {len(serpapi_keys)} 個 API Key")

        # 5. MiniMax（Coding Plan Web Search，結構化結果）
        if minimax_keys:
            self._providers.append(MiniMaxSearchProvider(minimax_keys))
            logger.info(f"已配置 MiniMax 搜尋，共 {len(minimax_keys)} 個 API Key")

        # 6. SearXNG（自建例項，無配額兜底，最後兜底）
        if searxng_base_urls:
            self._providers.append(SearXNGSearchProvider(searxng_base_urls))
            logger.info(f"已配置 SearXNG 搜尋，共 {len(searxng_base_urls)} 個例項")
        
        if not self._providers:
            logger.warning("未配置任何搜尋引擎 API Key，新聞搜尋功能將不可用")

        # In-memory search result cache: {cache_key: (timestamp, SearchResponse)}
        self._cache: Dict[str, Tuple[float, 'SearchResponse']] = {}
        # Default cache TTL in seconds (10 minutes)
        self._cache_ttl: int = 600
        logger.info(
            "新聞時效策略已啟用: profile=%s, profile_days=%s, NEWS_MAX_AGE_DAYS=%s, effective_window=%s",
            self.news_strategy_profile,
            self.news_profile_days,
            self.news_max_age_days,
            self.news_window_days,
        )
    
    @staticmethod
    def _is_foreign_stock(stock_code: str) -> bool:
        """判斷是否為港股或美股"""
        import re
        code = stock_code.strip()
        # 美股：1-5個大寫字母，可能包含點（如 BRK.B）
        if re.match(r'^[A-Za-z]{1,5}(\.[A-Za-z])?$', code):
            return True
        # 港股：帶 hk 字首或 5位純數字
        lower = code.lower()
        if lower.startswith('hk'):
            return True
        if code.isdigit() and len(code) == 5:
            return True
        return False

    # A-share ETF code prefixes (Shanghai 51/52/56/58, Shenzhen 15/16/18)
    _A_ETF_PREFIXES = ('51', '52', '56', '58', '15', '16', '18')
    _ETF_NAME_KEYWORDS = ('ETF', 'FUND', 'TRUST', 'INDEX', 'TRACKER', 'UNIT')  # US/HK ETF name hints

    @staticmethod
    def is_index_or_etf(stock_code: str, stock_name: str) -> bool:
        """
        Judge if symbol is index-tracking ETF or market index.
        For such symbols, analysis focuses on index movement only, not issuer company risks.
        """
        code = (stock_code or '').strip().split('.')[0]
        if not code:
            return False
        # A-share ETF
        if code.isdigit() and len(code) == 6 and code.startswith(SearchService._A_ETF_PREFIXES):
            return True
        # US index (SPX, DJI, IXIC etc.)
        if is_us_index_code(code):
            return True
        # US/HK ETF: foreign symbol + name contains fund-like keywords
        if SearchService._is_foreign_stock(code):
            name_upper = (stock_name or '').upper()
            return any(kw in name_upper for kw in SearchService._ETF_NAME_KEYWORDS)
        return False

    @property
    def is_available(self) -> bool:
        """檢查是否有可用的搜尋引擎"""
        return any(p.is_available for p in self._providers)

    def _cache_key(self, query: str, max_results: int, days: int) -> str:
        """Build a cache key from query parameters."""
        return f"{query}|{max_results}|{days}"

    def _get_cached(self, key: str) -> Optional['SearchResponse']:
        """Return cached SearchResponse if still valid, else None."""
        entry = self._cache.get(key)
        if entry is None:
            return None
        ts, response = entry
        if time.time() - ts > self._cache_ttl:
            del self._cache[key]
            return None
        logger.debug(f"Search cache hit: {key[:60]}...")
        return response

    def _put_cache(self, key: str, response: 'SearchResponse') -> None:
        """Store a successful SearchResponse in cache."""
        # Hard cap: evict oldest entries when cache exceeds limit
        _MAX_CACHE_SIZE = 500
        if len(self._cache) >= _MAX_CACHE_SIZE:
            now = time.time()
            # First pass: remove expired entries
            expired = [k for k, (ts, _) in self._cache.items() if now - ts > self._cache_ttl]
            for k in expired:
                del self._cache[k]
            # Second pass: if still over limit, evict oldest entries (FIFO)
            if len(self._cache) >= _MAX_CACHE_SIZE:
                excess = len(self._cache) - _MAX_CACHE_SIZE + 1
                oldest = sorted(self._cache.keys(), key=lambda k: self._cache[k][0])[:excess]
                for k in oldest:
                    del self._cache[k]
        self._cache[key] = (time.time(), response)

    def _effective_news_window_days(self) -> int:
        """Resolve effective news window from strategy profile and global max-age."""
        return resolve_news_window_days(
            news_max_age_days=self.news_max_age_days,
            news_strategy_profile=self.news_strategy_profile,
        )

    @classmethod
    def _provider_request_size(cls, max_results: int) -> int:
        """Apply light overfetch before time filtering to avoid sparse outputs."""
        target = max(1, int(max_results))
        return max(target, min(target * cls.NEWS_OVERSAMPLE_FACTOR, cls.NEWS_OVERSAMPLE_MAX))

    @staticmethod
    def _parse_relative_news_date(text: str, now: datetime) -> Optional[date]:
        """Parse common Chinese/English relative-time strings."""
        raw = (text or "").strip()
        if not raw:
            return None

        lower = raw.lower()
        if raw in {"今天", "今日", "剛剛"} or lower in {"today", "just now", "now"}:
            return now.date()
        if raw == "昨天" or lower == "yesterday":
            return (now - timedelta(days=1)).date()
        if raw == "前天":
            return (now - timedelta(days=2)).date()

        zh = re.match(r"^\s*(\d+)\s*(分鐘|小時|天|周|個月|月|年)\s*前\s*$", raw)
        if zh:
            amount = int(zh.group(1))
            unit = zh.group(2)
            if unit == "分鐘":
                return (now - timedelta(minutes=amount)).date()
            if unit == "小時":
                return (now - timedelta(hours=amount)).date()
            if unit == "天":
                return (now - timedelta(days=amount)).date()
            if unit == "周":
                return (now - timedelta(weeks=amount)).date()
            if unit in {"個月", "月"}:
                return (now - timedelta(days=amount * 30)).date()
            if unit == "年":
                return (now - timedelta(days=amount * 365)).date()

        en = re.match(
            r"^\s*(\d+)\s*(minute|minutes|min|mins|hour|hours|day|days|week|weeks|month|months|year|years)\s*ago\s*$",
            lower,
        )
        if en:
            amount = int(en.group(1))
            unit = en.group(2)
            if unit in {"minute", "minutes", "min", "mins"}:
                return (now - timedelta(minutes=amount)).date()
            if unit in {"hour", "hours"}:
                return (now - timedelta(hours=amount)).date()
            if unit in {"day", "days"}:
                return (now - timedelta(days=amount)).date()
            if unit in {"week", "weeks"}:
                return (now - timedelta(weeks=amount)).date()
            if unit in {"month", "months"}:
                return (now - timedelta(days=amount * 30)).date()
            if unit in {"year", "years"}:
                return (now - timedelta(days=amount * 365)).date()

        return None

    @classmethod
    def _normalize_news_publish_date(cls, value: Any) -> Optional[date]:
        """Normalize provider date value into a date object."""
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is not None:
                local_tz = datetime.now().astimezone().tzinfo or timezone.utc
                return value.astimezone(local_tz).date()
            return value.date()
        if isinstance(value, date):
            return value

        text = str(value).strip()
        if not text:
            return None
        now = datetime.now()
        local_tz = now.astimezone().tzinfo or timezone.utc

        relative_date = cls._parse_relative_news_date(text, now)
        if relative_date:
            return relative_date

        # Unix timestamp fallback
        if text.isdigit() and len(text) in (10, 13):
            try:
                ts = int(text[:10]) if len(text) == 13 else int(text)
                # Provider timestamps are typically UTC epoch seconds.
                # Normalize to local date to keep window checks aligned with local "today".
                return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(local_tz).date()
            except (OSError, OverflowError, ValueError):
                pass

        iso_candidate = text.replace("Z", "+00:00")
        try:
            parsed_iso = datetime.fromisoformat(iso_candidate)
            if parsed_iso.tzinfo is not None:
                return parsed_iso.astimezone(local_tz).date()
            return parsed_iso.date()
        except ValueError:
            pass

        normalized = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", text, flags=re.IGNORECASE)

        try:
            parsed_rfc = parsedate_to_datetime(normalized)
            if parsed_rfc:
                if parsed_rfc.tzinfo is not None:
                    return parsed_rfc.astimezone(local_tz).date()
                return parsed_rfc.date()
        except (TypeError, ValueError):
            pass

        zh_match = re.search(r"(\d{4})\s*[年/\-.]\s*(\d{1,2})\s*[月/\-.]\s*(\d{1,2})\s*日?", text)
        if zh_match:
            try:
                return date(int(zh_match.group(1)), int(zh_match.group(2)), int(zh_match.group(3)))
            except ValueError:
                pass

        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%Y/%m/%d",
            "%Y.%m.%d %H:%M:%S",
            "%Y.%m.%d %H:%M",
            "%Y.%m.%d",
            "%Y%m%d",
            "%b %d, %Y",
            "%B %d, %Y",
            "%d %b %Y",
            "%d %B %Y",
            "%a, %d %b %Y %H:%M:%S %z",
        ):
            try:
                parsed_dt = datetime.strptime(normalized, fmt)
                if parsed_dt.tzinfo is not None:
                    return parsed_dt.astimezone(local_tz).date()
                return parsed_dt.date()
            except ValueError:
                continue

        return None

    def _filter_news_response(
        self,
        response: SearchResponse,
        *,
        search_days: int,
        max_results: int,
        log_scope: str,
    ) -> SearchResponse:
        """Hard-filter results by published_date recency and normalize date strings."""
        if not response.success or not response.results:
            return response

        today = datetime.now().date()
        earliest = today - timedelta(days=max(0, int(search_days) - 1))
        latest = today + timedelta(days=self.FUTURE_TOLERANCE_DAYS)

        filtered: List[SearchResult] = []
        dropped_unknown = 0
        dropped_old = 0
        dropped_future = 0

        for item in response.results:
            published = self._normalize_news_publish_date(item.published_date)
            if published is None:
                dropped_unknown += 1
                continue
            if published < earliest:
                dropped_old += 1
                continue
            if published > latest:
                dropped_future += 1
                continue

            filtered.append(
                SearchResult(
                    title=item.title,
                    snippet=item.snippet,
                    url=item.url,
                    source=item.source,
                    published_date=published.isoformat(),
                )
            )
            if len(filtered) >= max_results:
                break

        if dropped_unknown or dropped_old or dropped_future:
            logger.info(
                "[新聞過濾] %s: provider=%s, total=%s, kept=%s, drop_unknown=%s, drop_old=%s, drop_future=%s, window=[%s,%s]",
                log_scope,
                response.provider,
                len(response.results),
                len(filtered),
                dropped_unknown,
                dropped_old,
                dropped_future,
                earliest.isoformat(),
                latest.isoformat(),
            )

        return SearchResponse(
            query=response.query,
            results=filtered,
            provider=response.provider,
            success=response.success,
            error_message=response.error_message,
            search_time=response.search_time,
        )
    
    def search_stock_news(
        self,
        stock_code: str,
        stock_name: str,
        max_results: int = 5,
        focus_keywords: Optional[List[str]] = None
    ) -> SearchResponse:
        """
        搜尋股票相關新聞
        
        Args:
            stock_code: 股票程式碼
            stock_name: 股票名稱
            max_results: 最大返回結果數
            focus_keywords: 重點關注的關鍵詞列表
            
        Returns:
            SearchResponse 物件
        """
        # 策略視窗優先：ultra_short/short/medium/long = 1/3/7/30 天，
        # 並統一受 NEWS_MAX_AGE_DAYS 上限約束。
        search_days = self._effective_news_window_days()
        provider_max_results = self._provider_request_size(max_results)

        # 構建搜尋查詢（最佳化搜尋效果）
        is_foreign = self._is_foreign_stock(stock_code)
        if focus_keywords:
            # 如果提供了關鍵詞，直接使用關鍵詞作為查詢
            query = " ".join(focus_keywords)
        elif is_foreign:
            # 港股/美股使用英文搜尋關鍵詞
            query = f"{stock_name} {stock_code} stock latest news"
        else:
            # 預設主查詢：股票名稱 + 核心關鍵詞
            query = f"{stock_name} {stock_code} 股票 最新訊息"

        logger.info(
            (
                "搜尋股票新聞: %s(%s), query='%s', 時間範圍: 近%s天 "
                "(profile=%s, NEWS_MAX_AGE_DAYS=%s), 目標條數=%s, provider請求條數=%s"
            ),
            stock_name,
            stock_code,
            query,
            search_days,
            self.news_strategy_profile,
            self.news_max_age_days,
            max_results,
            provider_max_results,
        )

        # Check cache first
        cache_key = self._cache_key(query, max_results, search_days)
        cached = self._get_cached(cache_key)
        if cached is not None:
            logger.info(f"使用快取搜尋結果: {stock_name}({stock_code})")
            return cached

        # 依次嘗試各個搜尋引擎（若過濾後為空，繼續嘗試下一引擎）
        had_provider_success = False
        for provider in self._providers:
            if not provider.is_available:
                continue
            
            response = provider.search(query, provider_max_results, days=search_days)
            filtered_response = self._filter_news_response(
                response,
                search_days=search_days,
                max_results=max_results,
                log_scope=f"{stock_code}:{provider.name}:stock_news",
            )
            had_provider_success = had_provider_success or bool(response.success)

            if filtered_response.success and filtered_response.results:
                logger.info(f"使用 {provider.name} 搜尋成功")
                self._put_cache(cache_key, filtered_response)
                return filtered_response
            else:
                if response.success and not filtered_response.results:
                    logger.info(
                        "%s 搜尋成功但過濾後無有效新聞，繼續嘗試下一引擎",
                        provider.name,
                    )
                else:
                    logger.warning(
                        "%s 搜尋失敗: %s，嘗試下一個引擎",
                        provider.name,
                        response.error_message,
                    )

        if had_provider_success:
            return SearchResponse(
                query=query,
                results=[],
                provider="Filtered",
                success=True,
                error_message=None,
            )
        
        # 所有引擎都失敗
        return SearchResponse(
            query=query,
            results=[],
            provider="None",
            success=False,
            error_message="所有搜尋引擎都不可用或搜尋失敗"
        )
    
    def search_stock_events(
        self,
        stock_code: str,
        stock_name: str,
        event_types: Optional[List[str]] = None
    ) -> SearchResponse:
        """
        搜尋股票特定事件（年報預告、減持等）
        
        專門針對交易決策相關的重要事件進行搜尋
        
        Args:
            stock_code: 股票程式碼
            stock_name: 股票名稱
            event_types: 事件型別列表
            
        Returns:
            SearchResponse 物件
        """
        if event_types is None:
            if self._is_foreign_stock(stock_code):
                event_types = ["earnings report", "insider selling", "quarterly results"]
            else:
                event_types = ["年報預告", "減持公告", "業績快報"]
        
        # 構建針對性查詢
        event_query = " OR ".join(event_types)
        query = f"{stock_name} ({event_query})"
        
        logger.info(f"搜尋股票事件: {stock_name}({stock_code}) - {event_types}")
        
        # 依次嘗試各個搜尋引擎
        for provider in self._providers:
            if not provider.is_available:
                continue
            
            response = provider.search(query, max_results=5)
            
            if response.success:
                return response
        
        return SearchResponse(
            query=query,
            results=[],
            provider="None",
            success=False,
            error_message="事件搜尋失敗"
        )
    
    def search_comprehensive_intel(
        self,
        stock_code: str,
        stock_name: str,
        max_searches: int = 3
    ) -> Dict[str, SearchResponse]:
        """
        多維度情報搜尋（同時使用多個引擎、多個維度）
        
        搜尋維度：
        1. 最新訊息 - 近期新聞動態
        2. 風險排查 - 減持、處罰、利空
        3. 業績預期 - 年報預告、業績快報
        
        Args:
            stock_code: 股票程式碼
            stock_name: 股票名稱
            max_searches: 最大搜尋次數
            
        Returns:
            {維度名稱: SearchResponse} 字典
        """
        results = {}
        search_count = 0

        is_foreign = self._is_foreign_stock(stock_code)
        is_index_etf = self.is_index_or_etf(stock_code, stock_name)

        if is_foreign:
            search_dimensions = [
                {'name': 'latest_news', 'query': f"{stock_name} {stock_code} latest news events", 'desc': '最新訊息'},
                {'name': 'market_analysis', 'query': f"{stock_name} analyst rating target price report", 'desc': '機構分析'},
                {'name': 'risk_check', 'query': (
                    f"{stock_name} {stock_code} index performance outlook tracking error"
                    if is_index_etf else f"{stock_name} risk insider selling lawsuit litigation"
                ), 'desc': '風險排查'},
                {'name': 'earnings', 'query': (
                    f"{stock_name} {stock_code} index performance composition outlook"
                    if is_index_etf else f"{stock_name} earnings revenue profit growth forecast"
                ), 'desc': '業績預期'},
                {'name': 'industry', 'query': (
                    f"{stock_name} {stock_code} index sector allocation holdings"
                    if is_index_etf else f"{stock_name} industry competitors market share outlook"
                ), 'desc': '行業分析'},
            ]
        else:
            search_dimensions = [
                {'name': 'latest_news', 'query': f"{stock_name} {stock_code} 最新 新聞 重大 事件", 'desc': '最新訊息'},
                {'name': 'market_analysis', 'query': f"{stock_name} 研報 目標價 評級 深度分析", 'desc': '機構分析'},
                {'name': 'risk_check', 'query': (
                    f"{stock_name} 指數走勢 跟蹤誤差 淨值 表現"
                    if is_index_etf else f"{stock_name} 減持 處罰 違規 訴訟 利空 風險"
                ), 'desc': '風險排查'},
                {'name': 'earnings', 'query': (
                    f"{stock_name} 指數成分 淨值 跟蹤表現"
                    if is_index_etf else f"{stock_name} 業績預告 財報 營收 淨利潤 同比增長"
                ), 'desc': '業績預期'},
                {'name': 'industry', 'query': (
                    f"{stock_name} 指數成分股 行業配置 權重"
                    if is_index_etf else f"{stock_name} 所在行業 競爭對手 市場份額 行業前景"
                ), 'desc': '行業分析'},
            ]
        
        search_days = self._effective_news_window_days()
        target_per_dimension = 3
        provider_max_results = self._provider_request_size(target_per_dimension)

        logger.info(
            (
                "開始多維度情報搜尋: %s(%s), 時間範圍: 近%s天 "
                "(profile=%s, NEWS_MAX_AGE_DAYS=%s), 目標條數=%s, provider請求條數=%s"
            ),
            stock_name,
            stock_code,
            search_days,
            self.news_strategy_profile,
            self.news_max_age_days,
            target_per_dimension,
            provider_max_results,
        )
        
        # 輪流使用不同的搜尋引擎
        provider_index = 0
        
        for dim in search_dimensions:
            if search_count >= max_searches:
                break
            
            # 選擇搜尋引擎（輪流使用）
            available_providers = [p for p in self._providers if p.is_available]
            if not available_providers:
                break
            
            provider = available_providers[provider_index % len(available_providers)]
            provider_index += 1
            
            logger.info(f"[情報搜尋] {dim['desc']}: 使用 {provider.name}")
            
            response = provider.search(
                dim['query'],
                max_results=provider_max_results,
                days=search_days,
            )
            filtered_response = self._filter_news_response(
                response,
                search_days=search_days,
                max_results=target_per_dimension,
                log_scope=f"{stock_code}:{provider.name}:{dim['name']}",
            )
            results[dim['name']] = filtered_response
            search_count += 1
            
            if response.success:
                logger.info(
                    "[情報搜尋] %s: 原始=%s條, 過濾後=%s條",
                    dim['desc'],
                    len(response.results),
                    len(filtered_response.results),
                )
            else:
                logger.warning(f"[情報搜尋] {dim['desc']}: 搜尋失敗 - {response.error_message}")
            
            # 短暫延遲避免請求過快
            time.sleep(0.5)
        
        return results
    
    def format_intel_report(self, intel_results: Dict[str, SearchResponse], stock_name: str) -> str:
        """
        格式化情報搜尋結果為報告
        
        Args:
            intel_results: 多維度搜尋結果
            stock_name: 股票名稱
            
        Returns:
            格式化的情報報告文字
        """
        lines = [f"【{stock_name} 情報搜尋結果】"]
        
        # 維度展示順序
        display_order = ['latest_news', 'market_analysis', 'risk_check', 'earnings', 'industry']
        
        for dim_name in display_order:
            if dim_name not in intel_results:
                continue
                
            resp = intel_results[dim_name]
            
            # 獲取維度描述
            dim_desc = dim_name
            if dim_name == 'latest_news': dim_desc = '📰 最新訊息'
            elif dim_name == 'market_analysis': dim_desc = '📈 機構分析'
            elif dim_name == 'risk_check': dim_desc = '⚠️ 風險排查'
            elif dim_name == 'earnings': dim_desc = '📊 業績預期'
            elif dim_name == 'industry': dim_desc = '🏭 行業分析'
            
            lines.append(f"\n{dim_desc} (來源: {resp.provider}):")
            if resp.success and resp.results:
                # 增加顯示條數
                for i, r in enumerate(resp.results[:4], 1):
                    date_str = f" [{r.published_date}]" if r.published_date else ""
                    lines.append(f"  {i}. {r.title}{date_str}")
                    # 如果摘要太短，可能資訊量不足
                    snippet = r.snippet[:150] if len(r.snippet) > 20 else r.snippet
                    lines.append(f"     {snippet}...")
            else:
                lines.append("  未找到相關資訊")
        
        return "\n".join(lines)
    
    def batch_search(
        self,
        stocks: List[Dict[str, str]],
        max_results_per_stock: int = 3,
        delay_between: float = 1.0
    ) -> Dict[str, SearchResponse]:
        """
        Batch search news for multiple stocks.
        
        Args:
            stocks: List of stocks
            max_results_per_stock: Max results per stock
            delay_between: Delay between searches (seconds)
            
        Returns:
            Dict of results
        """
        results = {}
        
        for i, stock in enumerate(stocks):
            if i > 0:
                time.sleep(delay_between)
            
            code = stock.get('code', '')
            name = stock.get('name', '')
            
            response = self.search_stock_news(code, name, max_results_per_stock)
            results[code] = response
        
        return results

    def search_stock_price_fallback(
        self,
        stock_code: str,
        stock_name: str,
        max_attempts: int = 3,
        max_results: int = 5
    ) -> SearchResponse:
        """
        Enhance search when data sources fail.
        
        When all data sources (efinance, akshare, tushare, baostock, etc.) fail to get
        stock data, use search engines to find stock trends and price info as supplemental data for AI analysis.
        
        Strategy:
        1. Search using multiple keyword templates
        2. Try all available search engines for each keyword
        3. Aggregate and deduplicate results
        
        Args:
            stock_code: Stock Code
            stock_name: Stock Name
            max_attempts: Max search attempts (using different keywords)
            max_results: Max results to return
            
        Returns:
            SearchResponse object with aggregated results
        """

        if not self.is_available:
            return SearchResponse(
                query=f"{stock_name} 股價走勢",
                results=[],
                provider="None",
                success=False,
                error_message="未配置搜尋引擎 API Key"
            )
        
        logger.info(f"[增強搜尋] 資料來源失敗，啟動增強搜尋: {stock_name}({stock_code})")
        
        all_results = []
        seen_urls = set()
        successful_providers = []
        
        # 使用多個關鍵詞模板搜尋
        is_foreign = self._is_foreign_stock(stock_code)
        keywords = self.ENHANCED_SEARCH_KEYWORDS_EN if is_foreign else self.ENHANCED_SEARCH_KEYWORDS
        for i, keyword_template in enumerate(keywords[:max_attempts]):
            query = keyword_template.format(name=stock_name, code=stock_code)
            
            logger.info(f"[增強搜尋] 第 {i+1}/{max_attempts} 次搜尋: {query}")
            
            # 依次嘗試各個搜尋引擎
            for provider in self._providers:
                if not provider.is_available:
                    continue
                
                try:
                    response = provider.search(query, max_results=3)
                    
                    if response.success and response.results:
                        # 去重並新增結果
                        for result in response.results:
                            if result.url not in seen_urls:
                                seen_urls.add(result.url)
                                all_results.append(result)
                                
                        if provider.name not in successful_providers:
                            successful_providers.append(provider.name)
                        
                        logger.info(f"[增強搜尋] {provider.name} 返回 {len(response.results)} 條結果")
                        break  # 成功後跳到下一個關鍵詞
                    else:
                        logger.debug(f"[增強搜尋] {provider.name} 無結果或失敗")
                        
                except Exception as e:
                    logger.warning(f"[增強搜尋] {provider.name} 搜尋異常: {e}")
                    continue
            
            # 短暫延遲避免請求過快
            if i < max_attempts - 1:
                time.sleep(0.5)
        
        # 彙總結果
        if all_results:
            # 擷取前 max_results 條
            final_results = all_results[:max_results]
            provider_str = ", ".join(successful_providers) if successful_providers else "None"
            
            logger.info(f"[增強搜尋] 完成，共獲取 {len(final_results)} 條結果（來源: {provider_str}）")
            
            return SearchResponse(
                query=f"{stock_name}({stock_code}) 股價走勢",
                results=final_results,
                provider=provider_str,
                success=True,
            )
        else:
            logger.warning(f"[增強搜尋] 所有搜尋均未返回結果")
            return SearchResponse(
                query=f"{stock_name}({stock_code}) 股價走勢",
                results=[],
                provider="None",
                success=False,
                error_message="增強搜尋未找到相關資訊"
            )

    def search_stock_with_enhanced_fallback(
        self,
        stock_code: str,
        stock_name: str,
        include_news: bool = True,
        include_price: bool = False,
        max_results: int = 5
    ) -> Dict[str, SearchResponse]:
        """
        綜合搜尋介面（支援新聞和股價資訊）
        
        當 include_price=True 時，會同時搜尋新聞和股價資訊。
        主要用於資料來源完全失敗時的兜底方案。
        
        Args:
            stock_code: 股票程式碼
            stock_name: 股票名稱
            include_news: 是否搜尋新聞
            include_price: 是否搜尋股價/走勢資訊
            max_results: 每類搜尋的最大結果數
            
        Returns:
            {'news': SearchResponse, 'price': SearchResponse} 字典
        """
        results = {}
        
        if include_news:
            results['news'] = self.search_stock_news(
                stock_code, 
                stock_name, 
                max_results=max_results
            )
        
        if include_price:
            results['price'] = self.search_stock_price_fallback(
                stock_code,
                stock_name,
                max_attempts=3,
                max_results=max_results
            )
        
        return results

    def format_price_search_context(self, response: SearchResponse) -> str:
        """
        將股價搜尋結果格式化為 AI 分析上下文
        
        Args:
            response: 搜尋響應物件
            
        Returns:
            格式化的文字，可直接用於 AI 分析
        """
        if not response.success or not response.results:
            return "【股價走勢搜尋】未找到相關資訊，請以其他渠道資料為準。"
        
        lines = [
            f"【股價走勢搜尋結果】（來源: {response.provider}）",
            "⚠️ 注意：以下資訊來自網路搜尋，僅供參考，可能存在延遲或不準確。",
            ""
        ]
        
        for i, result in enumerate(response.results, 1):
            date_str = f" [{result.published_date}]" if result.published_date else ""
            lines.append(f"{i}. 【{result.source}】{result.title}{date_str}")
            lines.append(f"   {result.snippet[:200]}...")
            lines.append("")
        
        return "\n".join(lines)


# === 便捷函式 ===
_search_service: Optional[SearchService] = None


def get_search_service() -> SearchService:
    """獲取搜尋服務單例"""
    global _search_service
    
    if _search_service is None:
        from src.config import get_config
        config = get_config()
        
        _search_service = SearchService(
            bocha_keys=config.bocha_api_keys,
            tavily_keys=config.tavily_api_keys,
            brave_keys=config.brave_api_keys,
            serpapi_keys=config.serpapi_keys,
            minimax_keys=config.minimax_api_keys,
            searxng_base_urls=config.searxng_base_urls,
            news_max_age_days=config.news_max_age_days,
            news_strategy_profile=getattr(config, "news_strategy_profile", "short"),
        )
    
    return _search_service


def reset_search_service() -> None:
    """重置搜尋服務（用於測試）"""
    global _search_service
    _search_service = None


if __name__ == "__main__":
    # 測試搜尋服務
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s'
    )
    
    # 手動測試（需要配置 API Key）
    service = get_search_service()
    
    if service.is_available:
        print("=== 測試股票新聞搜尋 ===")
        response = service.search_stock_news("300389", "艾比森")
        print(f"搜尋狀態: {'成功' if response.success else '失敗'}")
        print(f"搜尋引擎: {response.provider}")
        print(f"結果數量: {len(response.results)}")
        print(f"耗時: {response.search_time:.2f}s")
        print("\n" + response.to_context())
    else:
        print("未配置搜尋引擎 API Key，跳過測試")
