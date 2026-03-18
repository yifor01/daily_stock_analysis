# -*- coding: utf-8 -*-
"""
===================================
飛書 Stream 模式介面卡
===================================

使用飛書官方 lark-oapi SDK 的 WebSocket 長連線模式接入機器人，
無需公網 IP 和 Webhook 配置。

優勢：
- 不需要公網 IP 或域名
- 不需要配置 Webhook URL
- 透過 WebSocket 長連線接收訊息
- 更簡單的接入方式
- 內建自動重連和心跳保活

依賴：
pip install lark-oapi

飛書長連線文件：
https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/server-side-sdk/python--sdk/handle-events
"""

import json
import logging
import threading
from datetime import datetime
from typing import Optional, Callable
import time

logger = logging.getLogger(__name__)

# 嘗試匯入飛書 SDK
try:
    import lark_oapi as lark
    from lark_oapi import ws
    from lark_oapi.api.im.v1 import (
        P2ImMessageReceiveV1,
        ReplyMessageRequest,
        ReplyMessageRequestBody,
        CreateMessageRequest,
        CreateMessageRequestBody,
    )

    FEISHU_SDK_AVAILABLE = True
except ImportError:
    FEISHU_SDK_AVAILABLE = False
    logger.warning("[Feishu Stream] lark-oapi SDK 未安裝，Stream 模式不可用")
    logger.warning("[Feishu Stream] 請執行: pip install lark-oapi")

from bot.models import BotMessage, BotResponse, ChatType
from src.formatters import format_feishu_markdown, chunk_content_by_max_bytes
from src.config import get_config


class FeishuReplyClient:
    """
    飛書訊息回覆客戶端
    
    使用飛書 API 傳送回覆訊息。
    """

    def __init__(self, app_id: str, app_secret: str):
        """
        Args:
            app_id: 飛書應用 ID
            app_secret: 飛書應用金鑰
        """
        if not FEISHU_SDK_AVAILABLE:
            raise ImportError("lark-oapi SDK 未安裝")

        self._client = lark.Client.builder() \
            .app_id(app_id) \
            .app_secret(app_secret) \
            .log_level(lark.LogLevel.WARNING) \
            .build()

        # 獲取配置的最大位元組數
        config = get_config()
        self._max_bytes = getattr(config, 'feishu_max_bytes', 20000)

    def _send_interactive_card(self, content: str, message_id: Optional[str] = None,
                               chat_id: Optional[str] = None,
                               receive_id_type: str = "chat_id",
                               at_user: bool = False, user_id: Optional[str] = None) -> bool:
        """
        傳送互動卡片訊息（支援 Markdown 渲染）
        
        Args:
            content: Markdown 格式的內容
            message_id: 原訊息 ID（回覆時使用）
            chat_id: 會話 ID（主動傳送時使用）
            receive_id_type: 接收者 ID 型別
            at_user: 是否 @使用者
            user_id: 使用者 open_id（at_user=True 時需要）
            
        Returns:
            是否傳送成功
        """
        try:
            # 如果需要 @使用者，在內容前新增 @ 標記
            final_content = content
            if at_user and user_id:
                final_content = f"<at user_id=\"{user_id}\"></at> {content}"
            
            # 構建互動卡片 payload
            card_data = {
                "config": {"wide_screen_mode": True},
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": final_content
                        }
                    }
                ]
            }

            content_json = json.dumps(card_data)

            if message_id:
                # 回覆訊息
                request = ReplyMessageRequest.builder() \
                    .message_id(message_id) \
                    .request_body(
                    ReplyMessageRequestBody.builder()
                    .content(content_json)
                    .msg_type("interactive")
                    .build()
                ) \
                    .build()
                response = self._client.im.v1.message.reply(request)
            else:
                # 主動傳送訊息
                request = CreateMessageRequest.builder() \
                    .receive_id_type(receive_id_type) \
                    .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .content(content_json)
                    .msg_type("interactive")
                    .build()
                ) \
                    .build()
                response = self._client.im.v1.message.create(request)

            if not response.success():
                logger.error(
                    f"[Feishu Stream] 傳送互動卡片失敗: code={response.code}, "
                    f"msg={response.msg}, log_id={response.get_log_id()}"
                )
                return False

            logger.debug(f"[Feishu Stream] 傳送互動卡片成功")
            return True

        except Exception as e:
            logger.error(f"[Feishu Stream] 傳送互動卡片異常: {e}")
            return False

    def reply_text(self, message_id: str, text: str, at_user: bool = False,
                   user_id: Optional[str] = None) -> bool:
        """
        回覆文字訊息（支援互動卡片和分段傳送）
        
        Args:
            message_id: 原訊息 ID
            text: 回覆文字
            at_user: 是否 @使用者
            user_id: 使用者 open_id（at_user=True 時需要）
            
        Returns:
            是否傳送成功
        """
        # 將文字轉換為飛書 Markdown 格式
        formatted_text = format_feishu_markdown(text)

        # 檢查是否需要分段傳送
        content_bytes = len(formatted_text.encode('utf-8'))
        if content_bytes > self._max_bytes:
            logger.info(
                f"[Feishu Stream] 回覆訊息內容超長({content_bytes}位元組)，將分批傳送"
            )
            return self._send_to_chat_chunked(
                formatted_text,
                lambda chunk: self._send_interactive_card(
                    chunk,
                    message_id=message_id,
                    at_user=at_user,
                    user_id=user_id,
                ),
            )

        # 單條訊息，使用互動卡片
        return self._send_interactive_card(
            formatted_text, message_id=message_id, at_user=at_user, user_id=user_id
        )

    def send_to_chat(self, chat_id: str, text: str,
                     receive_id_type: str = "chat_id") -> bool:
        """
        傳送訊息到指定會話（支援互動卡片和分段傳送）
        
        Args:
            chat_id: 會話 ID
            text: 訊息文字
            receive_id_type: 接收者 ID 型別，預設 chat_id
            
        Returns:
            是否傳送成功
        """
        # 將文字轉換為飛書 Markdown 格式
        formatted_text = format_feishu_markdown(text)

        # 檢查是否需要分段傳送
        content_bytes = len(formatted_text.encode('utf-8'))
        if content_bytes > self._max_bytes:
            logger.info(
                f"[Feishu Stream] 傳送訊息內容超長({content_bytes}位元組)，將分批傳送"
            )
            return self._send_to_chat_chunked(
                formatted_text,
                lambda chunk: self._send_interactive_card(
                    chunk,
                    chat_id=chat_id,
                    receive_id_type=receive_id_type,
                ),
            )
        
        # 單條訊息，使用互動卡片
        return self._send_interactive_card(formatted_text, chat_id=chat_id, receive_id_type=receive_id_type)
        
    def _send_to_chat_chunked(self, content: str, send_func: Callable[[str], bool]) -> bool:
        """
        分批傳送訊息（支援互動卡片和分段傳送）
        
        Args:
            content: 訊息文字
            send_func: 傳送單個分片的函式，返回是否傳送成功
            
        Returns:
            是否全部傳送成功
        """
        chunks = chunk_content_by_max_bytes(content, self._max_bytes, add_page_marker=True)
        success_count = 0
        for i, chunk in enumerate(chunks):
            if send_func(chunk):
                success_count += 1
            else:
                logger.error(f"[Feishu Stream] 傳送訊息失敗: {chunk}")
            if i < len(chunks) - 1:
                time.sleep(1)
        return success_count == len(chunks)


class FeishuStreamHandler:
    """
    飛書 Stream 模式訊息處理器
    
    將 SDK 的事件轉換為統一的 BotMessage 格式，
    並呼叫命令分發器處理。
    """

    def __init__(
            self,
            on_message: Callable[[BotMessage], BotResponse],
            reply_client: FeishuReplyClient
    ):
        """
        Args:
            on_message: 訊息處理回撥函式，接收 BotMessage 返回 BotResponse
            reply_client: 飛書回覆客戶端
        """
        self._on_message = on_message
        self._reply_client = reply_client
        self._logger = logger

    @staticmethod
    def _truncate_log_content(text: str, max_len: int = 200) -> str:
        """截斷日誌內容"""
        cleaned = text.replace("\n", " ").strip()
        if len(cleaned) > max_len:
            return f"{cleaned[:max_len]}..."
        return cleaned

    def _log_incoming_message(self, message: BotMessage) -> None:
        """記錄收到的訊息日誌"""
        content = message.raw_content or message.content or ""
        summary = self._truncate_log_content(content)
        self._logger.info(
            "[Feishu Stream] Incoming message: msg_id=%s user_id=%s "
            "chat_id=%s chat_type=%s content=%s",
            message.message_id,
            message.user_id,
            message.chat_id,
            getattr(message.chat_type, "value", message.chat_type),
            summary,
        )

    def handle_message(self, event: 'P2ImMessageReceiveV1') -> None:
        """
        處理接收到的訊息事件
        
        Args:
            event: 飛書訊息接收事件
        """
        try:
            # 解析訊息
            bot_message = self._parse_event_message(event)

            if bot_message is None:
                return

            self._log_incoming_message(bot_message)

            # 呼叫訊息處理回撥
            response = self._on_message(bot_message)

            # 傳送回覆
            if response and response.text:
                self._reply_client.reply_text(
                    message_id=bot_message.message_id,
                    text=response.text,
                    at_user=response.at_user,
                    user_id=bot_message.user_id if response.at_user else None
                )

        except Exception as e:
            self._logger.error(f"[Feishu Stream] 處理訊息失敗: {e}")
            self._logger.exception(e)

    def _parse_event_message(self, event: 'P2ImMessageReceiveV1') -> Optional[BotMessage]:
        """
        解析飛書事件訊息為統一格式
        
        Args:
            event: P2ImMessageReceiveV1 事件物件
        """
        try:
            event_data = event.event
            if event_data is None:
                return None

            message_data = event_data.message
            sender_data = event_data.sender

            if message_data is None:
                return None

            # 只處理文字訊息
            message_type = message_data.message_type or ""
            if message_type != "text":
                self._logger.debug(f"[Feishu Stream] 忽略非文字訊息: {message_type}")
                return None

            # 解析訊息內容
            content_str = message_data.content or "{}"
            try:
                content_json = json.loads(content_str)
                raw_content = content_json.get("text", "")
            except json.JSONDecodeError:
                raw_content = content_str

            # 提取命令（去除 @機器人）
            content = self._extract_command(raw_content, message_data.mentions)
            mentioned = "@" in raw_content or bool(message_data.mentions)

            # 獲取傳送者資訊
            user_id = ""
            if sender_data and sender_data.sender_id:
                user_id = sender_data.sender_id.open_id or sender_data.sender_id.user_id or ""

            # 獲取會話型別
            chat_type_str = message_data.chat_type or ""
            if chat_type_str == "group":
                chat_type = ChatType.GROUP
            elif chat_type_str == "p2p":
                chat_type = ChatType.PRIVATE
            else:
                chat_type = ChatType.UNKNOWN

            # 建立時間
            create_time = message_data.create_time
            try:
                if create_time:
                    timestamp = datetime.fromtimestamp(int(create_time) / 1000)
                else:
                    timestamp = datetime.now()
            except (ValueError, TypeError):
                timestamp = datetime.now()

            # 構建原始資料
            raw_data = {
                "header": {
                    "event_id": event.header.event_id if event.header else "",
                    "event_type": event.header.event_type if event.header else "",
                    "create_time": event.header.create_time if event.header else "",
                    "token": event.header.token if event.header else "",
                    "app_id": event.header.app_id if event.header else "",
                },
                "event": {
                    "message_id": message_data.message_id,
                    "chat_id": message_data.chat_id,
                    "chat_type": message_data.chat_type,
                    "content": message_data.content,
                }
            }

            return BotMessage(
                platform="feishu",
                message_id=message_data.message_id or "",
                user_id=user_id,
                user_name=user_id,  # 飛書不直接返回使用者名稱
                chat_id=message_data.chat_id or "",
                chat_type=chat_type,
                content=content,
                raw_content=raw_content,
                mentioned=mentioned,
                mentions=[m.key or "" for m in (message_data.mentions or [])],
                timestamp=timestamp,
                raw_data=raw_data,
            )

        except Exception as e:
            self._logger.error(f"[Feishu Stream] 解析訊息失敗: {e}")
            return None

    def _extract_command(self, text: str, mentions: list) -> str:
        """
        提取命令內容（去除 @機器人）
        
        飛書的 @使用者 格式是：@_user_1, @_user_2 等
        
        Args:
            text: 原始訊息文字
            mentions: @提及列表
        """
        import re

        # 方式1: 透過 mentions 列表移除（精確匹配）
        for mention in (mentions or []):
            key = getattr(mention, 'key', '') or ''
            if key:
                text = text.replace(key, '')

        # 方式2: 正則兜底，移除飛書 @使用者 格式（@_user_N）
        # 當 mentions 為空或未正確傳遞時生效
        text = re.sub(r'@_user_\d+\s*', '', text)

        # 清理多餘空格
        return ' '.join(text.split())


class FeishuStreamClient:
    """
    飛書 Stream 模式客戶端
    
    封裝 lark-oapi SDK 的 WebSocket 客戶端，提供簡單的啟動介面。
    
    使用方式：
        client = FeishuStreamClient()
        client.start()  # 阻塞執行
        
        # 或者在後臺執行
        client.start_background()
    """

    def __init__(
            self,
            app_id: Optional[str] = None,
            app_secret: Optional[str] = None
    ):
        """
        Args:
            app_id: 應用 ID（不傳則從配置讀取）
            app_secret: 應用金鑰（不傳則從配置讀取）
        """
        if not FEISHU_SDK_AVAILABLE:
            raise ImportError(
                "lark-oapi SDK 未安裝。\n"
                "請執行: pip install lark-oapi"
            )

        from src.config import get_config
        config = get_config()

        self._app_id = app_id or getattr(config, 'feishu_app_id', None)
        self._app_secret = app_secret or getattr(config, 'feishu_app_secret', None)

        if not self._app_id or not self._app_secret:
            raise ValueError(
                "飛書 Stream 模式需要配置 FEISHU_APP_ID 和 FEISHU_APP_SECRET"
            )

        self._ws_client: Optional[ws.Client] = None
        self._reply_client: Optional[FeishuReplyClient] = None
        self._background_thread: Optional[threading.Thread] = None
        self._running = False

    def _create_message_handler(self) -> Callable[[BotMessage], BotResponse]:
        """建立訊息處理函式"""

        def handle_message(message: BotMessage) -> BotResponse:
            from bot.dispatcher import get_dispatcher
            dispatcher = get_dispatcher()
            return dispatcher.dispatch(message)

        return handle_message

    def _create_event_handler(self) -> 'lark.EventDispatcherHandler':
        """建立事件分發處理器"""
        # 建立回覆客戶端
        self._reply_client = FeishuReplyClient(self._app_id, self._app_secret)

        # 建立訊息處理器
        handler = FeishuStreamHandler(
            self._create_message_handler(),
            self._reply_client
        )

        # 建立並註冊事件處理器
        # 注意：encrypt_key 和 verification_token 在長連線模式下不是必需的
        # 但 SDK 要求傳入（可以為空字串）
        from src.config import get_config
        config = get_config()

        encrypt_key = getattr(config, 'feishu_encrypt_key', '') or ''
        verification_token = getattr(config, 'feishu_verification_token', '') or ''

        event_handler = lark.EventDispatcherHandler.builder(
            encrypt_key=encrypt_key,
            verification_token=verification_token,
            level=lark.LogLevel.WARNING
        ).register_p2_im_message_receive_v1(
            handler.handle_message
        ).build()

        return event_handler

    def start(self) -> None:
        """
        啟動 Stream 客戶端（阻塞）
        
        此方法會阻塞當前執行緒，直到客戶端停止。
        """
        logger.info("[Feishu Stream] 正在啟動...")

        # 建立事件處理器
        event_handler = self._create_event_handler()

        # 建立 WebSocket 客戶端
        self._ws_client = ws.Client(
            app_id=self._app_id,
            app_secret=self._app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.WARNING,
            auto_reconnect=True
        )

        self._running = True
        logger.info("[Feishu Stream] 客戶端已啟動，等待訊息...")

        # 啟動（阻塞）
        self._ws_client.start()

    def start_background(self) -> None:
        """
        在後臺執行緒啟動 Stream 客戶端（非阻塞）
        
        適用於與其他服務（如 WebUI）同時執行的場景。
        """
        if self._background_thread and self._background_thread.is_alive():
            logger.warning("[Feishu Stream] 客戶端已在執行")
            return

        self._running = True
        self._background_thread = threading.Thread(
            target=self._run_in_background,
            daemon=True,
            name="FeishuStreamClient"
        )
        self._background_thread.start()
        logger.info("[Feishu Stream] 後臺客戶端已啟動")

    def _run_in_background(self) -> None:
        """後臺執行（處理異常和重連）"""
        import time

        while self._running:
            try:
                self.start()
            except Exception as e:
                logger.error(f"[Feishu Stream] 執行異常: {e}")
                if self._running:
                    logger.info("[Feishu Stream] 5 秒後重連...")
                    time.sleep(5)

    def stop(self) -> None:
        """停止客戶端"""
        self._running = False
        logger.info("[Feishu Stream] 客戶端已停止")

    @property
    def is_running(self) -> bool:
        """是否正在執行"""
        return self._running


# 全域性客戶端例項
_stream_client: Optional[FeishuStreamClient] = None


def get_feishu_stream_client() -> Optional[FeishuStreamClient]:
    """獲取全域性 Stream 客戶端例項"""
    global _stream_client

    if _stream_client is None and FEISHU_SDK_AVAILABLE:
        try:
            _stream_client = FeishuStreamClient()
        except (ImportError, ValueError) as e:
            logger.warning(f"[Feishu Stream] 無法建立客戶端: {e}")
            return None

    return _stream_client


def start_feishu_stream_background() -> bool:
    """
    在後臺啟動飛書 Stream 客戶端
    
    Returns:
        是否成功啟動
    """
    client = get_feishu_stream_client()
    if client:
        client.start_background()
        return True
    return False
