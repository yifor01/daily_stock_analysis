import type React from 'react';
import type { TaskInfo } from '../../types/analysis';

/**
 * 任務項元件屬性
 */
interface TaskItemProps {
  task: TaskInfo;
}

/**
 * 單個任務項
 */
const TaskItem: React.FC<TaskItemProps> = ({ task }) => {
  const isPending = task.status === 'pending';
  const isProcessing = task.status === 'processing';

  return (
    <div className="flex items-center gap-3 px-3 py-2 bg-elevated rounded-lg border border-white/5">
      {/* 狀態圖示 */}
      <div className="shrink-0">
        {isProcessing ? (
          // 載入動畫
          <svg className="w-4 h-4 text-cyan animate-spin" fill="none" viewBox="0 0 24 24">
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
        ) : isPending ? (
          // 等待圖示
          <svg className="w-4 h-4 text-muted-text" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        ) : null}
      </div>

      {/* 任務資訊 */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-white truncate">
            {task.stockName || task.stockCode}
          </span>
          <span className="text-xs text-muted-text">
            {task.stockCode}
          </span>
        </div>
        {task.message && (
          <p className="text-xs text-secondary-text truncate mt-0.5">
            {task.message}
          </p>
        )}
      </div>

      {/* 狀態標籤 */}
      <div className="flex-shrink-0">
        <span
          className={`text-xs px-1.5 py-0.5 rounded ${
            isProcessing
              ? 'bg-cyan/20 text-cyan'
              : 'bg-white/10 text-muted-text'
          }`}
        >
          {isProcessing ? '分析中' : '等待中'}
        </span>
      </div>
    </div>
  );
};

/**
 * 任務面板屬性
 */
interface TaskPanelProps {
  /** 任務列表 */
  tasks: TaskInfo[];
  /** 是否顯示 */
  visible?: boolean;
  /** 標題 */
  title?: string;
  /** 自定義類名 */
  className?: string;
}

/**
 * 任務面板元件
 * 顯示進行中的分析任務列表
 */
export const TaskPanel: React.FC<TaskPanelProps> = ({
  tasks,
  visible = true,
  title = '分析任務',
  className = '',
}) => {
  // 篩選活躍任務（pending 和 processing）
  const activeTasks = tasks.filter(
    (t) => t.status === 'pending' || t.status === 'processing'
  );

  // 無任務或不可見時不渲染
  if (!visible || activeTasks.length === 0) {
    return null;
  }

  const pendingCount = activeTasks.filter((t) => t.status === 'pending').length;
  const processingCount = activeTasks.filter((t) => t.status === 'processing').length;

  return (
    <div className={`bg-card rounded-xl border border-white/5 overflow-hidden ${className}`}>
      {/* 標題欄 */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-white/5">
        <div className="flex items-center gap-2">
          <svg className="w-4 h-4 text-cyan" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
          <span className="text-sm font-medium text-white">{title}</span>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-text">
          {processingCount > 0 && (
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 bg-cyan rounded-full animate-pulse" />
              {processingCount} 進行中
            </span>
          )}
          {pendingCount > 0 && (
            <span>{pendingCount} 等待中</span>
          )}
        </div>
      </div>

      {/* 任務列表 */}
      <div className="p-2 space-y-2 max-h-64 overflow-y-auto">
        {activeTasks.map((task) => (
          <TaskItem key={task.taskId} task={task} />
        ))}
      </div>
    </div>
  );
};

export default TaskPanel;
