import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { HistoryList } from '../HistoryList';
import type { HistoryItem } from '../../../types/analysis';

const baseProps = {
  isLoading: false,
  isLoadingMore: false,
  hasMore: false,
  selectedIds: new Set<number>(),
  onItemClick: vi.fn(),
  onLoadMore: vi.fn(),
  onToggleItemSelection: vi.fn(),
  onToggleSelectAll: vi.fn(),
  onDeleteSelected: vi.fn(),
};

const items: HistoryItem[] = [
  {
    id: 1,
    queryId: 'q-1',
    stockCode: '600519',
    stockName: '貴州茅臺',
    sentimentScore: 82,
    operationAdvice: '買入',
    createdAt: '2026-03-15T08:00:00Z',
  },
];

describe('HistoryList', () => {
  it('shows the empty state copy when no history exists', () => {
    render(<HistoryList {...baseProps} items={[]} />);

    expect(screen.getByText('暫無歷史分析記錄')).toBeInTheDocument();
    expect(screen.getByText('完成首次分析後，這裡會保留最近結果。')).toBeInTheDocument();
  });

  it('renders selected count and forwards item interactions', () => {
    const onItemClick = vi.fn();
    const onToggleItemSelection = vi.fn();

    render(
      <HistoryList
        {...baseProps}
        items={items}
        selectedIds={new Set([1])}
        selectedId={1}
        onItemClick={onItemClick}
        onToggleItemSelection={onToggleItemSelection}
      />,
    );

    expect(screen.getByText('已選 1')).toBeInTheDocument();
    expect(screen.getByText('買入 82')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /貴州茅臺/i }));
    expect(onItemClick).toHaveBeenCalledWith(1);

    fireEvent.click(screen.getAllByRole('checkbox')[1]);
    expect(onToggleItemSelection).toHaveBeenCalledWith(1);
  });
});
