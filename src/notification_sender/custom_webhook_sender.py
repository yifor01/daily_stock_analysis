# -*- coding: utf-8 -*-
"""
自定義 Webhook 傳送提醒服務

職責：
1. 傳送自定義 Webhook 訊息
"""
import logging
import json
import requests

from src.config import Config
from src.formatters import chunk_content_by_max_bytes, slice_at_max_bytes


logger = logging.getLogger(__name__)


class CustomWebhookSender:

    def __init__(self, config: Config):
        """
        初始化自定義 Webhook 配置

        Args:
            config: 配置物件
        """
        self._custom_webhook_urls = getattr(config, 'custom_webhook_urls', []) or []
        self._custom_webhook_bearer_token = getattr(config, 'custom_webhook_bearer_token', None)
        self._webhook_verify_ssl = getattr(config, 'webhook_verify_ssl', True)
 
    def send_to_custom(self, content: str) -> bool:
        """
        推送訊息到自定義 Webhook
        
        支援任意接受 POST JSON 的 Webhook 端點
        預設傳送格式：{"text": "訊息內容", "content": "訊息內容"}
        
        適用於：
        - 釘釘機器人
        - Discord Webhook
        - Slack Incoming Webhook
        - 自建通知服務
        - 其他支援 POST JSON 的服務
        
        Args:
            content: 訊息內容（Markdown 格式）
            
        Returns:
            是否至少有一個 Webhook 傳送成功
        """
        if not self._custom_webhook_urls:
            logger.warning("未配置自定義 Webhook，跳過推送")
            return False
        
        success_count = 0
        
        for i, url in enumerate(self._custom_webhook_urls):
            try:
                # 通用 JSON 格式，相容大多數 Webhook
                # 釘釘格式: {"msgtype": "text", "text": {"content": "xxx"}}
                # Slack 格式: {"text": "xxx"}
                # Discord 格式: {"content": "xxx"}
                
                # 釘釘機器人對 body 有位元組上限（約 20000 bytes），超長需要分批傳送
                if self._is_dingtalk_webhook(url):
                    if self._send_dingtalk_chunked(url, content, max_bytes=20000):
                        logger.info(f"自定義 Webhook {i+1}（釘釘）推送成功")
                        success_count += 1
                    else:
                        logger.error(f"自定義 Webhook {i+1}（釘釘）推送失敗")
                    continue

                # 其他 Webhook：單次傳送
                payload = self._build_custom_webhook_payload(url, content)
                if self._post_custom_webhook(url, payload, timeout=30):
                    logger.info(f"自定義 Webhook {i+1} 推送成功")
                    success_count += 1
                else:
                    logger.error(f"自定義 Webhook {i+1} 推送失敗")
                    
            except Exception as e:
                logger.error(f"自定義 Webhook {i+1} 推送異常: {e}")
        
        logger.info(f"自定義 Webhook 推送完成：成功 {success_count}/{len(self._custom_webhook_urls)}")
        return success_count > 0

    
    def _send_custom_webhook_image(
        self, image_bytes: bytes, fallback_content: str = ""
    ) -> bool:
        """Send image to Custom Webhooks; Discord supports file attachment (Issue #289)."""
        if not self._custom_webhook_urls:
            return False
        success_count = 0
        for i, url in enumerate(self._custom_webhook_urls):
            try:
                if self._is_discord_webhook(url):
                    files = {"file": ("report.png", image_bytes, "image/png")}
                    data = {"content": "📈 股票智慧分析報告"}
                    headers = {"User-Agent": "StockAnalysis/1.0"}
                    if self._custom_webhook_bearer_token:
                        headers["Authorization"] = (
                            f"Bearer {self._custom_webhook_bearer_token}"
                        )
                    response = requests.post(
                        url, data=data, files=files, headers=headers, timeout=30,
                        verify=self._webhook_verify_ssl
                    )
                    if response.status_code in (200, 204):
                        logger.info("自定義 Webhook %d（Discord 圖片）推送成功", i + 1)
                        success_count += 1
                    else:
                        logger.error(
                            "自定義 Webhook %d（Discord 圖片）推送失敗: HTTP %s",
                            i + 1, response.status_code,
                        )
                else:
                    if fallback_content:
                        payload = self._build_custom_webhook_payload(url, fallback_content)
                        if self._post_custom_webhook(url, payload, timeout=30):
                            logger.info(
                                "自定義 Webhook %d（圖片不支援，回退文字）推送成功", i + 1
                            )
                            success_count += 1
                    else:
                        logger.warning(
                            "自定義 Webhook %d 不支援圖片，且無回退內容，跳過", i + 1
                        )
            except Exception as e:
                logger.error("自定義 Webhook %d 圖片推送異常: %s", i + 1, e)
        return success_count > 0

    def _post_custom_webhook(self, url: str, payload: dict, timeout: int = 30) -> bool:
        headers = {
            'Content-Type': 'application/json; charset=utf-8',
            'User-Agent': 'StockAnalysis/1.0',
        }
        # 支援 Bearer Token 認證（#51）
        if self._custom_webhook_bearer_token:
            headers['Authorization'] = f'Bearer {self._custom_webhook_bearer_token}'
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        response = requests.post(url, data=body, headers=headers, timeout=timeout, verify=self._webhook_verify_ssl)
        if response.status_code == 200:
            return True
        logger.error(f"自定義 Webhook 推送失敗: HTTP {response.status_code}")
        logger.debug(f"響應內容: {response.text[:200]}")
        return False
    
    def _build_custom_webhook_payload(self, url: str, content: str) -> dict:
        """
        根據 URL 構建對應的 Webhook payload
        
        自動識別常見服務並使用對應格式
        """
        url_lower = url.lower()
        
        # 釘釘機器人
        if 'dingtalk' in url_lower or 'oapi.dingtalk.com' in url_lower:
            return {
                "msgtype": "markdown",
                "markdown": {
                    "title": "股票分析報告",
                    "text": content
                }
            }
        
        # Discord Webhook
        if 'discord.com/api/webhooks' in url_lower or 'discordapp.com/api/webhooks' in url_lower:
            # Discord 限制 2000 字元
            truncated = content[:1900] + "..." if len(content) > 1900 else content
            return {
                "content": truncated
            }
        
        # Slack Incoming Webhook
        if 'hooks.slack.com' in url_lower:
            return {
                "text": content,
                "mrkdwn": True
            }
        
        # Bark (iOS 推送)
        if 'api.day.app' in url_lower:
            return {
                "title": "股票分析報告",
                "body": content[:4000],  # Bark 限制
                "group": "stock"
            }
        
        # 通用格式（相容大多數服務）
        return {
            "text": content,
            "content": content,
            "message": content,
            "body": content
        }
    
    def _send_dingtalk_chunked(self, url: str, content: str, max_bytes: int = 20000) -> bool:
        import time as _time

        # 為 payload 開銷預留空間，避免 body 超限
        budget = max(1000, max_bytes - 1500)
        chunks = chunk_content_by_max_bytes(content, budget)
        if not chunks:
            return False

        total = len(chunks)
        ok = 0

        for idx, chunk in enumerate(chunks):
            marker = f"\n\n📄 *({idx+1}/{total})*" if total > 1 else ""
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "title": "股票分析報告",
                    "text": chunk + marker,
                },
            }

            # 如果仍超限（極端情況下），再按位元組硬截斷一次
            body_bytes = len(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
            if body_bytes > max_bytes:
                hard_budget = max(200, budget - (body_bytes - max_bytes) - 200)
                payload["markdown"]["text"], _ = slice_at_max_bytes(payload["markdown"]["text"], hard_budget)

            if self._post_custom_webhook(url, payload, timeout=30):
                ok += 1
            else:
                logger.error(f"釘釘分批傳送失敗: 第 {idx+1}/{total} 批")

            if idx < total - 1:
                _time.sleep(1)

        return ok == total

    
    @staticmethod
    def _is_dingtalk_webhook(url: str) -> bool:
        url_lower = (url or "").lower()
        return 'dingtalk' in url_lower or 'oapi.dingtalk.com' in url_lower

    @staticmethod
    def _is_discord_webhook(url: str) -> bool:
        url_lower = (url or "").lower()
        return (
            'discord.com/api/webhooks' in url_lower
            or 'discordapp.com/api/webhooks' in url_lower
        )
