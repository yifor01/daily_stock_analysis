import React from 'react';
import type { AnalysisResult, AnalysisReport } from '../../types/analysis';
import { ReportOverview } from './ReportOverview';
import { ReportStrategy } from './ReportStrategy';
import { ReportNews } from './ReportNews';
import { ReportDetails } from './ReportDetails';

interface ReportSummaryProps {
  data: AnalysisResult | AnalysisReport;
  isHistory?: boolean;
}

/**
 * 完整報告展示元件
 * 整合概覽、策略、資訊、詳情四個區域
 */
export const ReportSummary: React.FC<ReportSummaryProps> = ({
  data,
  isHistory = false,
}) => {
  // 相容 AnalysisResult 和 AnalysisReport 兩種資料格式
  const report: AnalysisReport = 'report' in data ? data.report : data;
  // 使用 report id，因為 queryId 在批次分析時可能重複，且歷史報告詳情介面需要 recordId 來獲取關聯資訊和詳情資料
  const recordId = report.meta.id;

  const { meta, summary, strategy, details } = report;
  const modelUsed = (meta.modelUsed || '').trim();
  const shouldShowModel = Boolean(
    modelUsed && !['unknown', 'error', 'none', 'null', 'n/a'].includes(modelUsed.toLowerCase()),
  );

  return (
    <div className="space-y-5 pb-8 animate-fade-in">
      {/* 概覽區（首屏） */}
      <ReportOverview
        meta={meta}
        summary={summary}
        isHistory={isHistory}
      />

      {/* 策略點位區 */}
      <ReportStrategy strategy={strategy} />

      {/* 資訊區 */}
      <ReportNews recordId={recordId} limit={8} />

      {/* 透明度與追溯區 */}
      <ReportDetails details={details} recordId={recordId} />

      {/* 分析模型標記（Issue #528）— 報告末尾 */}
      {shouldShowModel && (
        <p className="px-1 text-xs text-muted-text">
          分析模型: {modelUsed}
        </p>
      )}
    </div>
  );
};
