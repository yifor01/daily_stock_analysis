# -*- coding: utf-8 -*-
"""
===================================
非同步任務服務層
===================================

職責：
1. 管理非同步分析任務（執行緒池）
2. 執行股票分析並推送結果
3. 查詢任務狀態和歷史

遷移自 web/services.py 的 AnalysisService 類
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional, Dict, Any, List, Union

from src.enums import ReportType
from src.storage import get_db
from bot.models import BotMessage

logger = logging.getLogger(__name__)


class TaskService:
    """
    非同步任務服務

    負責：
    1. 管理非同步分析任務
    2. 執行股票分析
    3. 觸發通知推送
    """

    _instance: Optional['TaskService'] = None
    _lock = threading.Lock()

    def __init__(self, max_workers: int = 3):
        self._executor: Optional[ThreadPoolExecutor] = None
        self._max_workers = max_workers
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._tasks_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> 'TaskService':
        """獲取單例例項"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @property
    def executor(self) -> ThreadPoolExecutor:
        """獲取或建立執行緒池"""
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=self._max_workers,
                thread_name_prefix="analysis_"
            )
        return self._executor

    def submit_analysis(
        self,
        code: str,
        report_type: Union[ReportType, str] = ReportType.SIMPLE,
        source_message: Optional[BotMessage] = None,
        save_context_snapshot: Optional[bool] = None,
        query_source: str = "bot"
    ) -> Dict[str, Any]:
        """
        提交非同步分析任務

        Args:
            code: 股票程式碼
            report_type: 報告型別列舉
            source_message: 來源訊息（用於回覆）
            save_context_snapshot: 是否儲存上下文快照
            query_source: 任務來源標識（bot/api/cli/system）

        Returns:
            任務資訊字典
        """
        # 確保 report_type 是列舉型別
        if isinstance(report_type, str):
            report_type = ReportType.from_str(report_type)

        task_id = f"{code}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

        # 提交到執行緒池
        self.executor.submit(
            self._run_analysis,
            code,
            task_id,
            report_type,
            source_message,
            save_context_snapshot,
            query_source
        )

        logger.info(f"[TaskService] 已提交股票 {code} 的分析任務, task_id={task_id}, report_type={report_type.value}")

        return {
            "success": True,
            "message": "分析任務已提交，將非同步執行並推送通知",
            "code": code,
            "task_id": task_id,
            "report_type": report_type.value
        }

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """獲取任務狀態"""
        with self._tasks_lock:
            return self._tasks.get(task_id)

    def list_tasks(self, limit: int = 20) -> List[Dict[str, Any]]:
        """列出最近的任務"""
        with self._tasks_lock:
            tasks = list(self._tasks.values())
        # 按開始時間倒序
        tasks.sort(key=lambda x: x.get('start_time', ''), reverse=True)
        return tasks[:limit]

    def get_analysis_history(
        self,
        code: Optional[str] = None,
        query_id: Optional[str] = None,
        days: int = 30,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """獲取分析歷史記錄"""
        db = get_db()
        records = db.get_analysis_history(code=code, query_id=query_id, days=days, limit=limit)
        return [r.to_dict() for r in records]

    def _run_analysis(
        self,
        code: str,
        task_id: str,
        report_type: ReportType = ReportType.SIMPLE,
        source_message: Optional[BotMessage] = None,
        save_context_snapshot: Optional[bool] = None,
        query_source: str = "bot"
    ) -> Dict[str, Any]:
        """
        執行單隻股票分析

        內部方法，線上程池中執行
        """
        # 初始化任務狀態
        with self._tasks_lock:
            self._tasks[task_id] = {
                "task_id": task_id,
                "code": code,
                "status": "running",
                "start_time": datetime.now().isoformat(),
                "result": None,
                "error": None,
                "report_type": report_type.value
            }

        try:
            # 延遲匯入避免迴圈依賴
            from src.config import get_config
            from main import StockAnalysisPipeline

            logger.info(f"[TaskService] 開始分析股票: {code}")

            # 建立分析管道
            config = get_config()
            pipeline = StockAnalysisPipeline(
                config=config,
                max_workers=1,
                source_message=source_message,
                query_id=task_id,
                query_source=query_source,
                save_context_snapshot=save_context_snapshot
            )

            # 執行單隻股票分析（啟用單股推送）
            result = pipeline.process_single_stock(
                code=code,
                skip_analysis=False,
                single_stock_notify=True,
                report_type=report_type
            )

            if result:
                result_data = {
                    "code": result.code,
                    "name": result.name,
                    "sentiment_score": result.sentiment_score,
                    "operation_advice": result.operation_advice,
                    "trend_prediction": result.trend_prediction,
                    "analysis_summary": result.analysis_summary,
                }

                with self._tasks_lock:
                    self._tasks[task_id].update({
                        "status": "completed",
                        "end_time": datetime.now().isoformat(),
                        "result": result_data
                    })

                logger.info(f"[TaskService] 股票 {code} 分析完成: {result.operation_advice}")
                return {"success": True, "task_id": task_id, "result": result_data}
            else:
                with self._tasks_lock:
                    self._tasks[task_id].update({
                        "status": "failed",
                        "end_time": datetime.now().isoformat(),
                        "error": "分析返回空結果"
                    })

                logger.warning(f"[TaskService] 股票 {code} 分析失敗: 返回空結果")
                return {"success": False, "task_id": task_id, "error": "分析返回空結果"}

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[TaskService] 股票 {code} 分析異常: {error_msg}")

            with self._tasks_lock:
                self._tasks[task_id].update({
                    "status": "failed",
                    "end_time": datetime.now().isoformat(),
                    "error": error_msg
                })

            return {"success": False, "task_id": task_id, "error": error_msg}


# ============================================================
# 便捷函式
# ============================================================

def get_task_service() -> TaskService:
    """獲取任務服務單例"""
    return TaskService.get_instance()
