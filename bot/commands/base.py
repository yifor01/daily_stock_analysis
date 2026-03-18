# -*- coding: utf-8 -*-
"""
===================================
命令基類
===================================

定義命令處理器的抽象基類，所有命令都必須繼承此類。
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from bot.models import BotMessage, BotResponse


class BotCommand(ABC):
    """
    命令處理器抽象基類
    
    所有命令都必須繼承此類並實現抽象方法。
    
    使用示例：
        class MyCommand(BotCommand):
            @property
            def name(self) -> str:
                return "mycommand"
            
            @property
            def aliases(self) -> List[str]:
                return ["mc", "我的命令"]
            
            @property
            def description(self) -> str:
                return "這是我的命令"
            
            @property
            def usage(self) -> str:
                return "/mycommand [引數]"
            
            def execute(self, message: BotMessage, args: List[str]) -> BotResponse:
                return BotResponse.text_response("命令執行成功")
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """
        命令名稱（不含字首）
        
        例如 "analyze"，使用者輸入 "/analyze" 觸發
        """
        pass
    
    @property
    @abstractmethod
    def aliases(self) -> List[str]:
        """
        命令別名列表
        
        例如 ["a", "分析"]，使用者輸入 "/a" 或 "分析" 也能觸發
        """
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """命令描述（用於幫助資訊）"""
        pass
    
    @property
    @abstractmethod
    def usage(self) -> str:
        """
        使用說明（用於幫助資訊）
        
        例如 "/analyze <股票程式碼>"
        """
        pass
    
    @property
    def hidden(self) -> bool:
        """
        是否在幫助列表中隱藏
        
        預設 False，設為 True 則不顯示在 /help 列表中
        """
        return False
    
    @property
    def admin_only(self) -> bool:
        """
        是否僅管理員可用
        
        預設 False，設為 True 則需要管理員許可權
        """
        return False
    
    @abstractmethod
    def execute(self, message: BotMessage, args: List[str]) -> BotResponse:
        """
        執行命令
        
        Args:
            message: 原始訊息物件
            args: 命令引數列表（已分割）
            
        Returns:
            BotResponse 響應物件
        """
        pass
    
    def validate_args(self, args: List[str]) -> Optional[str]:
        """
        驗證引數
        
        子類可重寫此方法進行引數校驗。
        
        Args:
            args: 命令引數列表
            
        Returns:
            如果引數有效返回 None，否則返回錯誤資訊
        """
        return None
    
    def get_help_text(self) -> str:
        """獲取幫助文字"""
        return f"**{self.name}** - {self.description}\n用法: `{self.usage}`"
