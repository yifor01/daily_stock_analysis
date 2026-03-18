import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  AnalysisRequest,
  AnalysisResult,
  AnalyzeResponse,
  AnalyzeAsyncResponse,
  AnalysisReport,
  TaskStatus,
  TaskListResponse,
} from '../types/analysis';

// ============ API 介面 ============

export const analysisApi = {
  /**
   * 觸發股票分析
   * @param data 分析請求引數
   * @returns 同步模式返回 AnalysisResult；非同步模式返回單任務或批次任務接受響應
   */
  analyze: async (data: AnalysisRequest): Promise<AnalyzeResponse> => {
    const requestData = {
      stock_code: data.stockCode,
      stock_codes: data.stockCodes,
      report_type: data.reportType || 'detailed',
      force_refresh: data.forceRefresh || false,
      async_mode: data.asyncMode || false,
    };

    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/analysis/analyze',
      requestData
    );

    const result = toCamelCase<AnalyzeResponse>(response.data);

    // 確保同步分析返回中的 report 欄位正確轉換
    if ('report' in result && result.report) {
      result.report = toCamelCase<AnalysisReport>(result.report);
    }

    return result;
  },

  /**
   * 非同步模式觸發分析
   * 返回 task_id，透過 SSE 或輪詢獲取結果
   * @param data 分析請求引數
   * @returns 單任務或批次任務接受響應；409 時丟擲重複任務錯誤
   */
  analyzeAsync: async (data: AnalysisRequest): Promise<AnalyzeAsyncResponse> => {
    const requestData = {
      stock_code: data.stockCode,
      stock_codes: data.stockCodes,
      report_type: data.reportType || 'detailed',
      force_refresh: data.forceRefresh || false,
      async_mode: true,
    };

    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/analysis/analyze',
      requestData,
      {
        // 允許 202 狀態碼
        validateStatus: (status) => status === 200 || status === 202 || status === 409,
      }
    );

    // 處理 409 重複提交錯誤
    if (response.status === 409) {
      const errorData = toCamelCase<{
        error: string;
        message: string;
        stockCode: string;
        existingTaskId: string;
      }>(response.data);
      throw new DuplicateTaskError(errorData.stockCode, errorData.existingTaskId, errorData.message);
    }

    return toCamelCase<AnalyzeAsyncResponse>(response.data);
  },

  /**
   * 獲取非同步任務狀態
   * @param taskId 任務 ID
   */
  getStatus: async (taskId: string): Promise<TaskStatus> => {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/analysis/status/${taskId}`
    );

    const data = toCamelCase<TaskStatus>(response.data);

    // 確保巢狀的 result 也被正確轉換
    if (data.result) {
      data.result = toCamelCase<AnalysisResult>(data.result);
      if (data.result.report) {
        data.result.report = toCamelCase<AnalysisReport>(data.result.report);
      }
    }

    return data;
  },

  /**
   * 獲取任務列表
   * @param params 篩選引數
   */
  getTasks: async (params?: {
    status?: string;
    limit?: number;
  }): Promise<TaskListResponse> => {
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/analysis/tasks',
      { params }
    );

    const data = toCamelCase<TaskListResponse>(response.data);

    return data;
  },

  /**
   * 獲取 SSE 流 URL
   * 用於 EventSource 連線
   */
  getTaskStreamUrl: (): string => {
    // 獲取 API base URL
    const baseUrl = apiClient.defaults.baseURL || '';
    return `${baseUrl}/api/v1/analysis/tasks/stream`;
  },
};

// ============ 自定義錯誤類 ============

/**
 * 重複任務錯誤
 * 當股票正在分析中時丟擲
 */
export class DuplicateTaskError extends Error {
  stockCode: string;
  existingTaskId: string;

  constructor(stockCode: string, existingTaskId: string, message?: string) {
    super(message || `股票 ${stockCode} 正在分析中`);
    this.name = 'DuplicateTaskError';
    this.stockCode = stockCode;
    this.existingTaskId = existingTaskId;
  }
}
