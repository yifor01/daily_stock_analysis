# -*- coding: utf-8 -*-
"""
===================================
列舉型別定義
===================================

集中管理系統中使用的列舉型別，提供型別安全和程式碼可讀性。
"""

from enum import Enum


class ReportType(str, Enum):
    """
    報告型別列舉

    用於 API 觸發分析時選擇推送的報告格式。
    繼承 str 使其可以直接與字串比較和序列化。
    """
    SIMPLE = "simple"  # 精簡報告：使用 generate_single_stock_report
    FULL = "full"      # 完整報告：使用 generate_dashboard_report
    BRIEF = "brief"    # 簡潔模式：3-5 句話概括，適合移動端/推送

    @classmethod
    def from_str(cls, value: str) -> "ReportType":
        """
        從字串安全地轉換為列舉值
        
        Args:
            value: 字串值
            
        Returns:
            對應的列舉值，無效輸入返回預設值 SIMPLE
        """
        try:
            normalized = value.lower().strip()
            if normalized == "detailed":
                normalized = cls.FULL.value
            return cls(normalized)
        except (ValueError, AttributeError):
            return cls.SIMPLE
    
    @property
    def display_name(self) -> str:
        """獲取用於顯示的名稱"""
        return {
            ReportType.SIMPLE: "精簡報告",
            ReportType.FULL: "完整報告",
            ReportType.BRIEF: "簡潔報告",
        }.get(self, "精簡報告")
