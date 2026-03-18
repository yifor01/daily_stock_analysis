import type React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Pie, PieChart, ResponsiveContainer, Tooltip, Legend, Cell } from 'recharts';
import { portfolioApi } from '../api/portfolio';
import type { ParsedApiError } from '../api/error';
import { getParsedApiError } from '../api/error';
import { ApiErrorAlert, Card, Badge, ConfirmDialog } from '../components/common';
import { toDateInputValue } from '../utils/format';
import type {
  PortfolioAccountItem,
  PortfolioCashDirection,
  PortfolioCashLedgerListItem,
  PortfolioCorporateActionListItem,
  PortfolioCorporateActionType,
  PortfolioCostMethod,
  PortfolioImportBrokerItem,
  PortfolioImportCommitResponse,
  PortfolioImportParseResponse,
  PortfolioPositionItem,
  PortfolioRiskResponse,
  PortfolioSide,
  PortfolioSnapshotResponse,
  PortfolioTradeListItem,
} from '../types/portfolio';

const PIE_COLORS = ['#00d4ff', '#00ff88', '#ffaa00', '#ff7a45', '#7f8cff', '#ff4466'];
const DEFAULT_PAGE_SIZE = 20;
const FALLBACK_BROKERS: PortfolioImportBrokerItem[] = [
  { broker: 'huatai', aliases: [], displayName: '華泰' },
  { broker: 'citic', aliases: ['zhongxin'], displayName: '中信' },
  { broker: 'cmb', aliases: ['cmbchina', 'zhaoshang'], displayName: '招商' },
];

type AccountOption = 'all' | number;
type EventType = 'trade' | 'cash' | 'corporate';

type FlatPosition = PortfolioPositionItem & {
  accountId: number;
  accountName: string;
};

type PendingDelete =
  | { eventType: 'trade'; id: number; message: string }
  | { eventType: 'cash'; id: number; message: string }
  | { eventType: 'corporate'; id: number; message: string };

function getTodayIso(): string {
  return toDateInputValue(new Date());
}

function formatMoney(value: number | undefined | null, currency = 'CNY'): string {
  if (value == null || Number.isNaN(value)) return '--';
  return `${currency} ${Number(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function formatPct(value: number | undefined | null): string {
  if (value == null || Number.isNaN(value)) return '--';
  return `${value.toFixed(2)}%`;
}

function formatSideLabel(value: PortfolioSide): string {
  return value === 'buy' ? '買入' : '賣出';
}

function formatCashDirectionLabel(value: PortfolioCashDirection): string {
  return value === 'in' ? '流入' : '流出';
}

function formatCorporateActionLabel(value: PortfolioCorporateActionType): string {
  return value === 'cash_dividend' ? '現金分紅' : '拆並股調整';
}

function formatBrokerLabel(value: string, displayName?: string): string {
  if (displayName && displayName.trim()) return `${value}（${displayName.trim()}）`;
  if (value === 'huatai') return 'huatai（華泰）';
  if (value === 'citic') return 'citic（中信）';
  if (value === 'cmb') return 'cmb（招商）';
  return value;
}

const PortfolioPage: React.FC = () => {
  // Set page title
  useEffect(() => {
    document.title = '持倉分析 - DSA';
  }, []);

  const [accounts, setAccounts] = useState<PortfolioAccountItem[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<AccountOption>('all');
  const [showCreateAccount, setShowCreateAccount] = useState(false);
  const [accountCreating, setAccountCreating] = useState(false);
  const [accountCreateError, setAccountCreateError] = useState<string | null>(null);
  const [accountCreateSuccess, setAccountCreateSuccess] = useState<string | null>(null);
  const [accountForm, setAccountForm] = useState({
    name: '',
    broker: 'Demo',
    market: 'cn' as 'cn' | 'hk' | 'us',
    baseCurrency: 'CNY',
  });
  const [costMethod, setCostMethod] = useState<PortfolioCostMethod>('fifo');
  const [snapshot, setSnapshot] = useState<PortfolioSnapshotResponse | null>(null);
  const [risk, setRisk] = useState<PortfolioRiskResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [riskWarning, setRiskWarning] = useState<string | null>(null);
  const [writeWarning, setWriteWarning] = useState<string | null>(null);

  const [brokers, setBrokers] = useState<PortfolioImportBrokerItem[]>([]);
  const [selectedBroker, setSelectedBroker] = useState('huatai');
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvDryRun, setCsvDryRun] = useState(true);
  const [csvParsing, setCsvParsing] = useState(false);
  const [csvCommitting, setCsvCommitting] = useState(false);
  const [csvParseResult, setCsvParseResult] = useState<PortfolioImportParseResponse | null>(null);
  const [csvCommitResult, setCsvCommitResult] = useState<PortfolioImportCommitResponse | null>(null);
  const [brokerLoadWarning, setBrokerLoadWarning] = useState<string | null>(null);

  const [eventType, setEventType] = useState<EventType>('trade');
  const [eventDateFrom, setEventDateFrom] = useState('');
  const [eventDateTo, setEventDateTo] = useState('');
  const [eventSymbol, setEventSymbol] = useState('');
  const [eventSide, setEventSide] = useState<'' | PortfolioSide>('');
  const [eventDirection, setEventDirection] = useState<'' | PortfolioCashDirection>('');
  const [eventActionType, setEventActionType] = useState<'' | PortfolioCorporateActionType>('');
  const [eventPage, setEventPage] = useState(1);
  const [eventTotal, setEventTotal] = useState(0);
  const [eventLoading, setEventLoading] = useState(false);
  const [tradeEvents, setTradeEvents] = useState<PortfolioTradeListItem[]>([]);
  const [cashEvents, setCashEvents] = useState<PortfolioCashLedgerListItem[]>([]);
  const [corporateEvents, setCorporateEvents] = useState<PortfolioCorporateActionListItem[]>([]);
  const [pendingDelete, setPendingDelete] = useState<PendingDelete | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const [tradeForm, setTradeForm] = useState({
    symbol: '',
    tradeDate: getTodayIso(),
    side: 'buy' as PortfolioSide,
    quantity: '',
    price: '',
    fee: '',
    tax: '',
    tradeUid: '',
    note: '',
  });
  const [cashForm, setCashForm] = useState({
    eventDate: getTodayIso(),
    direction: 'in' as PortfolioCashDirection,
    amount: '',
    currency: '',
    note: '',
  });
  const [corpForm, setCorpForm] = useState({
    symbol: '',
    effectiveDate: getTodayIso(),
    actionType: 'cash_dividend' as PortfolioCorporateActionType,
    cashDividendPerShare: '',
    splitRatio: '',
    note: '',
  });

  const queryAccountId = selectedAccount === 'all' ? undefined : selectedAccount;
  const hasAccounts = accounts.length > 0;
  const writableAccount = selectedAccount === 'all' ? undefined : accounts.find((item) => item.id === selectedAccount);
  const writableAccountId = writableAccount?.id;
  const writeBlocked = !writableAccountId;
  const totalEventPages = Math.max(1, Math.ceil(eventTotal / DEFAULT_PAGE_SIZE));
  const currentEventCount = eventType === 'trade'
    ? tradeEvents.length
    : eventType === 'cash'
      ? cashEvents.length
      : corporateEvents.length;

  const loadAccounts = useCallback(async () => {
    try {
      const response = await portfolioApi.getAccounts(false);
      const items = response.accounts || [];
      setAccounts(items);
      setSelectedAccount((prev) => {
        if (items.length === 0) return 'all';
        if (prev !== 'all' && !items.some((item) => item.id === prev)) return items[0].id;
        return prev;
      });
      if (items.length === 0) setShowCreateAccount(true);
    } catch (err) {
      setError(getParsedApiError(err));
    }
  }, []);

  const loadBrokers = useCallback(async () => {
    try {
      const response = await portfolioApi.listImportBrokers();
      const brokerItems = response.brokers || [];
      if (brokerItems.length === 0) {
        setBrokers(FALLBACK_BROKERS);
        setBrokerLoadWarning('券商列表介面返回為空，已回退為內建券商列表（華泰/中信/招商）。');
        if (!FALLBACK_BROKERS.some((item) => item.broker === selectedBroker)) {
          setSelectedBroker(FALLBACK_BROKERS[0].broker);
        }
        return;
      }
      setBrokers(brokerItems);
      setBrokerLoadWarning(null);
      if (!brokerItems.some((item) => item.broker === selectedBroker)) {
        setSelectedBroker(brokerItems[0].broker);
      }
    } catch {
      setBrokers(FALLBACK_BROKERS);
      setBrokerLoadWarning('券商列表介面不可用，已回退為內建券商列表（華泰/中信/招商）。');
      if (!FALLBACK_BROKERS.some((item) => item.broker === selectedBroker)) {
        setSelectedBroker(FALLBACK_BROKERS[0].broker);
      }
    }
  }, [selectedBroker]);

  const loadSnapshotAndRisk = useCallback(async () => {
    setIsLoading(true);
    setRiskWarning(null);
    try {
      const snapshotData = await portfolioApi.getSnapshot({
        accountId: queryAccountId,
        costMethod,
      });
      setSnapshot(snapshotData);
      setError(null);

      try {
        const riskData = await portfolioApi.getRisk({
          accountId: queryAccountId,
          costMethod,
        });
        setRisk(riskData);
      } catch (riskErr) {
        setRisk(null);
        const parsed = getParsedApiError(riskErr);
        setRiskWarning(parsed.message || '風險資料獲取失敗，已降級為僅展示快照資料。');
      }
    } catch (err) {
      setSnapshot(null);
      setRisk(null);
      setError(getParsedApiError(err));
    } finally {
      setIsLoading(false);
    }
  }, [queryAccountId, costMethod]);

  const loadEventsPage = useCallback(async (page: number) => {
    setEventLoading(true);
    try {
      if (eventType === 'trade') {
        const response = await portfolioApi.listTrades({
          accountId: queryAccountId,
          dateFrom: eventDateFrom || undefined,
          dateTo: eventDateTo || undefined,
          symbol: eventSymbol || undefined,
          side: eventSide || undefined,
          page,
          pageSize: DEFAULT_PAGE_SIZE,
        });
        setTradeEvents(response.items || []);
        setEventTotal(response.total || 0);
      } else if (eventType === 'cash') {
        const response = await portfolioApi.listCashLedger({
          accountId: queryAccountId,
          dateFrom: eventDateFrom || undefined,
          dateTo: eventDateTo || undefined,
          direction: eventDirection || undefined,
          page,
          pageSize: DEFAULT_PAGE_SIZE,
        });
        setCashEvents(response.items || []);
        setEventTotal(response.total || 0);
      } else {
        const response = await portfolioApi.listCorporateActions({
          accountId: queryAccountId,
          dateFrom: eventDateFrom || undefined,
          dateTo: eventDateTo || undefined,
          symbol: eventSymbol || undefined,
          actionType: eventActionType || undefined,
          page,
          pageSize: DEFAULT_PAGE_SIZE,
        });
        setCorporateEvents(response.items || []);
        setEventTotal(response.total || 0);
      }
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setEventLoading(false);
    }
  }, [
    eventActionType,
    eventDateFrom,
    eventDateTo,
    eventDirection,
    eventSide,
    eventSymbol,
    eventType,
    queryAccountId,
  ]);

  const loadEvents = useCallback(async () => {
    await loadEventsPage(eventPage);
  }, [eventPage, loadEventsPage]);

  const refreshPortfolioData = useCallback(async (page = eventPage) => {
    await Promise.all([loadSnapshotAndRisk(), loadEventsPage(page)]);
  }, [eventPage, loadEventsPage, loadSnapshotAndRisk]);

  useEffect(() => {
    void loadAccounts();
    void loadBrokers();
  }, [loadAccounts, loadBrokers]);

  useEffect(() => {
    void loadSnapshotAndRisk();
  }, [loadSnapshotAndRisk]);

  useEffect(() => {
    void loadEvents();
  }, [loadEvents]);

  useEffect(() => {
    setEventPage(1);
  }, [eventType, queryAccountId, eventDateFrom, eventDateTo, eventSymbol, eventSide, eventDirection, eventActionType]);

  useEffect(() => {
    if (!writeBlocked) {
      setWriteWarning(null);
    }
  }, [writeBlocked]);

  const positionRows: FlatPosition[] = useMemo(() => {
    if (!snapshot) return [];
    const rows: FlatPosition[] = [];
    for (const account of snapshot.accounts || []) {
      for (const position of account.positions || []) {
        rows.push({
          ...position,
          accountId: account.accountId,
          accountName: account.accountName,
        });
      }
    }
    rows.sort((a, b) => Number(b.marketValueBase || 0) - Number(a.marketValueBase || 0));
    return rows;
  }, [snapshot]);

  const sectorPieData = useMemo(() => {
    const sectors = risk?.sectorConcentration?.topSectors || [];
    return sectors
      .slice(0, 6)
      .map((item) => ({
        name: item.sector,
        value: Number(item.weightPct || 0),
      }))
      .filter((item) => item.value > 0);
  }, [risk]);

  const positionFallbackPieData = useMemo(() => {
    if (!risk?.concentration?.topPositions?.length) {
      return [];
    }
    return risk.concentration.topPositions
      .slice(0, 6)
      .map((item) => ({
        name: item.symbol,
        value: Number(item.weightPct || 0),
      }))
      .filter((item) => item.value > 0);
  }, [risk]);

  const concentrationPieData = sectorPieData.length > 0 ? sectorPieData : positionFallbackPieData;
  const concentrationMode = sectorPieData.length > 0 ? 'sector' : 'position';

  const handleTradeSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!writableAccountId) {
      setWriteWarning('請先在右上角選擇具體賬戶，再進行錄入或匯入提交。');
      return;
    }
    try {
      setWriteWarning(null);
      await portfolioApi.createTrade({
        accountId: writableAccountId,
        symbol: tradeForm.symbol,
        tradeDate: tradeForm.tradeDate,
        side: tradeForm.side,
        quantity: Number(tradeForm.quantity),
        price: Number(tradeForm.price),
        fee: Number(tradeForm.fee || 0),
        tax: Number(tradeForm.tax || 0),
        tradeUid: tradeForm.tradeUid || undefined,
        note: tradeForm.note || undefined,
      });
      await refreshPortfolioData();
      setTradeForm((prev) => ({ ...prev, symbol: '', tradeUid: '', note: '' }));
    } catch (err) {
      setError(getParsedApiError(err));
    }
  };

  const handleCashSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!writableAccountId) {
      setWriteWarning('請先在右上角選擇具體賬戶，再進行錄入或匯入提交。');
      return;
    }
    try {
      setWriteWarning(null);
      await portfolioApi.createCashLedger({
        accountId: writableAccountId,
        eventDate: cashForm.eventDate,
        direction: cashForm.direction,
        amount: Number(cashForm.amount),
        currency: cashForm.currency || undefined,
        note: cashForm.note || undefined,
      });
      await refreshPortfolioData();
      setCashForm((prev) => ({ ...prev, note: '' }));
    } catch (err) {
      setError(getParsedApiError(err));
    }
  };

  const handleCorporateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!writableAccountId) {
      setWriteWarning('請先在右上角選擇具體賬戶，再進行錄入或匯入提交。');
      return;
    }
    try {
      setWriteWarning(null);
      await portfolioApi.createCorporateAction({
        accountId: writableAccountId,
        symbol: corpForm.symbol,
        effectiveDate: corpForm.effectiveDate,
        actionType: corpForm.actionType,
        cashDividendPerShare: corpForm.cashDividendPerShare ? Number(corpForm.cashDividendPerShare) : undefined,
        splitRatio: corpForm.splitRatio ? Number(corpForm.splitRatio) : undefined,
        note: corpForm.note || undefined,
      });
      await refreshPortfolioData();
      setCorpForm((prev) => ({ ...prev, symbol: '', note: '' }));
    } catch (err) {
      setError(getParsedApiError(err));
    }
  };

  const handleParseCsv = async () => {
    if (!csvFile) return;
    try {
      setCsvParsing(true);
      const parsed = await portfolioApi.parseCsvImport(selectedBroker, csvFile);
      setCsvParseResult(parsed);
      setCsvCommitResult(null);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setCsvParsing(false);
    }
  };

  const handleCommitCsv = async () => {
    if (!csvFile) return;
    if (!writableAccountId) {
      setWriteWarning('請先在右上角選擇具體賬戶，再進行錄入或匯入提交。');
      return;
    }
    try {
      setWriteWarning(null);
      setCsvCommitting(true);
      const committed = await portfolioApi.commitCsvImport(writableAccountId, selectedBroker, csvFile, csvDryRun);
      setCsvCommitResult(committed);
      if (!csvDryRun) {
        await refreshPortfolioData();
      }
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setCsvCommitting(false);
    }
  };

  const openDeleteDialog = (item: PendingDelete) => {
    if (!writableAccountId) {
      setWriteWarning('請先在右上角選擇具體賬戶，再進行刪除修正。');
      return;
    }
    setPendingDelete(item);
  };

  const handleConfirmDelete = async () => {
    if (!pendingDelete || deleteLoading) return;
    if (!writableAccountId) {
      setWriteWarning('請先在右上角選擇具體賬戶，再進行刪除修正。');
      setPendingDelete(null);
      return;
    }

    const nextPage = currentEventCount === 1 && eventPage > 1 ? eventPage - 1 : eventPage;
    try {
      setDeleteLoading(true);
      setWriteWarning(null);
      if (pendingDelete.eventType === 'trade') {
        await portfolioApi.deleteTrade(pendingDelete.id);
      } else if (pendingDelete.eventType === 'cash') {
        await portfolioApi.deleteCashLedger(pendingDelete.id);
      } else {
        await portfolioApi.deleteCorporateAction(pendingDelete.id);
      }
      setPendingDelete(null);
      if (nextPage !== eventPage) {
        setEventPage(nextPage);
      }
      await refreshPortfolioData(nextPage);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setDeleteLoading(false);
    }
  };

  const handleCreateAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = accountForm.name.trim();
    if (!name) {
      setAccountCreateError('賬戶名稱不能為空。');
      setAccountCreateSuccess(null);
      return;
    }
    try {
      setAccountCreating(true);
      setAccountCreateError(null);
      setAccountCreateSuccess(null);
      const created = await portfolioApi.createAccount({
        name,
        broker: accountForm.broker.trim() || undefined,
        market: accountForm.market,
        baseCurrency: accountForm.baseCurrency.trim() || 'CNY',
      });
      await loadAccounts();
      setSelectedAccount(created.id);
      setShowCreateAccount(false);
      setWriteWarning(null);
      setAccountForm({
        name: '',
        broker: 'Demo',
        market: accountForm.market,
        baseCurrency: accountForm.baseCurrency,
      });
      setAccountCreateSuccess('賬戶建立成功，已自動切換到該賬戶。');
    } catch (err) {
      const parsed = getParsedApiError(err);
      setAccountCreateError(parsed.message || '建立賬戶失敗，請稍後重試。');
      setAccountCreateSuccess(null);
    } finally {
      setAccountCreating(false);
    }
  };

  const handleRefresh = async () => {
    await Promise.all([loadAccounts(), loadSnapshotAndRisk(), loadEvents(), loadBrokers()]);
  };

  return (
    <div className="min-h-screen p-4 md:p-6 space-y-4">
      <section className="space-y-3">
        <div className="space-y-2">
          <h1 className="text-xl md:text-2xl font-semibold text-white">持倉管理</h1>
          <p className="text-xs md:text-sm text-secondary">
            組合快照、手工錄入、CSV 匯入與風險分析（支援全組合 / 單賬戶切換）
          </p>
        </div>
        {hasAccounts ? (
          <div className="rounded-xl border border-white/10 bg-white/[0.02] p-3">
            <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_220px_280px] gap-2 items-end">
              <div>
                <p className="text-xs text-secondary mb-1">賬戶檢視</p>
                <select
                  value={String(selectedAccount)}
                  onChange={(e) => setSelectedAccount(e.target.value === 'all' ? 'all' : Number(e.target.value))}
                  className="input-terminal text-sm w-full"
                >
                  <option value="all">全部賬戶</option>
                  {accounts.map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.name} (#{account.id})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <p className="text-xs text-secondary mb-1">成本口徑</p>
                <select
                  value={costMethod}
                  onChange={(e) => setCostMethod(e.target.value as PortfolioCostMethod)}
                  className="input-terminal text-sm w-full"
                >
                  <option value="fifo">先進先出（FIFO）</option>
                  <option value="avg">均價成本（AVG）</option>
                </select>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  className="btn-secondary text-sm flex-1"
                  onClick={() => {
                    setShowCreateAccount((prev) => !prev);
                    setAccountCreateError(null);
                    setAccountCreateSuccess(null);
                  }}
                >
                  {showCreateAccount ? '收起新建' : '新建賬戶'}
                </button>
                <button type="button" onClick={() => void handleRefresh()} disabled={isLoading} className="btn-secondary text-sm flex-1">
                  {isLoading ? '重新整理中...' : '重新整理資料'}
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="text-xs text-amber-300 rounded-lg border border-amber-400/30 bg-amber-400/10 px-3 py-2 inline-block">
            還沒有可用賬戶，請先建立賬戶後再錄入交易或匯入 CSV。
          </div>
        )}
      </section>

      {error ? <ApiErrorAlert error={error} onDismiss={() => setError(null)} /> : null}
      {riskWarning ? (
        <div className="rounded-xl border border-amber-500/35 bg-amber-500/10 px-4 py-3 text-amber-100 text-sm">
          風險模組降級：{riskWarning}
        </div>
      ) : null}
      {writeWarning ? (
        <div className="rounded-xl border border-amber-500/35 bg-amber-500/10 px-4 py-3 text-amber-100 text-sm">
          操作提示：{writeWarning}
        </div>
      ) : null}

      {(showCreateAccount || !hasAccounts) ? (
        <Card padding="md">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-white">新建賬戶</h2>
            {hasAccounts ? (
              <button
                type="button"
                className="btn-secondary text-xs px-3 py-1"
                onClick={() => {
                  setShowCreateAccount(false);
                  setAccountCreateError(null);
                  setAccountCreateSuccess(null);
                }}
              >
                收起
              </button>
            ) : (
              <span className="text-xs text-secondary">建立後自動切換到該賬戶</span>
            )}
          </div>
          {accountCreateError ? (
            <div className="mt-2 text-xs text-red-300 rounded-lg border border-red-400/30 bg-red-400/10 px-2 py-1">
              {accountCreateError}
            </div>
          ) : null}
          {accountCreateSuccess ? (
            <div className="mt-2 text-xs text-emerald-300 rounded-lg border border-emerald-400/30 bg-emerald-400/10 px-2 py-1">
              {accountCreateSuccess}
            </div>
          ) : null}
          <form className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2" onSubmit={handleCreateAccount}>
            <input
              className="input-terminal text-sm md:col-span-2"
              placeholder="賬戶名稱（必填）"
              value={accountForm.name}
              onChange={(e) => setAccountForm((prev) => ({ ...prev, name: e.target.value }))}
            />
            <input
              className="input-terminal text-sm"
              placeholder="券商（可選，如 Demo/華泰）"
              value={accountForm.broker}
              onChange={(e) => setAccountForm((prev) => ({ ...prev, broker: e.target.value }))}
            />
            <input
              className="input-terminal text-sm"
              placeholder="基準幣（如 CNY/USD/HKD）"
              value={accountForm.baseCurrency}
              onChange={(e) => setAccountForm((prev) => ({ ...prev, baseCurrency: e.target.value.toUpperCase() }))}
            />
            <select
              className="input-terminal text-sm"
              value={accountForm.market}
              onChange={(e) => setAccountForm((prev) => ({ ...prev, market: e.target.value as 'cn' | 'hk' | 'us' }))}
            >
              <option value="cn">市場：A 股（cn）</option>
              <option value="hk">市場：港股（hk）</option>
              <option value="us">市場：美股（us）</option>
            </select>
            <button type="submit" className="btn-secondary text-sm" disabled={accountCreating}>
              {accountCreating ? '建立中...' : '建立賬戶'}
            </button>
          </form>
        </Card>
      ) : null}

      <section className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
        <Card variant="gradient" padding="md">
          <p className="text-xs text-secondary">總權益</p>
          <p className="mt-1 text-xl font-semibold text-white">{formatMoney(snapshot?.totalEquity, snapshot?.currency || 'CNY')}</p>
        </Card>
        <Card variant="gradient" padding="md">
          <p className="text-xs text-secondary">總市值</p>
          <p className="mt-1 text-xl font-semibold text-white">{formatMoney(snapshot?.totalMarketValue, snapshot?.currency || 'CNY')}</p>
        </Card>
        <Card variant="gradient" padding="md">
          <p className="text-xs text-secondary">總現金</p>
          <p className="mt-1 text-xl font-semibold text-white">{formatMoney(snapshot?.totalCash, snapshot?.currency || 'CNY')}</p>
        </Card>
        <Card variant="gradient" padding="md">
          <p className="text-xs text-secondary">匯率狀態</p>
          <div className="mt-2">{snapshot?.fxStale ? <Badge variant="warning">過期</Badge> : <Badge variant="success">最新</Badge>}</div>
        </Card>
      </section>

      <section className="grid grid-cols-1 xl:grid-cols-3 gap-3">
        <Card className="xl:col-span-2" padding="md">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-white">持倉明細</h2>
            <span className="text-xs text-secondary">共 {positionRows.length} 項</span>
          </div>
          {positionRows.length === 0 ? (
            <p className="text-sm text-muted py-6 text-center">當前無持倉資料</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs text-secondary border-b border-white/10">
                  <tr>
                    <th className="text-left py-2 pr-2">賬戶</th>
                    <th className="text-left py-2 pr-2">程式碼</th>
                    <th className="text-right py-2 pr-2">數量</th>
                    <th className="text-right py-2 pr-2">均價</th>
                    <th className="text-right py-2 pr-2">現價</th>
                    <th className="text-right py-2 pr-2">市值</th>
                    <th className="text-right py-2">未實現盈虧</th>
                  </tr>
                </thead>
                <tbody>
                  {positionRows.map((row) => (
                    <tr key={`${row.accountId}-${row.symbol}-${row.market}`} className="border-b border-white/5">
                      <td className="py-2 pr-2 text-secondary">{row.accountName}</td>
                      <td className="py-2 pr-2 font-mono text-white">{row.symbol}</td>
                      <td className="py-2 pr-2 text-right">{row.quantity.toFixed(2)}</td>
                      <td className="py-2 pr-2 text-right">{row.avgCost.toFixed(4)}</td>
                      <td className="py-2 pr-2 text-right">{row.lastPrice.toFixed(4)}</td>
                      <td className="py-2 pr-2 text-right">{formatMoney(row.marketValueBase, row.valuationCurrency)}</td>
                      <td className={`py-2 text-right ${row.unrealizedPnlBase >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {formatMoney(row.unrealizedPnlBase, row.valuationCurrency)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card padding="md">
          <h2 className="text-sm font-semibold text-white mb-3">{concentrationMode === 'sector' ? '行業集中度分佈' : '行業資料暫不可用，當前展示個股集中度'}</h2>
          {concentrationPieData.length > 0 ? (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={concentrationPieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90}>
                    {concentrationPieData.map((entry, index) => (
                      <Cell key={`cell-${entry.name}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => `${Number(value).toFixed(2)}%`} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="text-sm text-muted py-8 text-center">暫無集中度資料</p>
          )}
          <div className="mt-3 text-xs text-secondary space-y-1">
            <div>展示口徑: {concentrationMode === 'sector' ? '行業維度' : '個股維度（降級顯示）'}</div>
            <div>板塊集中度告警: {risk?.sectorConcentration?.alert ? '是' : '否'}</div>
            <div>Top1 權重: {formatPct(risk?.sectorConcentration?.topWeightPct ?? risk?.concentration?.topWeightPct)}</div>
          </div>
        </Card>
      </section>

      {writeBlocked && hasAccounts ? (
        <div className="text-xs text-amber-300 rounded-lg border border-amber-400/30 bg-amber-400/10 px-3 py-2">
          當前處於“全部賬戶”檢視。為避免誤寫，請先選擇一個具體賬戶後再進行手工錄入或 CSV 提交。
        </div>
      ) : null}

      <section className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Card padding="md">
          <h3 className="text-sm font-semibold text-white mb-2">回撤監控</h3>
          <div className="text-xs text-secondary space-y-1">
            <div>最大回撤: {formatPct(risk?.drawdown?.maxDrawdownPct)}</div>
            <div>當前回撤: {formatPct(risk?.drawdown?.currentDrawdownPct)}</div>
            <div>告警: {risk?.drawdown?.alert ? '是' : '否'}</div>
          </div>
        </Card>
        <Card padding="md">
          <h3 className="text-sm font-semibold text-white mb-2">止損接近預警</h3>
          <div className="text-xs text-secondary space-y-1">
            <div>觸發數: {risk?.stopLoss?.triggeredCount ?? 0}</div>
            <div>接近數: {risk?.stopLoss?.nearCount ?? 0}</div>
            <div>告警: {risk?.stopLoss?.nearAlert ? '是' : '否'}</div>
          </div>
        </Card>
        <Card padding="md">
          <h3 className="text-sm font-semibold text-white mb-2">口徑</h3>
          <div className="text-xs text-secondary space-y-1">
            <div>賬戶數: {snapshot?.accountCount ?? 0}</div>
            <div>計價幣種: {snapshot?.currency || 'CNY'}</div>
            <div>成本法: {(snapshot?.costMethod || costMethod).toUpperCase()}</div>
          </div>
        </Card>
      </section>

      <section className="grid grid-cols-1 xl:grid-cols-3 gap-3">
        <Card padding="md">
          <h3 className="text-sm font-semibold text-white mb-3">手工錄入：交易</h3>
          <form className="space-y-2" onSubmit={handleTradeSubmit}>
            <input className="input-terminal w-full text-sm" placeholder="股票程式碼（例如 600519）" value={tradeForm.symbol}
              onChange={(e) => setTradeForm((prev) => ({ ...prev, symbol: e.target.value }))} required />
            <div className="grid grid-cols-2 gap-2">
              <input className="input-terminal text-sm" type="date" value={tradeForm.tradeDate}
                onChange={(e) => setTradeForm((prev) => ({ ...prev, tradeDate: e.target.value }))} required />
              <select className="input-terminal text-sm" value={tradeForm.side}
                onChange={(e) => setTradeForm((prev) => ({ ...prev, side: e.target.value as PortfolioSide }))}>
                <option value="buy">買入</option>
                <option value="sell">賣出</option>
              </select>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <input className="input-terminal text-sm" type="number" min="0" step="0.0001" placeholder="數量（必填）" value={tradeForm.quantity}
                onChange={(e) => setTradeForm((prev) => ({ ...prev, quantity: e.target.value }))} required />
              <input className="input-terminal text-sm" type="number" min="0" step="0.0001" placeholder="成交價（必填）" value={tradeForm.price}
                onChange={(e) => setTradeForm((prev) => ({ ...prev, price: e.target.value }))} required />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <input className="input-terminal text-sm" type="number" min="0" step="0.0001" placeholder="手續費（可選）" value={tradeForm.fee}
                onChange={(e) => setTradeForm((prev) => ({ ...prev, fee: e.target.value }))} />
              <input className="input-terminal text-sm" type="number" min="0" step="0.0001" placeholder="稅費（可選）" value={tradeForm.tax}
                onChange={(e) => setTradeForm((prev) => ({ ...prev, tax: e.target.value }))} />
            </div>
            <p className="text-xs text-secondary">手續費和稅費可留空，系統將按 0 處理。</p>
            <button type="submit" className="btn-secondary w-full" disabled={!writableAccountId}>提交交易</button>
          </form>
        </Card>

        <Card padding="md">
          <h3 className="text-sm font-semibold text-white mb-3">手工錄入：資金流水</h3>
          <form className="space-y-2" onSubmit={handleCashSubmit}>
            <div className="grid grid-cols-2 gap-2">
              <input className="input-terminal text-sm" type="date" value={cashForm.eventDate}
                onChange={(e) => setCashForm((prev) => ({ ...prev, eventDate: e.target.value }))} required />
              <select className="input-terminal text-sm" value={cashForm.direction}
                onChange={(e) => setCashForm((prev) => ({ ...prev, direction: e.target.value as PortfolioCashDirection }))}>
                <option value="in">流入</option>
                <option value="out">流出</option>
              </select>
            </div>
            <input className="input-terminal w-full text-sm" type="number" min="0" step="0.0001" placeholder="金額"
              value={cashForm.amount} onChange={(e) => setCashForm((prev) => ({ ...prev, amount: e.target.value }))} required />
            <input className="input-terminal w-full text-sm" placeholder={`幣種（可選，預設 ${writableAccount?.baseCurrency || '賬戶基準幣'}）`} value={cashForm.currency}
              onChange={(e) => setCashForm((prev) => ({ ...prev, currency: e.target.value }))} />
            <button type="submit" className="btn-secondary w-full" disabled={!writableAccountId}>提交資金流水</button>
          </form>
        </Card>

        <Card padding="md">
          <h3 className="text-sm font-semibold text-white mb-3">手工錄入：公司行為</h3>
          <form className="space-y-2" onSubmit={handleCorporateSubmit}>
            <input className="input-terminal w-full text-sm" placeholder="股票程式碼" value={corpForm.symbol}
              onChange={(e) => setCorpForm((prev) => ({ ...prev, symbol: e.target.value }))} required />
            <div className="grid grid-cols-2 gap-2">
              <input className="input-terminal text-sm" type="date" value={corpForm.effectiveDate}
                onChange={(e) => setCorpForm((prev) => ({ ...prev, effectiveDate: e.target.value }))} required />
              <select className="input-terminal text-sm" value={corpForm.actionType}
                onChange={(e) => setCorpForm((prev) => ({ ...prev, actionType: e.target.value as PortfolioCorporateActionType }))}>
                <option value="cash_dividend">現金分紅</option>
                <option value="split_adjustment">拆並股調整</option>
              </select>
            </div>
            {corpForm.actionType === 'cash_dividend' ? (
              <input className="input-terminal w-full text-sm" type="number" min="0" step="0.000001" placeholder="每股分紅"
                value={corpForm.cashDividendPerShare}
                onChange={(e) => setCorpForm((prev) => ({ ...prev, cashDividendPerShare: e.target.value, splitRatio: '' }))} required />
            ) : (
              <input className="input-terminal w-full text-sm" type="number" min="0" step="0.000001" placeholder="拆並股比例"
                value={corpForm.splitRatio}
                onChange={(e) => setCorpForm((prev) => ({ ...prev, splitRatio: e.target.value, cashDividendPerShare: '' }))} required />
            )}
            <button type="submit" className="btn-secondary w-full" disabled={!writableAccountId}>提交企業行為</button>
          </form>
        </Card>
      </section>

      <section className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        <Card padding="md">
          <h3 className="text-sm font-semibold text-white mb-3">券商 CSV 匯入</h3>
          <div className="space-y-2">
            {brokerLoadWarning ? (
              <div className="text-xs text-amber-300 rounded-lg border border-amber-400/30 bg-amber-400/10 px-2 py-1">
                {brokerLoadWarning}
              </div>
            ) : null}
            <div className="grid grid-cols-2 gap-2">
              <select className="input-terminal text-sm" value={selectedBroker} onChange={(e) => setSelectedBroker(e.target.value)}>
                {brokers.length > 0 ? (
                  brokers.map((item) => <option key={item.broker} value={item.broker}>{formatBrokerLabel(item.broker, item.displayName)}</option>)
                ) : (
                  <option value="huatai">huatai（華泰）</option>
                )}
              </select>
              <label className="input-terminal text-sm flex items-center justify-center cursor-pointer">
                選擇 CSV
                <input type="file" accept=".csv" className="hidden"
                  onChange={(e) => setCsvFile(e.target.files && e.target.files[0] ? e.target.files[0] : null)} />
              </label>
            </div>
            <div className="flex items-center gap-2 text-xs text-secondary">
              <input id="csv-dry-run" type="checkbox" checked={csvDryRun} onChange={(e) => setCsvDryRun(e.target.checked)} />
              <label htmlFor="csv-dry-run">僅預演（不寫入）</label>
            </div>
            <div className="flex gap-2">
              <button type="button" className="btn-secondary flex-1" disabled={!csvFile || csvParsing} onClick={() => void handleParseCsv()}>
                {csvParsing ? '解析中...' : '解析檔案'}
              </button>
              <button type="button" className="btn-secondary flex-1"
                disabled={!csvFile || !writableAccountId || csvCommitting} onClick={() => void handleCommitCsv()}>
                {csvCommitting ? '提交中...' : '提交匯入'}
              </button>
            </div>
            {csvParseResult ? (
              <div className="text-xs text-secondary rounded-lg border border-white/10 p-2">
                解析結果：有效 {csvParseResult.recordCount} 條，跳過 {csvParseResult.skippedCount} 條，錯誤 {csvParseResult.errorCount} 條
              </div>
            ) : null}
            {csvCommitResult ? (
              <div className="text-xs text-secondary rounded-lg border border-white/10 p-2">
                提交結果：寫入 {csvCommitResult.insertedCount} 條，重複 {csvCommitResult.duplicateCount} 條，失敗 {csvCommitResult.failedCount} 條
              </div>
            ) : null}
          </div>
        </Card>

        <Card padding="md">
          <h3 className="text-sm font-semibold text-white mb-3">事件記錄</h3>
          <div className="space-y-2">
            <div className="grid grid-cols-2 gap-2">
              <select className="input-terminal text-sm" value={eventType} onChange={(e) => setEventType(e.target.value as EventType)}>
                <option value="trade">交易流水</option>
                <option value="cash">資金流水</option>
                <option value="corporate">公司行為</option>
              </select>
              <button type="button" className="btn-secondary text-sm" onClick={() => void loadEvents()} disabled={eventLoading}>
                {eventLoading ? '載入中...' : '重新整理流水'}
              </button>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <input className="input-terminal text-sm" type="date" value={eventDateFrom} onChange={(e) => setEventDateFrom(e.target.value)} />
              <input className="input-terminal text-sm" type="date" value={eventDateTo} onChange={(e) => setEventDateTo(e.target.value)} />
            </div>
            {(eventType === 'trade' || eventType === 'corporate') ? (
              <input className="input-terminal text-sm w-full" placeholder="按股票程式碼篩選" value={eventSymbol}
                onChange={(e) => setEventSymbol(e.target.value)} />
            ) : null}
            {eventType === 'trade' ? (
              <select className="input-terminal text-sm w-full" value={eventSide} onChange={(e) => setEventSide(e.target.value as '' | PortfolioSide)}>
                <option value="">全部買賣方向</option>
                <option value="buy">買入</option>
                <option value="sell">賣出</option>
              </select>
            ) : null}
            {eventType === 'cash' ? (
              <select className="input-terminal text-sm w-full" value={eventDirection}
                onChange={(e) => setEventDirection(e.target.value as '' | PortfolioCashDirection)}>
                <option value="">全部資金方向</option>
                <option value="in">流入</option>
                <option value="out">流出</option>
              </select>
            ) : null}
            {eventType === 'corporate' ? (
              <select className="input-terminal text-sm w-full" value={eventActionType}
                onChange={(e) => setEventActionType(e.target.value as '' | PortfolioCorporateActionType)}>
                <option value="">全部公司行為</option>
                <option value="cash_dividend">現金分紅</option>
                <option value="split_adjustment">拆並股調整</option>
              </select>
            ) : null}
            <div className="text-[11px] text-secondary">
              {writeBlocked ? '刪除修正僅在單賬戶檢視可用。請先選擇具體賬戶後再刪除錯誤流水。' : '如有錯誤流水，可直接刪除後重新錄入。'}
            </div>
            <div className="max-h-64 overflow-auto rounded-lg border border-white/10 p-2">
              {eventType === 'trade' && tradeEvents.map((item) => (
                <div key={`t-${item.id}`} className="flex items-start justify-between gap-3 border-b border-white/5 py-2 text-xs text-secondary">
                  <div className="min-w-0">
                    {item.tradeDate} {formatSideLabel(item.side)} {item.symbol} 數量={item.quantity} 價格={item.price}
                  </div>
                  {!writeBlocked ? (
                    <button
                      type="button"
                      className="btn-secondary shrink-0 !px-3 !py-1 !text-[11px]"
                      onClick={() => openDeleteDialog({
                        eventType: 'trade',
                        id: item.id,
                        message: `確認刪除 ${item.tradeDate} 的${formatSideLabel(item.side)}流水 ${item.symbol}（數量 ${item.quantity}，價格 ${item.price}）嗎？`,
                      })}
                    >
                      刪除
                    </button>
                  ) : null}
                </div>
              ))}
              {eventType === 'cash' && cashEvents.map((item) => (
                <div key={`c-${item.id}`} className="flex items-start justify-between gap-3 border-b border-white/5 py-2 text-xs text-secondary">
                  <div className="min-w-0">
                    {item.eventDate} {formatCashDirectionLabel(item.direction)} {item.amount} {item.currency}
                  </div>
                  {!writeBlocked ? (
                    <button
                      type="button"
                      className="btn-secondary shrink-0 !px-3 !py-1 !text-[11px]"
                      onClick={() => openDeleteDialog({
                        eventType: 'cash',
                        id: item.id,
                        message: `確認刪除 ${item.eventDate} 的資金流水（${formatCashDirectionLabel(item.direction)} ${item.amount} ${item.currency}）嗎？`,
                      })}
                    >
                      刪除
                    </button>
                  ) : null}
                </div>
              ))}
              {eventType === 'corporate' && corporateEvents.map((item) => (
                <div key={`ca-${item.id}`} className="flex items-start justify-between gap-3 border-b border-white/5 py-2 text-xs text-secondary">
                  <div className="min-w-0">
                    {item.effectiveDate} {formatCorporateActionLabel(item.actionType)} {item.symbol}
                  </div>
                  {!writeBlocked ? (
                    <button
                      type="button"
                      className="btn-secondary shrink-0 !px-3 !py-1 !text-[11px]"
                      onClick={() => openDeleteDialog({
                        eventType: 'corporate',
                        id: item.id,
                        message: `確認刪除 ${item.effectiveDate} 的公司行為 ${formatCorporateActionLabel(item.actionType)}（${item.symbol}）嗎？`,
                      })}
                    >
                      刪除
                    </button>
                  ) : null}
                </div>
              ))}
              {!eventLoading
                && ((eventType === 'trade' && tradeEvents.length === 0)
                  || (eventType === 'cash' && cashEvents.length === 0)
                  || (eventType === 'corporate' && corporateEvents.length === 0)) ? (
                    <p className="text-xs text-muted text-center py-3">暫無流水</p>
                  ) : null}
            </div>
            <div className="flex items-center justify-between text-xs text-secondary">
              <span>第 {eventPage} / {totalEventPages} 頁</span>
              <div className="flex gap-2">
                <button type="button" className="btn-secondary text-xs px-3 py-1" disabled={eventPage <= 1}
                  onClick={() => setEventPage((prev) => Math.max(1, prev - 1))}>
                  上一頁
                </button>
                <button type="button" className="btn-secondary text-xs px-3 py-1" disabled={eventPage >= totalEventPages}
                  onClick={() => setEventPage((prev) => Math.min(totalEventPages, prev + 1))}>
                  下一頁
                </button>
              </div>
            </div>
          </div>
        </Card>
      </section>
      <ConfirmDialog
        isOpen={Boolean(pendingDelete)}
        title="刪除錯誤流水"
        message={pendingDelete?.message || '確認刪除這條流水嗎？'}
        confirmText={deleteLoading ? '刪除中...' : '確認刪除'}
        cancelText="取消"
        isDanger
        onConfirm={() => void handleConfirmDelete()}
        onCancel={() => {
          if (!deleteLoading) {
            setPendingDelete(null);
          }
        }}
      />
    </div>
  );
};

export default PortfolioPage;
