# -*- coding: utf-8 -*-
"""
===================================
Discord 平臺介面卡
===================================

負責：
1. 驗證 Discord Webhook 請求
2. 解析 Discord 訊息為統一格式
3. 將響應轉換為 Discord 格式
"""

import logging
from typing import Dict, Any, Optional

from bot.platforms.base import BotPlatform
from bot.models import BotMessage, WebhookResponse


logger = logging.getLogger(__name__)


class DiscordPlatform(BotPlatform):
    """Discord 平臺介面卡"""
    
    @property
    def platform_name(self) -> str:
        """平臺標識名稱"""
        return "discord"
    
    def verify_request(self, headers: Dict[str, str], body: bytes) -> bool:
        """驗證 Discord Webhook 請求籤名
        
        Discord Webhook 簽名驗證：
        1. 從請求頭獲取 X-Signature-Ed25519 和 X-Signature-Timestamp
        2. 使用公鑰驗證簽名
        
        Args:
            headers: HTTP 請求頭
            body: 請求體原始位元組
            
        Returns:
            簽名是否有效
        """
        # TODO: 實現 Discord Webhook 簽名驗證
        # 當前暫時返回 True，後續需要完善
        return True
    
    def parse_message(self, data: Dict[str, Any]) -> Optional[BotMessage]:
        """解析 Discord 訊息為統一格式
        
        Args:
            data: 解析後的 JSON 資料
            
        Returns:
            BotMessage 物件，或 None（不需要處理）
        """
        # 檢查是否是訊息事件
        if data.get("type") != 1 and data.get("type") != 2:
            return None
        
        # 提取訊息內容
        content = data.get("content", "").strip()
        if not content:
            return None
        
        # 提取使用者資訊
        author = data.get("author", {})
        user_id = author.get("id", "")
        user_name = author.get("username", "unknown")
        
        # 提取頻道資訊
        channel_id = data.get("channel_id", "")
        guild_id = data.get("guild_id", "")
        
        # 提取訊息 ID
        message_id = data.get("id", "")
        
        # 提取附件資訊（如果有）
        attachments = data.get("attachments", [])
        attachment_urls = [att["url"] for att in attachments if "url" in att]
        
        # 構建 BotMessage 物件
        message = BotMessage(
            platform="discord",
            message_id=message_id,
            user_id=user_id,
            user_name=user_name,
            content=content,
            attachment_urls=attachment_urls,
            channel_id=channel_id,
            group_id=guild_id,
            # 從 data 中提取其他相關資訊
            timestamp=data.get("timestamp"),
            mention_everyone=data.get("mention_everyone", False),
            mentions=data.get("mentions", []),
            
            # 新增 Discord 特定的原始資料
            raw_data={
                "message_id": message_id,
                "channel_id": channel_id,
                "guild_id": guild_id,
                "author": author,
                "content": content,
                "timestamp": data.get("timestamp"),
                "attachments": attachments,
                "mentions": data.get("mentions", []),
                "mention_roles": data.get("mention_roles", []),
                "mention_everyone": data.get("mention_everyone", False),
                "type": data.get("type"),
            }
        )
        
        return message
    
    def format_response(self, response: Any, message: BotMessage) -> WebhookResponse:
        """將統一響應轉換為 Discord 格式
        
        Args:
            response: 統一響應物件
            message: 原始訊息物件
            
        Returns:
            WebhookResponse 物件
        """
        # 構建 Discord 響應格式
        discord_response = {
            "content": response.text if hasattr(response, "text") else str(response),
            "tts": False,
            "embeds": [],
            "allowed_mentions": {
                "parse": ["users", "roles", "everyone"]
            }
        }
        
        return WebhookResponse.success(discord_response)
    
    def handle_challenge(self, data: Dict[str, Any]) -> Optional[WebhookResponse]:
        """處理 Discord 驗證請求
        
        Discord 在配置 Webhook 時會傳送驗證請求
        
        Args:
            data: 請求資料
            
        Returns:
            驗證響應，或 None（不是驗證請求）
        """
        # Discord Webhook 驗證請求型別是 1
        if data.get("type") == 1:
            return WebhookResponse.success({
                "type": 1
            })
        
        # Discord 命令互動驗證
        if "challenge" in data:
            return WebhookResponse.success({
                "challenge": data["challenge"]
            })
        
        return None
