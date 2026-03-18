# -*- coding: utf-8 -*-
"""
Email 傳送提醒服務

職責：
1. 透過 SMTP 傳送 Email 訊息
"""
import logging
from typing import Optional, List
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.header import Header
from email.utils import formataddr
import smtplib

from src.config import Config
from src.formatters import markdown_to_html_document


logger = logging.getLogger(__name__)


# SMTP 伺服器配置（自動識別）
SMTP_CONFIGS = {
    # QQ郵箱
    "qq.com": {"server": "smtp.qq.com", "port": 465, "ssl": True},
    "foxmail.com": {"server": "smtp.qq.com", "port": 465, "ssl": True},
    # 網易郵箱
    "163.com": {"server": "smtp.163.com", "port": 465, "ssl": True},
    "126.com": {"server": "smtp.126.com", "port": 465, "ssl": True},
    # Gmail
    "gmail.com": {"server": "smtp.gmail.com", "port": 587, "ssl": False},
    # Outlook
    "outlook.com": {"server": "smtp-mail.outlook.com", "port": 587, "ssl": False},
    "hotmail.com": {"server": "smtp-mail.outlook.com", "port": 587, "ssl": False},
    "live.com": {"server": "smtp-mail.outlook.com", "port": 587, "ssl": False},
    # 新浪
    "sina.com": {"server": "smtp.sina.com", "port": 465, "ssl": True},
    # 搜狐
    "sohu.com": {"server": "smtp.sohu.com", "port": 465, "ssl": True},
    # 阿里雲
    "aliyun.com": {"server": "smtp.aliyun.com", "port": 465, "ssl": True},
    # 139郵箱
    "139.com": {"server": "smtp.139.com", "port": 465, "ssl": True},
}


class EmailSender:
    
    def __init__(self, config: Config):
        """
        初始化 Email 配置

        Args:
            config: 配置物件
        """
        self._email_config = {
            'sender': config.email_sender,
            'sender_name': getattr(config, 'email_sender_name', 'daily_stock_analysis股票分析助手'),
            'password': config.email_password,
            'receivers': config.email_receivers or ([config.email_sender] if config.email_sender else []),
        }
        self._stock_email_groups = getattr(config, 'stock_email_groups', None) or []
        
    def _is_email_configured(self) -> bool:
        """檢查郵件配置是否完整（只需郵箱和授權碼）"""
        return bool(self._email_config['sender'] and self._email_config['password'])
    
    def get_receivers_for_stocks(self, stock_codes: List[str]) -> List[str]:
        """
        Look up email receivers for given stock codes based on stock_email_groups.
        Returns union of receivers for all matching groups; falls back to default if none match.
        """
        if not stock_codes or not self._stock_email_groups:
            return self._email_config['receivers']
        seen: set = set()
        result: List[str] = []
        for stocks, emails in self._stock_email_groups:
            for code in stock_codes:
                if code in stocks:
                    for e in emails:
                        if e not in seen:
                            seen.add(e)
                            result.append(e)
                    break
        return result if result else self._email_config['receivers']

    def get_all_email_receivers(self) -> List[str]:
        """
        Return union of all configured email receivers (all groups + default).
        Used for market review which should go to everyone.
        """
        seen: set = set()
        result: List[str] = []
        for _, emails in self._stock_email_groups:
            for e in emails:
                if e not in seen:
                    seen.add(e)
                    result.append(e)
        for e in self._email_config['receivers']:
            if e not in seen:
                seen.add(e)
                result.append(e)
        return result

    def _format_sender_address(self, sender: str) -> str:
        """Encode display name safely so non-ASCII sender names work across SMTP providers."""
        sender_name = self._email_config.get('sender_name') or '股票分析助手'
        return formataddr((str(Header(str(sender_name), 'utf-8')), sender))

    @staticmethod
    def _close_server(server: Optional[smtplib.SMTP]) -> None:
        """Best-effort SMTP cleanup to avoid leaving sockets open on header/build errors.

        Exceptions from quit()/close() are intentionally silenced — connection may already
        be in a broken state, and there is nothing useful to do at this point.
        """
        if server is None:
            return
        try:
            server.quit()
        except Exception:
            try:
                server.close()
            except Exception:
                pass
    
    def send_to_email(
        self, content: str, subject: Optional[str] = None, receivers: Optional[List[str]] = None
    ) -> bool:
        """
        透過 SMTP 傳送郵件（自動識別 SMTP 伺服器）
        
        Args:
            content: 郵件內容（支援 Markdown，會轉換為 HTML）
            subject: 郵件主題（可選，預設自動生成）
            receivers: 收件人列表（可選，預設使用配置的 receivers）
            
        Returns:
            是否傳送成功
        """
        if not self._is_email_configured():
            logger.warning("郵件配置不完整，跳過推送")
            return False
        
        sender = self._email_config['sender']
        password = self._email_config['password']
        receivers = receivers or self._email_config['receivers']
        server: Optional[smtplib.SMTP] = None
        
        try:
            # 生成主題
            if subject is None:
                date_str = datetime.now().strftime('%Y-%m-%d')
                subject = f"📈 股票智慧分析報告 - {date_str}"
            
            # 將 Markdown 轉換為簡單 HTML
            html_content = markdown_to_html_document(content)
            
            # 構建郵件
            msg = MIMEMultipart('alternative')
            msg['Subject'] = Header(subject, 'utf-8')
            msg['From'] = self._format_sender_address(sender)
            msg['To'] = ', '.join(receivers)
            
            # 新增純文字和 HTML 兩個版本
            text_part = MIMEText(content, 'plain', 'utf-8')
            html_part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(text_part)
            msg.attach(html_part)
            
            # 自動識別 SMTP 配置
            domain = sender.split('@')[-1].lower()
            smtp_config = SMTP_CONFIGS.get(domain)
            
            if smtp_config:
                smtp_server = smtp_config['server']
                smtp_port = smtp_config['port']
                use_ssl = smtp_config['ssl']
                logger.info(f"自動識別郵箱型別: {domain} -> {smtp_server}:{smtp_port}")
            else:
                # 未知郵箱，嘗試通用配置
                smtp_server = f"smtp.{domain}"
                smtp_port = 465
                use_ssl = True
                logger.warning(f"未知郵箱型別 {domain}，嘗試通用配置: {smtp_server}:{smtp_port}")
            
            # 根據配置選擇連線方式
            if use_ssl:
                # SSL 連線（埠 465）
                server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=30)
            else:
                # TLS 連線（埠 587）
                server = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
                server.starttls()
            
            server.login(sender, password)
            server.send_message(msg)
            
            logger.info(f"郵件傳送成功，收件人: {receivers}")
            return True
            
        except smtplib.SMTPAuthenticationError:
            logger.error("郵件傳送失敗：認證錯誤，請檢查郵箱和授權碼是否正確")
            return False
        except smtplib.SMTPConnectError as e:
            logger.error(f"郵件傳送失敗：無法連線 SMTP 伺服器 - {e}")
            return False
        except Exception as e:
            logger.error(f"傳送郵件失敗: {e}")
            return False
        finally:
            self._close_server(server)

    def _send_email_with_inline_image(
        self, image_bytes: bytes, receivers: Optional[List[str]] = None
    ) -> bool:
        """Send email with inline image attachment (Issue #289)."""
        if not self._is_email_configured():
            return False
        sender = self._email_config['sender']
        password = self._email_config['password']
        receivers = receivers or self._email_config['receivers']
        server: Optional[smtplib.SMTP] = None
        try:
            date_str = datetime.now().strftime('%Y-%m-%d')
            subject = f"📈 股票智慧分析報告 - {date_str}"
            msg = MIMEMultipart('related')
            msg['Subject'] = Header(subject, 'utf-8')
            msg['From'] = self._format_sender_address(sender)
            msg['To'] = ', '.join(receivers)

            alt = MIMEMultipart('alternative')
            alt.attach(MIMEText('報告已生成，詳見下方圖片。', 'plain', 'utf-8'))
            html_body = (
                '<p>報告已生成，詳見下方圖片（點選可檢視大圖）：</p>'
                '<p><img src="cid:report-image" alt="股票分析報告" style="max-width:100%%;" /></p>'
            )
            alt.attach(MIMEText(html_body, 'html', 'utf-8'))
            msg.attach(alt)

            img_part = MIMEImage(image_bytes, _subtype='png')
            img_part.add_header('Content-Disposition', 'inline', filename='report.png')
            img_part.add_header('Content-ID', '<report-image>')
            msg.attach(img_part)

            domain = sender.split('@')[-1].lower()
            smtp_config = SMTP_CONFIGS.get(domain)
            if smtp_config:
                smtp_server, smtp_port = smtp_config['server'], smtp_config['port']
                use_ssl = smtp_config['ssl']
            else:
                smtp_server, smtp_port = f"smtp.{domain}", 465
                use_ssl = True

            if use_ssl:
                server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=30)
            else:
                server = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
                server.starttls()
            server.login(sender, password)
            server.send_message(msg)
            logger.info("郵件（內聯圖片）傳送成功，收件人: %s", receivers)
            return True
        except Exception as e:
            logger.error("郵件（內聯圖片）傳送失敗: %s", e)
            return False
        finally:
            self._close_server(server)
