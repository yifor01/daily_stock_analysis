# -*- coding: utf-8 -*-
"""
===================================
通知傳送層模組
===================================

提供各種通知傳送服務
"""

from .astrbot_sender import AstrbotSender
from .custom_webhook_sender import CustomWebhookSender
from .discord_sender import DiscordSender
from .email_sender import EmailSender
from .feishu_sender import FeishuSender
from .pushover_sender import PushoverSender
from .pushplus_sender import PushplusSender
from .serverchan3_sender import Serverchan3Sender
from .telegram_sender import TelegramSender
from .wechat_sender import WechatSender, WECHAT_IMAGE_MAX_BYTES
