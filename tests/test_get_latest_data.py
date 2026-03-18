# -*- coding: utf-8 -*-
"""
===================================
get_latest_data 測試
===================================

職責：
1. 驗證 get_latest_data 方法
2. 測試返回資料按日期降序排列
3. 測試 days 引數限制
"""

import os
import tempfile
import unittest
from datetime import date, timedelta

import pandas as pd

from src.config import Config
from src.storage import DatabaseManager, StockDaily


class GetLatestDataTestCase(unittest.TestCase):
    """get_latest_data 方法測試"""

    def setUp(self) -> None:
        """Initialize an isolated database for each test case."""
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test_get_latest_data.db")
        os.environ["DATABASE_PATH"] = self._db_path

        Config._instance = None
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()

    def tearDown(self) -> None:
        """Clean up resources."""
        DatabaseManager.reset_instance()
        self._temp_dir.cleanup()

    def _insert_stock_data(self, code: str, days_ago: int, close: float) -> None:
        """插入測試用股票資料"""
        target_date = date.today() - timedelta(days=days_ago)
        df = pd.DataFrame([{
            'date': target_date,
            'open': close - 1,
            'high': close + 1,
            'low': close - 2,
            'close': close,
            'volume': 1000000,
            'amount': 10000000,
            'pct_chg': 1.5,
        }])
        self.db.save_daily_data(df, code, data_source="TestData")

    def test_get_latest_data_returns_empty_when_no_data(self) -> None:
        """無資料時返回空列表"""
        result = self.db.get_latest_data("999999", days=2)
        self.assertEqual(result, [])

    def test_get_latest_data_returns_correct_count(self) -> None:
        """返回正確數量的資料"""
        # 插入5天資料
        for i in range(5):
            self._insert_stock_data("600519", days_ago=i, close=100.0 + i)

        # 請求2天資料
        result = self.db.get_latest_data("600519", days=2)
        self.assertEqual(len(result), 2)

        # 請求5天資料
        result = self.db.get_latest_data("600519", days=5)
        self.assertEqual(len(result), 5)

    def test_get_latest_data_ordered_by_date_desc(self) -> None:
        """驗證資料按日期降序排列"""
        # 插入3天資料
        for i in range(3):
            self._insert_stock_data("600519", days_ago=i, close=100.0 + i)

        result = self.db.get_latest_data("600519", days=3)

        # 驗證日期降序（最新日期在前）
        self.assertEqual(len(result), 3)
        self.assertGreater(result[0].date, result[1].date)
        self.assertGreater(result[1].date, result[2].date)

    def test_get_latest_data_filters_by_code(self) -> None:
        """驗證按股票程式碼過濾"""
        # 插入不同股票的資料
        self._insert_stock_data("600519", days_ago=0, close=100.0)
        self._insert_stock_data("000001", days_ago=0, close=50.0)

        result = self.db.get_latest_data("600519", days=5)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].code, "600519")


if __name__ == "__main__":
    unittest.main()
