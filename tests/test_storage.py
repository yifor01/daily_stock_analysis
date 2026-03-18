# -*- coding: utf-8 -*-
import unittest
import sys
import os

# Ensure src module can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.storage import DatabaseManager

class TestStorage(unittest.TestCase):
    
    def test_parse_sniper_value(self):
        """測試解析狙擊點位數值"""
        
        # 1. 正常數值
        self.assertEqual(DatabaseManager._parse_sniper_value(100), 100.0)
        self.assertEqual(DatabaseManager._parse_sniper_value(100.5), 100.5)
        self.assertEqual(DatabaseManager._parse_sniper_value("100"), 100.0)
        self.assertEqual(DatabaseManager._parse_sniper_value("100.5"), 100.5)
        
        # 2. 包含中文描述和"元"
        self.assertEqual(DatabaseManager._parse_sniper_value("建議在 100 元附近買入"), 100.0)
        self.assertEqual(DatabaseManager._parse_sniper_value("價格：100.5元"), 100.5)
        
        # 3. 包含干擾數字（修復的Bug場景）
        # 之前 "MA5" 會被錯誤提取為 5.0，現在應該提取 "元" 前面的 100
        text_bug = "無法給出。需等待MA5資料恢復，在股價回踩MA5且乖離率<2%時考慮100元"
        self.assertEqual(DatabaseManager._parse_sniper_value(text_bug), 100.0)
        
        # 4. 更多幹擾場景
        text_complex = "MA10為20.5，建議在30元買入"
        self.assertEqual(DatabaseManager._parse_sniper_value(text_complex), 30.0)
        
        text_multiple = "支撐位10元，阻力位20元" # 應該提取最後一個"元"前面的數字，即20，或者更復雜的邏輯？
        # 當前邏輯是找最後一個冒號，然後找之後的第一個"元"，提取中間的數字。
        # 測試沒有冒號的情況
        self.assertEqual(DatabaseManager._parse_sniper_value("30元"), 30.0)
        
        # 測試多個數字在"元"之前
        self.assertEqual(DatabaseManager._parse_sniper_value("MA5 10 20元"), 20.0)
        
        # 5. Fallback: no "元" character — extracts last non-MA number
        self.assertEqual(DatabaseManager._parse_sniper_value("102.10-103.00（MA5附近）"), 103.0)
        self.assertEqual(DatabaseManager._parse_sniper_value("97.62-98.50（MA10附近）"), 98.5)
        self.assertEqual(DatabaseManager._parse_sniper_value("93.40下方（MA20支撐）"), 93.4)
        self.assertEqual(DatabaseManager._parse_sniper_value("108.00-110.00（前期高點阻力）"), 110.0)

        # 6. 無效輸入
        self.assertIsNone(DatabaseManager._parse_sniper_value(None))
        self.assertIsNone(DatabaseManager._parse_sniper_value(""))
        self.assertIsNone(DatabaseManager._parse_sniper_value("沒有數字"))
        self.assertIsNone(DatabaseManager._parse_sniper_value("MA5但沒有元"))

        # 7. 迴歸：括號內技術指標數字不應被提取
        self.assertNotEqual(DatabaseManager._parse_sniper_value("1.52-1.53 (回踩MA5/10附近)"), 10.0)
        self.assertNotEqual(DatabaseManager._parse_sniper_value("1.55-1.56(MA5/M20支撐)"), 20.0)
        self.assertNotEqual(DatabaseManager._parse_sniper_value("1.49-1.50(MA60附近企穩)"), 60.0)
        # 驗證正確值在區間內
        self.assertIn(DatabaseManager._parse_sniper_value("1.52-1.53 (回踩MA5/10附近)"), [1.52, 1.53])
        self.assertIn(DatabaseManager._parse_sniper_value("1.55-1.56(MA5/M20支撐)"), [1.55, 1.56])
        self.assertIn(DatabaseManager._parse_sniper_value("1.49-1.50(MA60附近企穩)"), [1.49, 1.50])

    def test_get_chat_sessions_prefix_is_scoped_by_colon_boundary(self):
        DatabaseManager.reset_instance()
        db = DatabaseManager(db_url="sqlite:///:memory:")

        db.save_conversation_message("telegram_12345:chat", "user", "first user")
        db.save_conversation_message("telegram_123456:chat", "user", "second user")

        sessions = db.get_chat_sessions(session_prefix="telegram_12345")

        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["session_id"], "telegram_12345:chat")

        DatabaseManager.reset_instance()

    def test_get_chat_sessions_can_include_legacy_exact_session_id(self):
        DatabaseManager.reset_instance()
        db = DatabaseManager(db_url="sqlite:///:memory:")

        db.save_conversation_message("feishu_u1", "user", "legacy chat")
        db.save_conversation_message("feishu_u1:ask_600519", "user", "ask session")

        sessions = db.get_chat_sessions(
            session_prefix="feishu_u1:",
            extra_session_ids=["feishu_u1"],
        )

        self.assertEqual({item["session_id"] for item in sessions}, {"feishu_u1", "feishu_u1:ask_600519"})

        DatabaseManager.reset_instance()

if __name__ == '__main__':
    unittest.main()
