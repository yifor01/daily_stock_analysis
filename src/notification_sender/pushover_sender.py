# -*- coding: utf-8 -*-
"""
Pushover 傳送提醒服務

職責：
1. 透過 Pushover API 傳送 Pushover 訊息
"""
import logging
from typing import Optional
from datetime import datetime
import requests

from src.config import Config
from src.formatters import markdown_to_plain_text


logger = logging.getLogger(__name__)


class PushoverSender:
    
    def __init__(self, config: Config):
        """
        初始化 Pushover 配置

        Args:
            config: 配置物件
        """
        self._pushover_config = {
            'user_key': getattr(config, 'pushover_user_key', None),
            'api_token': getattr(config, 'pushover_api_token', None),
        }
        
    def _is_pushover_configured(self) -> bool:
        """檢查 Pushover 配置是否完整"""
        return bool(self._pushover_config['user_key'] and self._pushover_config['api_token'])

    def send_to_pushover(self, content: str, title: Optional[str] = None) -> bool:
        """
        推送訊息到 Pushover
        
        Pushover API 格式：
        POST https://api.pushover.net/1/messages.json
        {
            "token": "應用 API Token",
            "user": "使用者 Key",
            "message": "訊息內容",
            "title": "標題（可選）"
        }
        
        Pushover 特點：
        - 支援 iOS/Android/桌面多平臺推送
        - 訊息限制 1024 字元
        - 支援優先順序設定
        - 支援 HTML 格式
        
        Args:
            content: 訊息內容（Markdown 格式，會轉為純文字）
            title: 訊息標題（可選，預設為"股票分析報告"）
            
        Returns:
            是否傳送成功
        """
        if not self._is_pushover_configured():
            logger.warning("Pushover 配置不完整，跳過推送")
            return False
        
        user_key = self._pushover_config['user_key']
        api_token = self._pushover_config['api_token']
        
        # Pushover API 端點
        api_url = "https://api.pushover.net/1/messages.json"
        
        # 處理訊息標題
        if title is None:
            date_str = datetime.now().strftime('%Y-%m-%d')
            title = f"📈 股票分析報告 - {date_str}"
        
        # Pushover 訊息限制 1024 字元
        max_length = 1024
        
        # 轉換 Markdown 為純文字（Pushover 支援 HTML，但純文字更通用）
        plain_content = markdown_to_plain_text(content)
        
        if len(plain_content) <= max_length:
            # 單條訊息傳送
            return self._send_pushover_message(api_url, user_key, api_token, plain_content, title)
        else:
            # 分段傳送長訊息
            return self._send_pushover_chunked(api_url, user_key, api_token, plain_content, title, max_length)
      
    def _send_pushover_message(
        self, 
        api_url: str, 
        user_key: str, 
        api_token: str, 
        message: str, 
        title: str,
        priority: int = 0
    ) -> bool:
        """
        傳送單條 Pushover 訊息
        
        Args:
            api_url: Pushover API 端點
            user_key: 使用者 Key
            api_token: 應用 API Token
            message: 訊息內容
            title: 訊息標題
            priority: 優先順序 (-2 ~ 2，預設 0)
        """
        try:
            payload = {
                "token": api_token,
                "user": user_key,
                "message": message,
                "title": title,
                "priority": priority,
            }
            
            response = requests.post(api_url, data=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 1:
                    logger.info("Pushover 訊息傳送成功")
                    return True
                else:
                    errors = result.get('errors', ['未知錯誤'])
                    logger.error(f"Pushover 返回錯誤: {errors}")
                    return False
            else:
                logger.error(f"Pushover 請求失敗: HTTP {response.status_code}")
                logger.debug(f"響應內容: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"傳送 Pushover 訊息失敗: {e}")
            return False
    
    def _send_pushover_chunked(
        self, 
        api_url: str, 
        user_key: str, 
        api_token: str, 
        content: str, 
        title: str,
        max_length: int
    ) -> bool:
        """
        分段傳送長 Pushover 訊息
        
        按段落分割，確保每段不超過最大長度
        """
        import time
        
        # 按段落（分隔線或雙換行）分割
        if "────────" in content:
            sections = content.split("────────")
            separator = "────────"
        else:
            sections = content.split("\n\n")
            separator = "\n\n"
        
        chunks = []
        current_chunk = []
        current_length = 0
        
        for section in sections:
            # 計算新增這個 section 後的實際長度
            # join() 只在元素之間放置分隔符，不是每個元素後面
            # 所以：第一個元素不需要分隔符，後續元素需要一個分隔符連線
            if current_chunk:
                # 已有元素，新增新元素需要：當前長度 + 分隔符 + 新 section
                new_length = current_length + len(separator) + len(section)
            else:
                # 第一個元素，不需要分隔符
                new_length = len(section)
            
            if new_length > max_length:
                if current_chunk:
                    chunks.append(separator.join(current_chunk))
                current_chunk = [section]
                current_length = len(section)
            else:
                current_chunk.append(section)
                current_length = new_length
        
        if current_chunk:
            chunks.append(separator.join(current_chunk))
        
        total_chunks = len(chunks)
        success_count = 0
        
        logger.info(f"Pushover 分批傳送：共 {total_chunks} 批")
        
        for i, chunk in enumerate(chunks):
            # 新增分頁標記到標題
            chunk_title = f"{title} ({i+1}/{total_chunks})" if total_chunks > 1 else title
            
            if self._send_pushover_message(api_url, user_key, api_token, chunk, chunk_title):
                success_count += 1
                logger.info(f"Pushover 第 {i+1}/{total_chunks} 批傳送成功")
            else:
                logger.error(f"Pushover 第 {i+1}/{total_chunks} 批傳送失敗")
            
            # 批次間隔，避免觸發頻率限制
            if i < total_chunks - 1:
                time.sleep(1)
        
        return success_count == total_chunks
    