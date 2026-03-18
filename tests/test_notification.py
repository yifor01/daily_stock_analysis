# -*- coding: utf-8 -*-
"""
===================================
A股自選股智慧分析系統 - 通知服務單元測試
===================================

職責：
1. 驗證通知服務的配置檢測邏輯
2. 驗證通知服務的渠道檢測邏輯
3. 驗證通知服務的訊息傳送邏輯

TODO: 
1. 新增傳送渠道以外的測試，如：
    - 生成日報
2. 新增 send_to_context 的測試
"""
import os
import sys
import unittest
from unittest import mock
from typing import Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Keep this test runnable when optional LLM/runtime deps are not installed.
for optional_module in ("litellm", "json_repair"):
    try:
        __import__(optional_module)
    except ModuleNotFoundError:
        sys.modules[optional_module] = mock.MagicMock()

from src.config import Config
from src.notification import NotificationService, NotificationChannel
from src.analyzer import AnalysisResult
import requests


def _make_config(**overrides) -> Config:
    """Create a Config instance overriding only notification-related fields."""
    return Config(stock_list=[], **overrides)


def _make_response(status_code: int, json: Optional[dict] = None) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    if json:
        response.json = lambda: json
    return response


class TestNotificationServiceSendToMethods(unittest.TestCase):
    """測試通知傳送服務

    測試設計：

    測試按照渠道的字母順序排列，在合適位置新增新的測試方法。
    如果採用長訊息分批傳送，必須單獨測試分批傳送的邏輯，
        e.g. test_send_to_discord_via_notification_service_with_bot_requires_chunking

    1. 新增模擬配置：
    使用 mock.patch 裝飾器來模擬 get_config 函式，
    使用 _make_config 函式新增配置，並返回 Config 例項。

    2. 檢查配置是否正確：
    使用 assertIn 檢查 NotificationChannel.xxxx 是否在
    `NotificationService.get_available_channels()` 返回值中。

    3. 模擬請求響應：
    使用 mock.patch 裝飾器來模擬 requests.post 函式，
    使用 _make_response 函式模擬請求響應，並返回 Response 例項。
    若使用其他函式模擬請求響應，則使用 mock.patch 裝飾器來模擬該函式。

    4. 使用 assertTrue 檢查 send 的返回值。

    5. 使用 assert_called_once 檢查請求函式是否被呼叫一次。
    測試分批傳送時，使用 assertAlmostEqual(mock_post.call_count, ...) 檢查請求函式被呼叫次數

    """

    @mock.patch("src.notification.get_config")
    def test_no_channels_service_unavailable_and_send_returns_false(self, mock_get_config):
        mock_get_config.return_value = _make_config()

        service = NotificationService()

        self.assertFalse(service.is_available())
        result = service.send("test content")
        self.assertFalse(result)

    @mock.patch("src.notification.get_config")
    @mock.patch("requests.post")
    def test_send_to_astrbot_via_notification_service(self, mock_post: mock.MagicMock, mock_get_config: mock.MagicMock):
        cfg = _make_config(astrbot_url="https://astrbot.example")
        mock_get_config.return_value = cfg
        mock_post.return_value = _make_response(200)

        service = NotificationService()
        self.assertIn(NotificationChannel.ASTRBOT, service.get_available_channels())

        ok = service.send("astrbot content")

        self.assertTrue(ok)
        mock_post.assert_called_once()

    @mock.patch("src.notification.get_config")
    @mock.patch("requests.post")
    def test_send_to_custom_webhook_via_notification_service(
        self, mock_post: mock.MagicMock, mock_get_config: mock.MagicMock
    ):
        cfg = _make_config(custom_webhook_urls=["https://example.com/webhook"])
        mock_get_config.return_value = cfg
        mock_post.return_value = _make_response(200)

        service = NotificationService()
        self.assertIn(NotificationChannel.CUSTOM, service.get_available_channels())

        ok = service.send("custom content")

        self.assertTrue(ok)
        mock_post.assert_called_once()

    @mock.patch("src.notification.get_config")
    @mock.patch("requests.post")
    def test_send_to_discord_via_notification_service_with_webhook(
        self, mock_post: mock.MagicMock, mock_get_config: mock.MagicMock
    ):
        cfg = _make_config(discord_webhook_url="https://discord.example/webhook")
        mock_get_config.return_value = cfg
        mock_post.return_value = _make_response(204)

        service = NotificationService()
        self.assertIn(NotificationChannel.DISCORD, service.get_available_channels())

        ok = service.send("discord content")

        self.assertTrue(ok)
        mock_post.assert_called_once()

    @mock.patch("src.notification.get_config")
    @mock.patch("requests.post")
    def test_send_to_discord_via_notification_service_with_bot(
        self, mock_post: mock.MagicMock, mock_get_config: mock.MagicMock
    ):
        cfg = _make_config(discord_bot_token="TOKEN", discord_main_channel_id="123")
        mock_get_config.return_value = cfg
        mock_post.return_value = _make_response(200)

        service = NotificationService()
        self.assertIn(NotificationChannel.DISCORD, service.get_available_channels())

        ok = service.send("discord content")

        self.assertTrue(ok)
        mock_post.assert_called_once()
        
    @mock.patch("src.notification.get_config")
    @mock.patch("requests.post")
    def test_send_to_discord_via_notification_service_with_bot_requires_chunking(self, mock_post: mock.MagicMock, mock_get_config: mock.MagicMock):
        cfg = _make_config(
            discord_bot_token="TOKEN",
            discord_main_channel_id="123",
            discord_max_words=2000,
        )
        mock_get_config.return_value = cfg
        mock_post.return_value = _make_response(200)

        service = NotificationService()
        self.assertIn(NotificationChannel.DISCORD, service.get_available_channels())

        ok = service.send("A" * 6000)

        self.assertTrue(ok)
        self.assertAlmostEqual(mock_post.call_count, 4, delta=1)


class TestNotificationServiceReportGeneration(unittest.TestCase):
    """報告生成與選路相關測試。"""

    @mock.patch("src.notification.get_config")
    def test_generate_aggregate_report_routes_by_report_type(self, mock_get_config: mock.MagicMock):
        mock_get_config.return_value = _make_config()
        service = NotificationService()
        result = AnalysisResult(
            code="600519",
            name="貴州茅臺",
            sentiment_score=72,
            trend_prediction="看多",
            operation_advice="持有",
            analysis_summary="穩健",
        )

        with mock.patch.object(service, "generate_dashboard_report", return_value="dashboard") as mock_dashboard, mock.patch.object(
            service, "generate_brief_report", return_value="brief"
        ) as mock_brief:
            self.assertEqual(service.generate_aggregate_report([result], "simple"), "dashboard")
            self.assertEqual(service.generate_aggregate_report([result], "full"), "dashboard")
            self.assertEqual(service.generate_aggregate_report([result], "detailed"), "dashboard")
            self.assertEqual(service.generate_aggregate_report([result], "brief"), "brief")

        self.assertEqual(mock_dashboard.call_count, 3)
        mock_brief.assert_called_once()

    @mock.patch("src.notification.get_config")
    def test_generate_single_stock_report_keeps_legacy_simple_format(self, mock_get_config: mock.MagicMock):
        mock_get_config.return_value = _make_config(report_renderer_enabled=True)
        service = NotificationService()
        result = AnalysisResult(
            code="600519",
            name="貴州茅臺",
            sentiment_score=72,
            trend_prediction="看多",
            operation_advice="持有",
            analysis_summary="穩健",
        )

        with mock.patch("src.services.report_renderer.render") as mock_render:
            out = service.generate_single_stock_report(result)

        mock_render.assert_not_called()
        self.assertIn("貴州茅臺", out)
        self.assertIn("600519", out)

    @mock.patch("src.notification.get_config")
    def test_history_compare_context_uses_cache(self, mock_get_config: mock.MagicMock):
        mock_get_config.return_value = _make_config(report_history_compare_n=3)
        service = NotificationService()
        result = AnalysisResult(
            code="600519",
            name="貴州茅臺",
            sentiment_score=72,
            trend_prediction="看多",
            operation_advice="持有",
            analysis_summary="穩健",
            query_id="q-1",
        )

        with mock.patch(
            "src.services.history_comparison_service.get_signal_changes_batch",
            return_value={"600519": []},
        ) as mock_batch:
            first = service._get_history_compare_context([result])
            second = service._get_history_compare_context([result])

        self.assertEqual(first, {"history_by_code": {"600519": []}})
        self.assertEqual(second, {"history_by_code": {"600519": []}})
        mock_batch.assert_called_once()

    @mock.patch("src.notification.get_config")
    @mock.patch("smtplib.SMTP_SSL")
    def test_send_to_email_via_notification_service(
        self, mock_smtp_ssl: mock.MagicMock, mock_get_config: mock.MagicMock
    ):
        cfg = _make_config(
            email_sender="user@qq.com",
            email_password="PASS",
            email_receivers=["default@example.com"],
        )
        mock_get_config.return_value = cfg

        service = NotificationService()
        self.assertIn(NotificationChannel.EMAIL, service.get_available_channels())

        ok = service.send("email content")

        self.assertTrue(ok)
        mock_smtp_ssl.assert_called_once()
        mock_smtp_ssl.return_value.send_message.assert_called_once()

    @mock.patch("src.notification.get_config")
    @mock.patch("smtplib.SMTP_SSL")
    def test_send_to_email_with_stock_group_routing(
        self, mock_smtp_ssl: mock.MagicMock, mock_get_config: mock.MagicMock
    ):
        cfg = _make_config(
            email_sender="user@qq.com",
            email_password="PASS",
            email_receivers=["default@example.com"],
            stock_email_groups=[(["000001", "600519"], ["group@example.com"])],
        )
        mock_get_config.return_value = cfg

        service = NotificationService()
        self.assertIn(NotificationChannel.EMAIL, service.get_available_channels())

        server = mock_smtp_ssl.return_value

        ok = service.send("content", email_stock_codes=["000001"])

        self.assertTrue(ok)
        mock_smtp_ssl.assert_called_once()
        server.send_message.assert_called_once()
        msg = server.send_message.call_args[0][0]
        self.assertIn("group@example.com", msg["To"])

    @mock.patch("src.notification.get_config")
    @mock.patch("requests.post")
    def test_send_to_feishu_via_notification_service(self, mock_post: mock.MagicMock, mock_get_config: mock.MagicMock):
        cfg = _make_config(feishu_webhook_url="https://feishu.example")
        mock_get_config.return_value = cfg
        mock_post.return_value = _make_response(200, {"code": 0})

        service = NotificationService()
        self.assertIn(NotificationChannel.FEISHU, service.get_available_channels())

        ok = service.send("hello feishu")

        self.assertTrue(ok)
        mock_post.assert_called_once()
        
    @mock.patch("src.notification.get_config")
    @mock.patch("requests.post")
    def test_send_to_feishu_via_notification_service_requires_chunking(self, mock_post: mock.MagicMock, mock_get_config: mock.MagicMock):
        cfg = _make_config(feishu_webhook_url="https://feishu.example", feishu_max_bytes=2000)
        mock_get_config.return_value = cfg
        mock_post.return_value = _make_response(200, {"code": 0})

        service = NotificationService()
        self.assertIn(NotificationChannel.FEISHU, service.get_available_channels())

        ok = service.send("A" * 6000)

        self.assertTrue(ok)
        self.assertAlmostEqual(mock_post.call_count, 4, delta=1)

    @mock.patch("src.notification.get_config")
    @mock.patch("requests.post")
    def test_send_to_pushover_via_notification_service(
        self, mock_post: mock.MagicMock, mock_get_config: mock.MagicMock
    ):
        cfg = _make_config(
            pushover_user_key="USER",
            pushover_api_token="TOKEN",
        )
        mock_get_config.return_value = cfg
        mock_post.return_value = _make_response(200, {"status": 1})

        service = NotificationService()
        self.assertIn(NotificationChannel.PUSHOVER, service.get_available_channels())

        ok = service.send("pushover content")

        self.assertTrue(ok)
        mock_post.assert_called_once()

    @mock.patch("src.notification.get_config")
    @mock.patch("requests.post")
    def test_send_to_pushplus_via_notification_service(
        self, mock_post: mock.MagicMock, mock_get_config: mock.MagicMock
    ):
        cfg = _make_config(pushplus_token="TOKEN")
        mock_get_config.return_value = cfg
        mock_post.return_value = _make_response(200, {"code": 200})

        service = NotificationService()
        self.assertIn(NotificationChannel.PUSHPLUS, service.get_available_channels())

        ok = service.send("pushplus content")

        self.assertTrue(ok)
        mock_post.assert_called_once()

    @mock.patch("src.notification_sender.pushplus_sender.time.sleep")
    @mock.patch("src.notification.get_config")
    @mock.patch("requests.post")
    def test_send_to_pushplus_via_notification_service_requires_chunking(
        self,
        mock_post: mock.MagicMock,
        mock_get_config: mock.MagicMock,
        _mock_sleep: mock.MagicMock,
    ):
        cfg = _make_config(pushplus_token="TOKEN")
        mock_get_config.return_value = cfg
        mock_post.return_value = _make_response(200, {"code": 200})

        service = NotificationService()
        self.assertIn(NotificationChannel.PUSHPLUS, service.get_available_channels())

        ok = service.send("A" * 25000)

        self.assertTrue(ok)
        self.assertGreaterEqual(mock_post.call_count, 2)

    @mock.patch("src.notification.get_config")
    @mock.patch("requests.post")
    def test_send_to_serverchan3_via_notification_service(
        self, mock_post: mock.MagicMock, mock_get_config: mock.MagicMock
    ):
        cfg = _make_config(serverchan3_sendkey="SCTKEY")
        mock_get_config.return_value = cfg
        mock_post.return_value = _make_response(200, {"code": 0})

        service = NotificationService()
        self.assertIn(NotificationChannel.SERVERCHAN3, service.get_available_channels())

        ok = service.send("serverchan content")

        self.assertTrue(ok)
        mock_post.assert_called_once()

    @mock.patch("src.notification.get_config")
    @mock.patch("requests.post")
    def test_send_to_telegram_via_notification_service(
        self, mock_post: mock.MagicMock, mock_get_config: mock.MagicMock
    ):
        cfg = _make_config(telegram_bot_token="TOKEN", telegram_chat_id="123")
        mock_get_config.return_value = cfg
        mock_post.return_value = _make_response(200, {"ok": True})

        service = NotificationService()
        self.assertIn(NotificationChannel.TELEGRAM, service.get_available_channels())

        ok = service.send("hello telegram")

        self.assertTrue(ok)
        mock_post.assert_called_once()

    @mock.patch("src.notification.get_config")
    @mock.patch("requests.post")
    def test_send_to_wechat_via_notification_service(self, mock_post: mock.MagicMock, mock_get_config: mock.MagicMock):
        cfg = _make_config(wechat_webhook_url="https://wechat.example")
        mock_get_config.return_value = cfg
        mock_post.return_value = _make_response(200, {"errcode": 0})

        service = NotificationService()
        self.assertIn(NotificationChannel.WECHAT, service.get_available_channels())

        ok = service.send("hello wechat")

        self.assertTrue(ok)
        mock_post.assert_called_once()

    @mock.patch("src.notification.get_config")
    @mock.patch("requests.post")
    def test_send_to_wechat_via_notification_service_requires_chunking(self, mock_post: mock.MagicMock, mock_get_config: mock.MagicMock):
        cfg = _make_config(wechat_webhook_url="https://wechat.example", wechat_max_bytes=2000)
        mock_get_config.return_value = cfg
        mock_post.return_value = _make_response(200, {"errcode": 0})

        service = NotificationService()
        self.assertIn(NotificationChannel.WECHAT, service.get_available_channels())

        ok = service.send("A" * 6000)

        self.assertTrue(ok)
        self.assertAlmostEqual(mock_post.call_count, 4, delta=1)


if __name__ == "__main__":
    unittest.main()
