# -*- coding: utf-8 -*-
"""
Wechat 傳送提醒服務

職責：
1. 透過企業微信 Webhook 傳送文字訊息
2. 透過企業微信 Webhook 傳送圖片訊息
"""
import logging
import base64
import hashlib
import requests
import time

from src.config import Config
from src.formatters import chunk_content_by_max_bytes


logger = logging.getLogger(__name__)


# WeChat Work image msgtype limit ~2MB (base64 payload)
WECHAT_IMAGE_MAX_BYTES = 2 * 1024 * 1024

class WechatSender:
    
    def __init__(self, config: Config):
        """
        初始化企業微信配置

        Args:
            config: 配置物件
        """
        self._wechat_url = config.wechat_webhook_url
        self._wechat_max_bytes = getattr(config, 'wechat_max_bytes', 4000)
        self._wechat_msg_type = getattr(config, 'wechat_msg_type', 'markdown')
        self._webhook_verify_ssl = getattr(config, 'webhook_verify_ssl', True)
        
    def send_to_wechat(self, content: str) -> bool:
        """
        推送訊息到企業微信機器人
        
        企業微信 Webhook 訊息格式：
        支援 markdown 型別以及 text 型別, markdown 型別在微信中無法展示，可以使用 text 型別,
        markdown 型別會解析 markdown 格式,text 型別會直接傳送純文字。

        markdown 型別示例：
        {
            "msgtype": "markdown",
            "markdown": {
                "content": "## 標題\n\n內容"
            }
        }
        
        text 型別示例：
        {
            "msgtype": "text",
            "text": {
                "content": "內容"
            }
        }

        注意：企業微信 Markdown 限制 4096 位元組（非字元）, Text 型別限制 2048 位元組，超長內容會自動分批傳送
        可透過環境變數 WECHAT_MAX_BYTES 調整限制值
        
        Args:
            content: Markdown 格式的訊息內容
            
        Returns:
            是否傳送成功
        """
        if not self._wechat_url:
            logger.warning("企業微信 Webhook 未配置，跳過推送")
            return False
        
        # 根據訊息型別動態限制上限，避免 text 型別超過企業微信 2048 位元組限制
        if self._wechat_msg_type == 'text':
            max_bytes = min(self._wechat_max_bytes, 2000)  # 預留一定位元組給系統/分頁標記
        else:
            max_bytes = self._wechat_max_bytes  # markdown 預設 4000 位元組
        
        # 檢查位元組長度，超長則分批傳送
        content_bytes = len(content.encode('utf-8'))
        if content_bytes > max_bytes:
            logger.info(f"訊息內容超長({content_bytes}位元組/{len(content)}字元)，將分批傳送")
            return self._send_wechat_chunked(content, max_bytes)
        
        try:
            return self._send_wechat_message(content)
        except Exception as e:
            logger.error(f"傳送企業微信訊息失敗: {e}")
            return False

    def _send_wechat_image(self, image_bytes: bytes) -> bool:
        """Send image via WeChat Work webhook msgtype image (Issue #289)."""
        if not self._wechat_url:
            return False
        if len(image_bytes) > WECHAT_IMAGE_MAX_BYTES:
            logger.warning(
                "企業微信圖片超限 (%d > %d bytes)，拒絕傳送，呼叫方應 fallback 為文字",
                len(image_bytes), WECHAT_IMAGE_MAX_BYTES,
            )
            return False
        try:
            b64 = base64.b64encode(image_bytes).decode("ascii")
            md5_hash = hashlib.md5(image_bytes).hexdigest()
            payload = {
                "msgtype": "image",
                "image": {"base64": b64, "md5": md5_hash},
            }
            response = requests.post(
                self._wechat_url, json=payload, timeout=30, verify=self._webhook_verify_ssl
            )
            if response.status_code == 200:
                result = response.json()
                if result.get("errcode") == 0:
                    logger.info("企業微信圖片傳送成功")
                    return True
                logger.error("企業微信圖片傳送失敗: %s", result.get("errmsg", ""))
            else:
                logger.error("企業微信請求失敗: HTTP %s", response.status_code)
            return False
        except Exception as e:
            logger.error("企業微信圖片傳送異常: %s", e)
            return False
    
    def _send_wechat_message(self, content: str) -> bool:
        """傳送企業微信訊息"""
        payload = self._gen_wechat_payload(content)
        
        response = requests.post(
            self._wechat_url,
            json=payload,
            timeout=10,
            verify=self._webhook_verify_ssl
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('errcode') == 0:
                logger.info("企業微信訊息傳送成功")
                return True
            else:
                logger.error(f"企業微信返回錯誤: {result}")
                return False
        else:
            logger.error(f"企業微信請求失敗: {response.status_code}")
            return False
        
    def _send_wechat_chunked(self, content: str, max_bytes: int) -> bool:
        """
        分批傳送長訊息到企業微信
        
        按股票分析塊（以 --- 或 ### 分隔）智慧分割，確保每批不超過限制
        
        Args:
            content: 完整訊息內容
            max_bytes: 單條訊息最大位元組數
            
        Returns:
            是否全部傳送成功
        """
        chunks = chunk_content_by_max_bytes(content, max_bytes, add_page_marker=True)
        total_chunks = len(chunks)
        success_count = 0
        for i, chunk in enumerate(chunks):
            if self._send_wechat_message(chunk):
                success_count += 1
            else:
                logger.error(f"企業微信第 {i+1}/{total_chunks} 批傳送失敗")
            if i < total_chunks - 1:
                time.sleep(1)
        return success_count == len(chunks)

    def _gen_wechat_payload(self, content: str) -> dict:
        """生成企業微信訊息 payload"""
        if self._wechat_msg_type == 'text':
            return {
                "msgtype": "text",
                "text": {
                    "content": content
                }
            }
        else:
            return {
                "msgtype": "markdown",
                "markdown": {
                    "content": content
                }
            }
