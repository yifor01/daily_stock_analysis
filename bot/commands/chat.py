# -*- coding: utf-8 -*-
"""
Chat command for free-form conversation with the Agent.
"""

import logging

from bot.commands.base import BotCommand
from bot.models import BotMessage, BotResponse
from src.config import get_config

logger = logging.getLogger(__name__)

class ChatCommand(BotCommand):
    """
    Chat command handler.
    
    Usage: /chat <message>
    Example: /chat 幫我分析一下茅臺最近的走勢
    """
    
    @property
    def name(self) -> str:
        return "chat"
        
    @property
    def description(self) -> str:
        return "與 AI 助手進行自由對話 (需開啟 Agent 模式)"
        
    @property
    def usage(self) -> str:
        return "/chat <問題>"
        
    @property
    def aliases(self) -> list[str]:
        return ["c", "問"]
        
    def execute(self, message: BotMessage, args: list[str]) -> BotResponse:
        """Execute the chat command."""
        config = get_config()
        
        if not config.agent_mode:
            return BotResponse.text_response(
                "⚠️ Agent 模式未開啟，無法使用對話功能。\n請在配置中設定 `AGENT_MODE=true`。"
            )
            
        if not args:
            return BotResponse.text_response(
                "⚠️ 請提供要詢問的問題。\n用法: `/chat <問題>`\n示例: `/chat 幫我分析一下茅臺最近的走勢`"
            )
            
        user_message = " ".join(args)
        session_id = f"{message.platform}_{message.user_id}"
        
        try:
            from src.agent.factory import build_agent_executor
            executor = build_agent_executor(config)
            result = executor.chat(message=user_message, session_id=session_id)
            
            if result.success:
                return BotResponse.text_response(result.content)
            else:
                return BotResponse.text_response(f"⚠️ 對話失敗: {result.error}")
                
        except Exception as e:
            logger.error(f"Chat command failed: {e}")
            logger.exception("Chat error details:")
            return BotResponse.text_response(f"⚠️ 對話執行出錯: {str(e)}")
