/**
 * 股票分析相關型別定義
 * 與 API 規範 (api_spec.json) 對齊
 */

// ============ 請求型別 ============

export interface AnalysisRequest {
  stockCode?: string;
  stockCodes?: string[];
  reportType?: 'simple' | 'detailed' | 'full' | 'brief';
  forceRefresh?: boolean;
  asyncMode?: boolean;
}

// ============ 報告型別 ============

/** 報告元資訊 */
export interface ReportMeta {
  id?: number;  // 分析歷史記錄主鍵 ID（歷史報告時有此欄位）
  queryId: string;
  stockCode: string;
  stockName: string;
  reportType: 'simple' | 'detailed' | 'full' | 'brief';
  createdAt: string;
  currentPrice?: number;
  changePct?: number;
  modelUsed?: string;  // 分析使用的 LLM 模型（Issue #528）
}

/** 情緒標籤 */
export type SentimentLabel = '極度悲觀' | '悲觀' | '中性' | '樂觀' | '極度樂觀';

/** 報告概覽區 */
export interface ReportSummary {
  analysisSummary: string;
  operationAdvice: string;
  trendPrediction: string;
  sentimentScore: number;
  sentimentLabel?: SentimentLabel;
}

/** 策略點位區 */
export interface ReportStrategy {
  idealBuy?: string;
  secondaryBuy?: string;
  stopLoss?: string;
  takeProfit?: string;
}

/** 詳情區（可摺疊） */
export interface ReportDetails {
  newsContent?: string;
  rawResult?: Record<string, unknown>;
  contextSnapshot?: Record<string, unknown>;
  financialReport?: Record<string, unknown>;
  dividendMetrics?: Record<string, unknown>;
}

/** 完整分析報告 */
export interface AnalysisReport {
  meta: ReportMeta;
  summary: ReportSummary;
  strategy?: ReportStrategy;
  details?: ReportDetails;
}

// ============ 分析結果型別 ============

/** 同步分析返回結果 */
export interface AnalysisResult {
  queryId: string;
  stockCode: string;
  stockName: string;
  report: AnalysisReport;
  createdAt: string;
}

/** 非同步任務接受響應 */
export interface TaskAccepted {
  taskId: string;
  status: 'pending' | 'processing';
  message?: string;
}

export interface BatchTaskAcceptedItem {
  taskId: string;
  stockCode: string;
  status: 'pending' | 'processing';
  message?: string;
}

export interface BatchDuplicateTaskItem {
  stockCode: string;
  existingTaskId: string;
  message: string;
}

export interface BatchTaskAcceptedResponse {
  accepted: BatchTaskAcceptedItem[];
  duplicates: BatchDuplicateTaskItem[];
  message: string;
}

export type AnalyzeAsyncResponse = TaskAccepted | BatchTaskAcceptedResponse;

export type AnalyzeResponse = AnalysisResult | AnalyzeAsyncResponse;

/** 任務狀態 */
export interface TaskStatus {
  taskId: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress?: number;
  result?: AnalysisResult;
  error?: string;
}

/** 任務詳情（用於任務列表和 SSE 事件） */
export interface TaskInfo {
  taskId: string;
  stockCode: string;
  stockName?: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;
  message?: string;
  reportType: string;
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
  error?: string;
}

/** 任務列表響應 */
export interface TaskListResponse {
  total: number;
  pending: number;
  processing: number;
  tasks: TaskInfo[];
}

/** 重複任務錯誤響應 */
export interface DuplicateTaskError {
  error: 'duplicate_task';
  message: string;
  stockCode: string;
  existingTaskId: string;
}

// ============ 歷史記錄型別 ============

/** 歷史記錄摘要（列表展示用） */
export interface HistoryItem {
  id: number;  // Record primary key ID, always present for persisted history items
  queryId: string;  // 分析記錄關聯 query_id（批次分析時重複）
  stockCode: string;
  stockName?: string;
  reportType?: string;
  sentimentScore?: number;
  operationAdvice?: string;
  createdAt: string;
}

/** 歷史記錄列表響應 */
export interface HistoryListResponse {
  total: number;
  page: number;
  limit: number;
  items: HistoryItem[];
}

/** 新聞情報條目 */
export interface NewsIntelItem {
  title: string;
  snippet: string;
  url: string;
}

/** 新聞情報響應 */
export interface NewsIntelResponse {
  total: number;
  items: NewsIntelItem[];
}

/** 歷史列表篩選引數 */
export interface HistoryFilters {
  stockCode?: string;
  startDate?: string;
  endDate?: string;
}

/** 歷史列表分頁引數 */
export interface HistoryPagination {
  page: number;
  limit: number;
}

// ============ 錯誤型別 ============

export interface ApiError {
  error: string;
  message: string;
  detail?: Record<string, unknown>;
}

// ============ 輔助函式 ============

/** 根據情緒評分獲取情緒標籤 */
export const getSentimentLabel = (score: number): SentimentLabel => {
  if (score <= 20) return '極度悲觀';
  if (score <= 40) return '悲觀';
  if (score <= 60) return '中性';
  if (score <= 80) return '樂觀';
  return '極度樂觀';
};

/** 根據情緒評分獲取顏色 */
export const getSentimentColor = (score: number): string => {
  if (score <= 20) return '#ef4444'; // red-500
  if (score <= 40) return '#f97316'; // orange-500
  if (score <= 60) return '#eab308'; // yellow-500
  if (score <= 80) return '#22c55e'; // green-500
  return '#10b981'; // emerald-500
};
