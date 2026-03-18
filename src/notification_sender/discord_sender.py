# -*- coding: utf-8 -*-
"""
Discord 傳送提醒服務

職責：
1. 透過 webhook 或 Discord bot API 傳送 Discord 訊息
"""
import logging
import requests

from src.config import Config
from src.formatters import chunk_content_by_max_words


logger = logging.getLogger(__name__)


class DiscordSender:
    
    def __init__(self, config: Config):
        """
        初始化 Discord 配置

        Args:
            config: 配置物件
        """
        self._discord_config = {
            'bot_token': getattr(config, 'discord_bot_token', None),
            'channel_id': getattr(config, 'discord_main_channel_id', None),
            'webhook_url': getattr(config, 'discord_webhook_url', None),
        }
        self._discord_max_words = getattr(config, 'discord_max_words', 2000)
        self._webhook_verify_ssl = getattr(config, 'webhook_verify_ssl', True)
    
    def _is_discord_configured(self) -> bool:
        """檢查 Discord 配置是否完整（支援 Bot 或 Webhook）"""
        # 只要配置了 Webhook 或完整的 Bot Token+Channel，即視為可用
        bot_ok = bool(self._discord_config['bot_token'] and self._discord_config['channel_id'])
        webhook_ok = bool(self._discord_config['webhook_url'])
        return bot_ok or webhook_ok
    
    def send_to_discord(self, content: str) -> bool:
        """
        推送訊息到 Discord（支援 Webhook 和 Bot API）
        
        Args:
            content: Markdown 格式的訊息內容
            
        Returns:
            是否傳送成功
        """
        # 分割內容，避免單條訊息超過 Discord 限制
        try:
            chunks = chunk_content_by_max_words(content, self._discord_max_words)
        except ValueError as e:
            logger.error(f"分割 Discord 訊息失敗: {e}, 嘗試整段傳送。")
            chunks = [content]

        # 優先使用 Webhook（配置簡單，許可權低）
        if self._discord_config['webhook_url']:
            return all(self._send_discord_webhook(chunk) for chunk in chunks)

        # 其次使用 Bot API（許可權高，需要 channel_id）
        if self._discord_config['bot_token'] and self._discord_config['channel_id']:
            return all(self._send_discord_bot(chunk) for chunk in chunks)

        logger.warning("Discord 配置不完整，跳過推送")
        return False

  
    def _send_discord_webhook(self, content: str) -> bool:
        """
        使用 Webhook 傳送訊息到 Discord
        
        Discord Webhook 支援 Markdown 格式
        
        Args:
            content: Markdown 格式的訊息內容
            
        Returns:
            是否傳送成功
        """
        try:
            payload = {
                'content': content,
                'username': 'A股分析機器人',
                'avatar_url': 'https://picsum.photos/200'
            }
            
            response = requests.post(
                self._discord_config['webhook_url'],
                json=payload,
                timeout=10,
                verify=self._webhook_verify_ssl
            )
            
            if response.status_code in [200, 204]:
                logger.info("Discord Webhook 訊息傳送成功")
                return True
            else:
                logger.error(f"Discord Webhook 傳送失敗: {response.status_code} {response.text}")
                return False
        except Exception as e:
            logger.error(f"Discord Webhook 傳送異常: {e}")
            return False
    
    def _send_discord_bot(self, content: str) -> bool:
        """
        使用 Bot API 傳送訊息到 Discord
        
        Args:
            content: Markdown 格式的訊息內容
            
        Returns:
            是否傳送成功
        """
        try:
            headers = {
                'Authorization': f'Bot {self._discord_config["bot_token"]}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'content': content
            }
            
            url = f'https://discord.com/api/v10/channels/{self._discord_config["channel_id"]}/messages'
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            
            if response.status_code == 200:
                logger.info("Discord Bot 訊息傳送成功")
                return True
            else:
                logger.error(f"Discord Bot 傳送失敗: {response.status_code} {response.text}")
                return False
        except Exception as e:
            logger.error(f"Discord Bot 傳送異常: {e}")
            return False
