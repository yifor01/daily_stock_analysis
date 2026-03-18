# -*- coding: utf-8 -*-
"""
===================================
A股自選股智慧分析系統 - 非同步任務佇列
===================================

職責：
1. 管理非同步分析任務的生命週期
2. 防止相同股票程式碼重複提交
3. 提供 SSE 事件廣播機制
4. 任務完成後持久化到資料庫
"""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List, Any, TYPE_CHECKING, Tuple, Literal

if TYPE_CHECKING:
    from asyncio import Queue as AsyncQueue

from data_provider.base import canonical_stock_code

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """任務狀態列舉"""
    PENDING = "pending"        # 等待執行
    PROCESSING = "processing"  # 執行中
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"          # 失敗


@dataclass
class TaskInfo:
    """
    任務資訊資料類
    
    包含任務的完整狀態資訊，用於 API 響應和內部管理
    """
    task_id: str
    stock_code: str
    stock_name: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0
    message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    report_type: str = "detailed"
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典，用於 API 響應"""
        return {
            "task_id": self.task_id,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "report_type": self.report_type,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }
    
    def copy(self) -> 'TaskInfo':
        """建立任務資訊的副本"""
        return TaskInfo(
            task_id=self.task_id,
            stock_code=self.stock_code,
            stock_name=self.stock_name,
            status=self.status,
            progress=self.progress,
            message=self.message,
            result=self.result,
            error=self.error,
            report_type=self.report_type,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=self.completed_at,
        )


class DuplicateTaskError(Exception):
    """
    重複提交異常
    
    當股票已在分析中時丟擲此異常
    """
    def __init__(self, stock_code: str, existing_task_id: str):
        self.stock_code = stock_code
        self.existing_task_id = existing_task_id
        super().__init__(f"股票 {stock_code} 正在分析中 (task_id: {existing_task_id})")


class AnalysisTaskQueue:
    """
    非同步分析任務佇列
    
    單例模式，全域性唯一例項
    
    特性：
    1. 防止相同股票程式碼重複提交
    2. 執行緒池執行分析任務
    3. SSE 事件廣播機制
    4. 任務完成後自動持久化
    """
    
    _instance: Optional['AnalysisTaskQueue'] = None
    _instance_lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, max_workers: int = 3):
        # 防止重複初始化
        if hasattr(self, '_initialized') and self._initialized:
            return
        
        self._max_workers = max_workers
        self._executor: Optional[ThreadPoolExecutor] = None
        
        # 核心資料結構
        self._tasks: Dict[str, TaskInfo] = {}           # task_id -> TaskInfo
        self._analyzing_stocks: Dict[str, str] = {}     # stock_code -> task_id
        self._futures: Dict[str, Future] = {}           # task_id -> Future
        
        # SSE 訂閱者列表（asyncio.Queue 例項）
        self._subscribers: List['AsyncQueue'] = []
        self._subscribers_lock = threading.Lock()
        
        # 主事件迴圈引用（用於跨執行緒廣播）
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        
        # 執行緒安全鎖
        self._data_lock = threading.RLock()
        
        # 任務歷史保留數量（記憶體中）
        self._max_history = 100
        
        self._initialized = True
        logger.info(f"[TaskQueue] 初始化完成，最大併發: {max_workers}")
    
    @property
    def executor(self) -> ThreadPoolExecutor:
        """懶載入執行緒池"""
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=self._max_workers,
                thread_name_prefix="analysis_task_"
            )
        return self._executor

    @property
    def max_workers(self) -> int:
        """Return current executor max worker setting."""
        return self._max_workers

    def _has_inflight_tasks_locked(self) -> bool:
        """Check whether queue has any pending/processing tasks."""
        if self._analyzing_stocks:
            return True
        return any(
            task.status in (TaskStatus.PENDING, TaskStatus.PROCESSING)
            for task in self._tasks.values()
        )

    def sync_max_workers(
        self,
        max_workers: int,
        *,
        log: bool = True,
    ) -> Literal["applied", "unchanged", "deferred_busy"]:
        """
        Try to sync queue concurrency without replacing singleton instance.

        Returns:
            - "applied": new value applied immediately (idle queue only)
            - "unchanged": target equals current value or invalid target
            - "deferred_busy": queue is busy, apply is deferred
        """
        try:
            target = max(1, int(max_workers))
        except (TypeError, ValueError):
            if log:
                logger.warning("[TaskQueue] 忽略非法 MAX_WORKERS 值: %r", max_workers)
            return "unchanged"

        executor_to_shutdown: Optional[ThreadPoolExecutor] = None
        previous: int
        with self._data_lock:
            previous = self._max_workers
            if target == previous:
                return "unchanged"

            if self._has_inflight_tasks_locked():
                if log:
                    logger.info(
                        "[TaskQueue] 最大併發調整延後: 當前繁忙 (%s -> %s)",
                        previous,
                        target,
                    )
                return "deferred_busy"

            self._max_workers = target
            executor_to_shutdown = self._executor
            self._executor = None

        if executor_to_shutdown is not None:
            executor_to_shutdown.shutdown(wait=False)

        if log:
            logger.info("[TaskQueue] 最大併發已更新: %s -> %s", previous, target)
        return "applied"
    
    # ========== 任務提交與查詢 ==========
    
    def is_analyzing(self, stock_code: str) -> bool:
        """
        檢查股票是否正在分析中
        
        Args:
            stock_code: 股票程式碼
            
        Returns:
            True 表示正在分析中
        """
        with self._data_lock:
            return stock_code in self._analyzing_stocks
    
    def get_analyzing_task_id(self, stock_code: str) -> Optional[str]:
        """
        獲取正在分析該股票的任務 ID
        
        Args:
            stock_code: 股票程式碼
            
        Returns:
            任務 ID，如果沒有則返回 None
        """
        with self._data_lock:
            return self._analyzing_stocks.get(stock_code)
    
    def submit_task(
        self,
        stock_code: str,
        stock_name: Optional[str] = None,
        report_type: str = "detailed",
        force_refresh: bool = False,
    ) -> TaskInfo:
        """
        提交分析任務
        
        Args:
            stock_code: 股票程式碼
            stock_name: 股票名稱（可選）
            report_type: 報告型別
            force_refresh: 是否強制重新整理
            
        Returns:
            TaskInfo: 任務資訊
            
        Raises:
            DuplicateTaskError: 股票正在分析中
        """
        stock_code = canonical_stock_code(stock_code)
        if not stock_code:
            raise ValueError("股票程式碼不能為空或僅包含空白字元")

        accepted, duplicates = self.submit_tasks_batch(
            [stock_code],
            stock_name=stock_name,
            report_type=report_type,
            force_refresh=force_refresh,
        )
        if duplicates:
            raise duplicates[0]
        return accepted[0]

    def submit_tasks_batch(
        self,
        stock_codes: List[str],
        stock_name: Optional[str] = None,
        report_type: str = "detailed",
        force_refresh: bool = False,
    ) -> Tuple[List[TaskInfo], List[DuplicateTaskError]]:
        """
        批次提交分析任務。

        - 重複股票會被跳過並記錄在 duplicates 中
        - 如果執行緒池提交過程中發生異常，則回滾本次已建立任務，避免部分成功
        """
        accepted: List[TaskInfo] = []
        duplicates: List[DuplicateTaskError] = []
        created_task_ids: List[str] = []

        normalized_codes = [
            normalized for normalized in (canonical_stock_code(code) for code in stock_codes)
            if normalized
        ]

        with self._data_lock:
            for stock_code in normalized_codes:
                if stock_code in self._analyzing_stocks:
                    existing_task_id = self._analyzing_stocks[stock_code]
                    duplicates.append(DuplicateTaskError(stock_code, existing_task_id))
                    continue

                task_id = uuid.uuid4().hex
                task_info = TaskInfo(
                    task_id=task_id,
                    stock_code=stock_code,
                    stock_name=stock_name,
                    status=TaskStatus.PENDING,
                    message="任務已加入佇列",
                    report_type=report_type,
                )
                self._tasks[task_id] = task_info
                self._analyzing_stocks[stock_code] = task_id

                try:
                    future = self.executor.submit(
                        self._execute_task,
                        task_id,
                        stock_code,
                        report_type,
                        force_refresh,
                    )
                except Exception:
                    # 回滾當前批次，避免 API 拿不到 task_id 卻留下半提交任務。
                    self._rollback_submitted_tasks_locked(created_task_ids + [task_id])
                    raise

                self._futures[task_id] = future
                accepted.append(task_info)
                created_task_ids.append(task_id)
                logger.info(f"[TaskQueue] 任務已提交: {stock_code} -> {task_id}")

            # Keep task_created ordered before worker-emitted task_started/task_completed.
            # Broadcasting here also preserves batch rollback semantics because we only
            # reach this point after every submit in the batch has succeeded.
            for task_info in accepted:
                self._broadcast_event("task_created", task_info.to_dict())

        return accepted, duplicates

    def _rollback_submitted_tasks_locked(self, task_ids: List[str]) -> None:
        """回滾當前批次已建立但尚未穩定返回給呼叫方的任務。"""
        for task_id in task_ids:
            future = self._futures.pop(task_id, None)
            if future is not None:
                future.cancel()

            task = self._tasks.pop(task_id, None)
            if task and self._analyzing_stocks.get(task.stock_code) == task_id:
                del self._analyzing_stocks[task.stock_code]
    
    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """
        獲取任務資訊
        
        Args:
            task_id: 任務 ID
            
        Returns:
            TaskInfo 或 None
        """
        with self._data_lock:
            task = self._tasks.get(task_id)
            return task.copy() if task else None
    
    def list_pending_tasks(self) -> List[TaskInfo]:
        """
        獲取所有進行中的任務（pending + processing）
        
        Returns:
            任務列表（副本）
        """
        with self._data_lock:
            return [
                task.copy() for task in self._tasks.values()
                if task.status in (TaskStatus.PENDING, TaskStatus.PROCESSING)
            ]
    
    def list_all_tasks(self, limit: int = 50) -> List[TaskInfo]:
        """
        獲取所有任務（按建立時間倒序）
        
        Args:
            limit: 返回數量限制
            
        Returns:
            任務列表（副本）
        """
        with self._data_lock:
            tasks = sorted(
                self._tasks.values(),
                key=lambda t: t.created_at,
                reverse=True
            )
            return [t.copy() for t in tasks[:limit]]
    
    def get_task_stats(self) -> Dict[str, int]:
        """
        獲取任務統計資訊
        
        Returns:
            統計資訊字典
        """
        with self._data_lock:
            stats = {
                "total": len(self._tasks),
                "pending": 0,
                "processing": 0,
                "completed": 0,
                "failed": 0,
            }
            for task in self._tasks.values():
                stats[task.status.value] = stats.get(task.status.value, 0) + 1
            return stats
    
    # ========== 任務執行 ==========
    
    def _execute_task(
        self,
        task_id: str,
        stock_code: str,
        report_type: str,
        force_refresh: bool,
    ) -> Optional[Dict[str, Any]]:
        """
        執行分析任務（線上程池中執行）
        
        Args:
            task_id: 任務 ID
            stock_code: 股票程式碼
            report_type: 報告型別
            force_refresh: 是否強制重新整理
            
        Returns:
            分析結果字典
        """
        # 更新狀態為處理中
        with self._data_lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            task.status = TaskStatus.PROCESSING
            task.started_at = datetime.now()
            task.message = "正在分析中..."
            task.progress = 10
        
        self._broadcast_event("task_started", task.to_dict())
        
        try:
            # 匯入分析服務（延遲匯入避免迴圈依賴）
            from src.services.analysis_service import AnalysisService
            
            # 執行分析
            service = AnalysisService()
            result = service.analyze_stock(
                stock_code=stock_code,
                report_type=report_type,
                force_refresh=force_refresh,
                query_id=task_id,
            )
            
            if result:
                # 更新任務狀態為完成
                with self._data_lock:
                    task = self._tasks.get(task_id)
                    if task:
                        task.status = TaskStatus.COMPLETED
                        task.progress = 100
                        task.completed_at = datetime.now()
                        task.result = result
                        task.message = "分析完成"
                        task.stock_name = result.get("stock_name", task.stock_name)
                        
                        # 從分析中集合移除
                        if task.stock_code in self._analyzing_stocks:
                            del self._analyzing_stocks[task.stock_code]
                
                self._broadcast_event("task_completed", task.to_dict())
                logger.info(f"[TaskQueue] 任務完成: {task_id} ({stock_code})")
                
                # 清理過期任務
                self._cleanup_old_tasks()
                
                return result
            else:
                # 分析返回空結果
                raise Exception("分析返回空結果")
                
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[TaskQueue] 任務失敗: {task_id} ({stock_code}), 錯誤: {error_msg}")
            
            with self._data_lock:
                task = self._tasks.get(task_id)
                if task:
                    task.status = TaskStatus.FAILED
                    task.completed_at = datetime.now()
                    task.error = error_msg[:200]  # 限制錯誤資訊長度
                    task.message = f"分析失敗: {error_msg[:50]}"
                    
                    # 從分析中集合移除
                    if task.stock_code in self._analyzing_stocks:
                        del self._analyzing_stocks[task.stock_code]
            
            self._broadcast_event("task_failed", task.to_dict())
            
            # 清理過期任務
            self._cleanup_old_tasks()
            
            return None
    
    def _cleanup_old_tasks(self) -> int:
        """
        清理過期的已完成任務
        
        保留最近 _max_history 個任務
        
        Returns:
            清理的任務數量
        """
        with self._data_lock:
            if len(self._tasks) <= self._max_history:
                return 0
            
            # 按時間排序，刪除舊的已完成任務
            completed_tasks = sorted(
                [t for t in self._tasks.values()
                 if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)],
                key=lambda t: t.created_at
            )
            
            to_remove = len(self._tasks) - self._max_history
            removed = 0
            
            for task in completed_tasks[:to_remove]:
                del self._tasks[task.task_id]
                if task.task_id in self._futures:
                    del self._futures[task.task_id]
                removed += 1
            
            if removed > 0:
                logger.debug(f"[TaskQueue] 清理了 {removed} 個過期任務")
            
            return removed
    
    # ========== SSE 事件廣播 ==========
    
    def subscribe(self, queue: 'AsyncQueue') -> None:
        """
        訂閱任務事件
        
        Args:
            queue: asyncio.Queue 例項，用於接收事件
        """
        with self._subscribers_lock:
            self._subscribers.append(queue)
            # 捕獲當前事件迴圈（應在主執行緒的 async 上下文中呼叫）
            try:
                self._main_loop = asyncio.get_running_loop()
            except RuntimeError:
                # 如果不在 async 上下文中，嘗試獲取事件迴圈
                try:
                    self._main_loop = asyncio.get_event_loop()
                except RuntimeError:
                    pass
            logger.debug(f"[TaskQueue] 新訂閱者加入，當前訂閱者數: {len(self._subscribers)}")
    
    def unsubscribe(self, queue: 'AsyncQueue') -> None:
        """
        取消訂閱任務事件
        
        Args:
            queue: 要取消訂閱的 asyncio.Queue 例項
        """
        with self._subscribers_lock:
            if queue in self._subscribers:
                self._subscribers.remove(queue)
                logger.debug(f"[TaskQueue] 訂閱者離開，當前訂閱者數: {len(self._subscribers)}")
    
    def _broadcast_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        廣播事件到所有訂閱者
        
        使用 call_soon_threadsafe 確保跨執行緒安全
        
        Args:
            event_type: 事件型別
            data: 事件資料
        """
        event = {"type": event_type, "data": data}
        
        with self._subscribers_lock:
            subscribers = self._subscribers.copy()
            loop = self._main_loop
        
        if not subscribers:
            return
        
        if loop is None:
            logger.warning("[TaskQueue] 無法廣播事件：主事件迴圈未設定")
            return
        
        for queue in subscribers:
            try:
                # 使用 call_soon_threadsafe 將事件放入 asyncio 佇列
                # 這是從工作執行緒向主事件迴圈傳送訊息的安全方式
                loop.call_soon_threadsafe(queue.put_nowait, event)
            except RuntimeError as e:
                # 事件迴圈已關閉
                logger.debug(f"[TaskQueue] 廣播事件跳過（迴圈已關閉）: {e}")
            except Exception as e:
                logger.warning(f"[TaskQueue] 廣播事件失敗: {e}")
    
    # ========== 清理方法 ==========
    
    def shutdown(self) -> None:
        """關閉任務佇列"""
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None
            logger.info("[TaskQueue] 執行緒池已關閉")


# ========== 便捷函式 ==========

def get_task_queue() -> AnalysisTaskQueue:
    """
    獲取任務佇列單例
    
    Returns:
        AnalysisTaskQueue 例項
    """
    queue = AnalysisTaskQueue()
    try:
        from src.config import get_config

        config = get_config()
        target_workers = max(1, int(getattr(config, "max_workers", queue.max_workers)))
        queue.sync_max_workers(target_workers, log=False)
    except Exception as exc:
        logger.debug("[TaskQueue] 讀取 MAX_WORKERS 失敗，使用當前併發設定: %s", exc)

    return queue
