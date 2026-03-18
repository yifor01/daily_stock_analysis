import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { IntelligentImport } from '../IntelligentImport';
import { SystemConfigConflictError } from '../../../api/systemConfig';

const { parseImport, update, onMerged } = vi.hoisted(() => ({
  parseImport: vi.fn(),
  update: vi.fn(),
  onMerged: vi.fn(),
}));

vi.mock('../../../api/stocks', () => ({
  stocksApi: {
    parseImport,
    extractFromImage: vi.fn(),
  },
}));

vi.mock('../../../api/systemConfig', async () => {
  const actual = await vi.importActual<typeof import('../../../api/systemConfig')>('../../../api/systemConfig');
  return {
    ...actual,
    systemConfigApi: {
      ...actual.systemConfigApi,
      update,
    },
  };
});

describe('IntelligentImport', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('refreshes config state after a config version conflict', async () => {
    parseImport.mockResolvedValue({
      items: [{ code: 'SZ000001', name: 'Ping An Bank', confidence: 'high' }],
      codes: [],
    });
    update.mockRejectedValue(
      new SystemConfigConflictError('配置版本衝突', 'v2'),
    );

    render(
      <IntelligentImport
        stockListValue="SH600000"
        configVersion="v1"
        maskToken="******"
        onMerged={onMerged}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText('或貼上 CSV/Excel 複製的文字...'), {
      target: { value: '000001' },
    });
    fireEvent.click(screen.getByRole('button', { name: '解析' }));

    await screen.findByText('SZ000001');

    fireEvent.click(screen.getByRole('button', { name: '合併到自選股' }));

    await waitFor(() => {
      expect(update).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(onMerged).toHaveBeenCalledWith('SH600000,SZ000001');
    });
    expect(await screen.findByText('配置已更新，請再次點選「合併到自選股」')).toBeInTheDocument();
  });
});
