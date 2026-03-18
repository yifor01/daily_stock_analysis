import type React from 'react';
import type { ReportMeta, ReportSummary as ReportSummaryType } from '../../types/analysis';
import { ScoreGauge, Card } from '../common';
import { formatDateTime } from '../../utils/format';

interface ReportOverviewProps {
  meta: ReportMeta;
  summary: ReportSummaryType;
  isHistory?: boolean;
}

/**
 * 報告概覽區元件 - 終端風格
 */
export const ReportOverview: React.FC<ReportOverviewProps> = ({
  meta,
  summary
}) => {
  // 根據漲跌幅獲取顏色
  const getPriceChangeColor = (changePct: number | undefined): string => {
    if (changePct === undefined || changePct === null) return 'text-muted-text';
    if (changePct > 0) return 'text-[#ff4d4d]'; // 紅漲
    if (changePct < 0) return 'text-[#00d46a]'; // 綠跌
    return 'text-muted-text';
  };

  // 格式化漲跌幅
  const formatChangePct = (changePct: number | undefined): string => {
    if (changePct === undefined || changePct === null) return '--';
    const sign = changePct > 0 ? '+' : '';
    return `${sign}${changePct.toFixed(2)}%`;
  };

  return (
    <div className="space-y-5">
      {/* 主資訊區 - 兩列布局，items-stretch 確保右側與左側同高 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 items-stretch">
        {/* 左側：股票資訊與結論 */}
        <div className="lg:col-span-2 space-y-5">
          {/* 股票頭部 */}
          <Card variant="gradient" padding="md">
            <div className="flex items-start justify-between mb-5">
              <div className="flex-1">
                <div className="flex items-center gap-3">
                  <h2 className="text-[28px] font-bold leading-tight text-white">
                    {meta.stockName || meta.stockCode}
                  </h2>
                  {/* 價格和漲跌幅 */}
                  {meta.currentPrice != null && (
                    <div className="flex items-baseline gap-2">
                      <span className={`text-xl font-bold font-mono ${getPriceChangeColor(meta.changePct)}`}>
                        {meta.currentPrice.toFixed(2)}
                      </span>
                      <span className={`text-sm font-semibold font-mono ${getPriceChangeColor(meta.changePct)}`}>
                        {formatChangePct(meta.changePct)}
                      </span>
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2 mt-1.5">
                  <span className="font-mono text-xs text-cyan bg-cyan/10 px-2 py-0.5 rounded-full">
                    {meta.stockCode}
                  </span>
                  <span className="text-xs text-muted-text flex items-center gap-1">
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                    {formatDateTime(meta.createdAt)}
                  </span>
                </div>
              </div>
            </div>

            {/* 關鍵結論 */}
            <div className="border-t border-white/5 pt-5">
              <span className="label-uppercase">KEY INSIGHTS</span>
              <p className="mt-2 whitespace-pre-wrap text-left text-[15px] leading-7 text-white max-w-[62ch]">
                {summary.analysisSummary || '暫無分析結論'}
              </p>
            </div>
          </Card>

          {/* 操作建議和趨勢預測 */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* 操作建議 */}
            <Card variant="bordered" padding="sm" hoverable>
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-lg bg-success/10 flex items-center justify-center flex-shrink-0">
                  <svg className="w-4 h-4 text-success" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
                  </svg>
                </div>
                <div className="space-y-1.5">
                  <h4 className="text-[11px] font-medium uppercase tracking-[0.16em] text-success">操作建議</h4>
                  <p className="text-sm leading-6 text-white">
                    {summary.operationAdvice || '暫無建議'}
                  </p>
                </div>
              </div>
            </Card>

            {/* 趨勢預測 */}
            <Card variant="bordered" padding="sm" hoverable>
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-lg bg-warning/10 flex items-center justify-center flex-shrink-0">
                  <svg className="w-4 h-4 text-warning" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                  </svg>
                </div>
                <div className="space-y-1.5">
                  <h4 className="text-[11px] font-medium uppercase tracking-[0.16em] text-warning">趨勢預測</h4>
                  <p className="text-sm leading-6 text-white">
                    {summary.trendPrediction || '暫無預測'}
                  </p>
                </div>
              </div>
            </Card>
          </div>
        </div>

        {/* 右側：情緒指標 - 填滿格子高度，消除與 STRATEGY POINTS 之間的空隙 */}
        <div className="flex flex-col self-stretch min-h-full">
          <Card variant="bordered" padding="md" className="!overflow-visible flex-1 flex flex-col min-h-0">
            <div className="text-center flex-1 flex flex-col justify-center">
              <h3 className="mb-5 text-sm font-medium tracking-wide text-white">Market Sentiment</h3>
              <ScoreGauge score={summary.sentimentScore} size="lg" />
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
};
