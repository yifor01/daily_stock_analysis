# -*- coding: utf-8 -*-
"""
===================================
機器人訊息模型
===================================

定義統一的訊息和響應模型，遮蔽各平臺差異。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List


class ChatType(str, Enum):
    """會話型別"""
    GROUP = "group"      # 群聊
    PRIVATE = "private"  # 私聊
    UNKNOWN = "unknown"  # 未知


class Platform(str, Enum):
    """平臺型別"""
    FEISHU = "feishu"        # 飛書
    DINGTALK = "dingtalk"    # 釘釘
    WECOM = "wecom"          # 企業微信
    TELEGRAM = "telegram"    # Telegram
    UNKNOWN = "unknown"      # 未知


@dataclass
class BotMessage:
    """
    統一的機器人訊息模型
    
    將各平臺的訊息格式統一為此模型，便於命令處理器處理。
    
    Attributes:
        platform: 平臺標識
        message_id: 訊息 ID（平臺原始 ID）
        user_id: 傳送者 ID
        user_name: 傳送者名稱
        chat_id: 會話 ID（群聊 ID 或私聊 ID）
        chat_type: 會話型別
        content: 訊息文字內容（已去除 @機器人 部分）
        raw_content: 原始訊息內容
        mentioned: 是否 @了機器人
        mentions: @的使用者列表
        timestamp: 訊息時間戳
        raw_data: 原始請求資料（平臺特定，用於除錯）
    """
    platform: str
    message_id: str
    user_id: str
    user_name: str
    chat_id: str
    chat_type: ChatType
    content: str
    raw_content: str = ""
    mentioned: bool = False
    mentions: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    raw_data: Dict[str, Any] = field(default_factory=dict)
    
    def get_command_and_args(self, prefix: str = "/") -> tuple:
        """
        解析命令和引數
        
        Args:
            prefix: 命令字首，預設 "/"
            
        Returns:
            (command, args) 元組，如 ("analyze", ["600519"])
            如果不是命令，返回 (None, [])
        """
        text = self.content.strip()
        
        # 檢查是否以命令字首開頭
        if not text.startswith(prefix):
            # 嘗試匹配中文命令（無字首）
            chinese_commands = {
                '分析': 'analyze',
                '大盤': 'market',
                '批次': 'batch',
                '幫助': 'help',
                '狀態': 'status',
            }
            for cn_cmd, en_cmd in chinese_commands.items():
                if text.startswith(cn_cmd):
                    args = text[len(cn_cmd):].strip().split()
                    return en_cmd, args
            return None, []
        
        # 去除字首
        text = text[len(prefix):]
        
        # 分割命令和引數
        parts = text.split()
        if not parts:
            return None, []
        
        command = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        return command, args
    
    def is_command(self, prefix: str = "/") -> bool:
        """檢查訊息是否是命令"""
        cmd, _ = self.get_command_and_args(prefix)
        return cmd is not None


@dataclass
class BotResponse:
    """
    統一的機器人響應模型
    
    命令處理器返回此模型，由平臺介面卡轉換為平臺特定格式。
    
    Attributes:
        text: 回覆文字
        markdown: 是否為 Markdown 格式
        at_user: 是否 @傳送者
        reply_to_message: 是否回覆原訊息
        extra: 額外資料（平臺特定）
    """
    text: str
    markdown: bool = False
    at_user: bool = True
    reply_to_message: bool = True
    extra: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def text_response(cls, text: str, at_user: bool = True) -> 'BotResponse':
        """建立純文字響應"""
        return cls(text=text, markdown=False, at_user=at_user)
    
    @classmethod
    def markdown_response(cls, text: str, at_user: bool = True) -> 'BotResponse':
        """建立 Markdown 響應"""
        return cls(text=text, markdown=True, at_user=at_user)
    
    @classmethod
    def error_response(cls, message: str) -> 'BotResponse':
        """建立錯誤響應"""
        return cls(text=f"❌ 錯誤：{message}", markdown=False, at_user=True)


@dataclass
class WebhookResponse:
    """
    Webhook 響應模型
    
    平臺介面卡返回此模型，包含 HTTP 響應內容。
    
    Attributes:
        status_code: HTTP 狀態碼
        body: 響應體（字典，將被 JSON 序列化）
        headers: 額外的響應頭
    """
    status_code: int = 200
    body: Dict[str, Any] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    
    @classmethod
    def success(cls, body: Optional[Dict] = None) -> 'WebhookResponse':
        """建立成功響應"""
        return cls(status_code=200, body=body or {})
    
    @classmethod
    def challenge(cls, challenge: str) -> 'WebhookResponse':
        """建立驗證響應（用於平臺 URL 驗證）"""
        return cls(status_code=200, body={"challenge": challenge})
    
    @classmethod
    def error(cls, message: str, status_code: int = 400) -> 'WebhookResponse':
        """建立錯誤響應"""
        return cls(status_code=status_code, body={"error": message})
