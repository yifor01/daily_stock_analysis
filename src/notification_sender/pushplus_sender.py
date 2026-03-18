# -*- coding: utf-8 -*-
"""
PushPlus 傳送提醒服務

職責：
1. 透過 PushPlus API 傳送 PushPlus 訊息
"""
import logging
import time
from typing import Optional
from datetime import datetime
import requests

from src.config import Config
from src.formatters import chunk_content_by_max_bytes


logger = logging.getLogger(__name__)


class PushplusSender:
    
    def __init__(self, config: Config):
        """
        初始化 PushPlus 配置

        Args:
            config: 配置物件
        """
        self._pushplus_token = getattr(config, 'pushplus_token', None)
        self._pushplus_topic = getattr(config, 'pushplus_topic', None)
        self._pushplus_max_bytes = getattr(config, 'pushplus_max_bytes', 20000)
        
    def send_to_pushplus(self, content: str, title: Optional[str] = None) -> bool:
        """
        推送訊息到 PushPlus

        PushPlus API 格式：
        POST http://www.pushplus.plus/send
        {
            "token": "使用者令牌",
            "title": "訊息標題",
            "content": "訊息內容",
            "template": "html/txt/json/markdown"
        }

        PushPlus 特點：
        - 國內推送服務，免費額度充足
        - 支援微信公眾號推送
        - 支援多種訊息格式

        Args:
            content: 訊息內容（Markdown 格式）
            title: 訊息標題（可選）

        Returns:
            是否傳送成功
        """
        if not self._pushplus_token:
            logger.warning("PushPlus Token 未配置，跳過推送")
            return False

        api_url = "http://www.pushplus.plus/send"

        if title is None:
            date_str = datetime.now().strftime('%Y-%m-%d')
            title = f"📈 股票分析報告 - {date_str}"

        try:
            content_bytes = len(content.encode('utf-8'))
            if content_bytes > self._pushplus_max_bytes:
                logger.info(
                    "PushPlus 訊息內容超長(%s位元組/%s字元)，將分批傳送",
                    content_bytes,
                    len(content),
                )
                return self._send_pushplus_chunked(
                    api_url,
                    content,
                    title,
                    self._pushplus_max_bytes,
                )

            return self._send_pushplus_message(api_url, content, title)
        except Exception as e:
            logger.error(f"傳送 PushPlus 訊息失敗: {e}")
            return False

    def _send_pushplus_message(self, api_url: str, content: str, title: str) -> bool:
        payload = {
            "token": self._pushplus_token,
            "title": title,
            "content": content,
            "template": "markdown",
        }

        if self._pushplus_topic:
            payload["topic"] = self._pushplus_topic

        response = requests.post(api_url, json=payload, timeout=10)

        if response.status_code == 200:
            result = response.json()
            if result.get('code') == 200:
                logger.info("PushPlus 訊息傳送成功")
                return True

            error_msg = result.get('msg', '未知錯誤')
            logger.error(f"PushPlus 返回錯誤: {error_msg}")
            return False

        logger.error(f"PushPlus 請求失敗: HTTP {response.status_code}")
        return False

    def _send_pushplus_chunked(self, api_url: str, content: str, title: str, max_bytes: int) -> bool:
        """分批傳送長 PushPlus 訊息，給 JSON payload 預留空間。"""
        budget = max(1000, max_bytes - 1500)
        chunks = chunk_content_by_max_bytes(content, budget, add_page_marker=True)
        total_chunks = len(chunks)
        success_count = 0

        logger.info(f"PushPlus 分批傳送：共 {total_chunks} 批")

        for i, chunk in enumerate(chunks):
            chunk_title = f"{title} ({i+1}/{total_chunks})" if total_chunks > 1 else title
            if self._send_pushplus_message(api_url, chunk, chunk_title):
                success_count += 1
                logger.info(f"PushPlus 第 {i+1}/{total_chunks} 批傳送成功")
            else:
                logger.error(f"PushPlus 第 {i+1}/{total_chunks} 批傳送失敗")

            if i < total_chunks - 1:
                time.sleep(1)

        return success_count == total_chunks
