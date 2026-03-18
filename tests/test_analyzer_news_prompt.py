# -*- coding: utf-8 -*-
"""Tests for analyzer news prompt hard constraints (Issue #697)."""

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

try:
    import litellm  # noqa: F401
except ModuleNotFoundError:
    sys.modules["litellm"] = MagicMock()

from src.analyzer import GeminiAnalyzer


class AnalyzerNewsPromptTestCase(unittest.TestCase):
    def test_prompt_contains_time_constraints(self) -> None:
        with patch.object(GeminiAnalyzer, "_init_litellm", return_value=None):
            analyzer = GeminiAnalyzer()

        context = {
            "code": "600519",
            "stock_name": "貴州茅臺",
            "date": "2026-03-16",
            "today": {},
            "fundamental_context": {
                "earnings": {
                    "data": {
                        "financial_report": {"report_date": "2025-12-31", "revenue": 1000},
                        "dividend": {"ttm_cash_dividend_per_share": 1.2, "ttm_dividend_yield_pct": 2.4},
                    }
                }
            },
        }
        fake_cfg = SimpleNamespace(
            news_max_age_days=30,
            news_strategy_profile="medium",  # 7 days
        )
        with patch("src.analyzer.get_config", return_value=fake_cfg):
            prompt = analyzer._format_prompt(context, "貴州茅臺", news_context="news")

        self.assertIn("近7日的新聞搜尋結果", prompt)
        self.assertIn("每一條都必須帶具體日期（YYYY-MM-DD）", prompt)
        self.assertIn("超出近7日視窗的新聞一律忽略", prompt)
        self.assertIn("時間未知、無法確定釋出日期的新聞一律忽略", prompt)
        self.assertIn("財報與分紅（價值投資口徑）", prompt)
        self.assertIn("禁止編造", prompt)

    def test_prompt_prefers_context_news_window_days(self) -> None:
        with patch.object(GeminiAnalyzer, "_init_litellm", return_value=None):
            analyzer = GeminiAnalyzer()

        context = {
            "code": "600519",
            "stock_name": "貴州茅臺",
            "date": "2026-03-16",
            "today": {},
            "news_window_days": 1,
        }
        fake_cfg = SimpleNamespace(
            news_max_age_days=30,
            news_strategy_profile="long",  # 30 days if fallback is used
        )
        with patch("src.analyzer.get_config", return_value=fake_cfg):
            prompt = analyzer._format_prompt(context, "貴州茅臺", news_context="news")

        self.assertIn("近1日的新聞搜尋結果", prompt)
        self.assertIn("超出近1日視窗的新聞一律忽略", prompt)


if __name__ == "__main__":
    unittest.main()
