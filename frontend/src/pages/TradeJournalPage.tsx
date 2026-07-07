import { useState, useEffect, useCallback } from 'react';
import { DashboardLayout } from '../components/dashboard/DashboardLayout';
import { Card, CardStat } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { get, post } from '../api/client';
import type { AITradeReview } from '../hooks/useAI';

// --- Types ---

type SortDirection = 'asc' | 'desc';
type SortField = 'date' | 'symbol' | 'entry_price' | 'exit_price' | 'pnl' | 'confidence_score' | 'setup_type';

interface JournalEntry {
  id: number;
  date: string;
  symbol: string;
  entry_price: number;
  exit_price: number;
  pnl: number;
  setup_type: string;
  confidence_score: number;
  trend_direction: string;
  exit_reason: string;
  ai_grade?: string;
  ai_review?: AITradeReview;
}

interface JournalStats {
  total_trades: number;
  win_rate: number;
  avg_profit: number;
  avg_loss: number;
  profit_factor: number;
  best_trade: number;
  worst_trade: number;
}

interface JournalFilters {
  date_from: string;
  date_to: string;
  setup_type: string;
  pnl_filter: 'all' | 'profit' | 'loss';
  symbol: string;
}

interface JournalResponse {
  entries: JournalEntry[];
  total: number;
}

const SETUP_TYPES = [
  'All',
  'Trend Pullback',
  'Consolidation Breakout',
  'Momentum',
  'Reversal',
  'Scalp',
];

const GRADE_COLORS: Record<string, string> = {
  A: 'text-profit bg-profit/10 border-profit/30',
  B: 'text-blue-400 bg-blue-400/10 border-blue-400/30',
  C: 'text-yellow-400 bg-yellow-400/10 border-yellow-400/30',
  D: 'text-orange-400 bg-orange-400/10 border-orange-400/30',
  F: 'text-loss bg-loss/10 border-loss/30',
};

export function TradeJournalPage() {
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [stats, setStats] = useState<JournalStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [statsLoading, setStatsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortField, setSortField] = useState<SortField>('date');
  const [sortDir, setSortDir] = useState<SortDirection>('desc');
  const [filters, setFilters] = useState<JournalFilters>({
    date_from: '',
    date_to: '',
    setup_type: 'All',
    pnl_filter: 'all',
    symbol: '',
  });
  const [reviewingTradeId, setReviewingTradeId] = useState<number | null>(null);
  const [selectedReview, setSelectedReview] = useState<AITradeReview | null>(null);
  const [reviewLoading, setReviewLoading] = useState(false);

  const fetchEntries = useCallback(async () => {
    try {
      setLoading(true);
      const params: Record<string, unknown> = {
        sort_by: sortField,
        sort_dir: sortDir,
      };
      if (filters.date_from) params.date_from = filters.date_from;
      if (filters.date_to) params.date_to = filters.date_to;
      if (filters.setup_type !== 'All') params.setup_type = filters.setup_type;
      if (filters.pnl_filter !== 'all') params.pnl_filter = filters.pnl_filter;
      if (filters.symbol.trim()) params.symbol = filters.symbol.trim();

      const data = await get<JournalResponse>('/api/v1/journal', params);
      setEntries(data.entries || []);
      setError(null);
    } catch {
      setError('Failed to load trade journal entries.');
    } finally {
      setLoading(false);
    }
  }, [sortField, sortDir, filters]);

  const fetchStats = useCallback(async () => {
    try {
      setStatsLoading(true);
      const data = await get<JournalStats>('/api/v1/journal/stats');
      setStats(data);
    } catch {
      // Stats are supplementary — don't block the page
    } finally {
      setStatsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEntries();
  }, [fetchEntries]);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDir('desc');
    }
  };

  const handleReviewTrade = async (entry: JournalEntry) => {
    if (entry.ai_review) {
      setSelectedReview(entry.ai_review);
      setReviewingTradeId(entry.id);
      return;
    }
    try {
      setReviewLoading(true);
      setReviewingTradeId(entry.id);
      const result = await post<AITradeReview>('/api/v1/ai/review-trade', {
        trade_id: entry.id,
        symbol: entry.symbol,
        entry_price: entry.entry_price,
        exit_price: entry.exit_price,
        pnl: entry.pnl,
        setup_type: entry.setup_type,
        exit_reason: entry.exit_reason,
      });
      setSelectedReview(result);
    } catch {
      setSelectedReview(null);
    } finally {
      setReviewLoading(false);
    }
  };

  const clearFilters = () => {
    setFilters({
      date_from: '',
      date_to: '',
      setup_type: 'All',
      pnl_filter: 'all',
      symbol: '',
    });
  };

  const hasActiveFilters =
    filters.date_from || filters.date_to || filters.setup_type !== 'All' || filters.pnl_filter !== 'all' || filters.symbol.trim();

  const formatDate = (ts: string): string => {
    const date = new Date(ts);
    return date.toLocaleDateString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  };

  const formatCurrency = (val: number): string => {
    const prefix = val >= 0 ? '+' : '';
    return `${prefix}₹${val.toFixed(2)}`;
  };

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) {
      return <span className="ml-1 text-dashboard-muted/50" aria-hidden="true">↕</span>;
    }
    return (
      <span className="ml-1" aria-hidden="true">
        {sortDir === 'asc' ? '↑' : '↓'}
      </span>
    );
  };

  return (
    <DashboardLayout>
      <div className="space-y-4">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold text-dashboard-text">Trade Journal</h1>
            <p className="text-sm text-dashboard-muted">
              Review and analyze your trading performance
            </p>
          </div>
          <Button variant="secondary" size="sm" onClick={fetchEntries}>
            Refresh
          </Button>
        </div>

        {/* Aggregate Stats Panel */}
        {statsLoading ? (
          <Card padding="md">
            <div className="text-sm text-dashboard-muted text-center">Loading stats...</div>
          </Card>
        ) : stats ? (
          <Card padding="md">
            <h2 className="text-sm font-medium text-dashboard-text mb-3">Performance Summary</h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-4">
              <CardStat label="Total Trades" value={stats.total_trades} />
              <CardStat
                label="Win Rate"
                value={`${stats.win_rate.toFixed(1)}%`}
                variant={stats.win_rate >= 50 ? 'profit' : 'loss'}
              />
              <CardStat
                label="Avg Profit"
                value={`₹${stats.avg_profit.toFixed(2)}`}
                variant="profit"
              />
              <CardStat
                label="Avg Loss"
                value={`₹${Math.abs(stats.avg_loss).toFixed(2)}`}
                variant="loss"
              />
              <CardStat
                label="Profit Factor"
                value={stats.profit_factor.toFixed(2)}
                variant={stats.profit_factor >= 1.5 ? 'profit' : stats.profit_factor >= 1 ? 'neutral' : 'loss'}
              />
              <CardStat
                label="Best Trade"
                value={`₹${stats.best_trade.toFixed(2)}`}
                variant="profit"
              />
              <CardStat
                label="Worst Trade"
                value={`₹${stats.worst_trade.toFixed(2)}`}
                variant="loss"
              />
            </div>
          </Card>
        ) : null}

        {/* Filters */}
        <Card padding="sm">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label htmlFor="journal-date-from" className="block text-xs text-dashboard-muted mb-1">
                From
              </label>
              <input
                id="journal-date-from"
                type="date"
                value={filters.date_from}
                onChange={(e) => setFilters((f) => ({ ...f, date_from: e.target.value }))}
                className="bg-dashboard-bg border border-dashboard-border rounded-lg px-2 py-1.5 text-sm text-dashboard-text focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label htmlFor="journal-date-to" className="block text-xs text-dashboard-muted mb-1">
                To
              </label>
              <input
                id="journal-date-to"
                type="date"
                value={filters.date_to}
                onChange={(e) => setFilters((f) => ({ ...f, date_to: e.target.value }))}
                className="bg-dashboard-bg border border-dashboard-border rounded-lg px-2 py-1.5 text-sm text-dashboard-text focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label htmlFor="journal-setup-type" className="block text-xs text-dashboard-muted mb-1">
                Setup Type
              </label>
              <select
                id="journal-setup-type"
                value={filters.setup_type}
                onChange={(e) => setFilters((f) => ({ ...f, setup_type: e.target.value }))}
                className="bg-dashboard-bg border border-dashboard-border rounded-lg px-2 py-1.5 text-sm text-dashboard-text focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {SETUP_TYPES.map((type) => (
                  <option key={type} value={type}>{type}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="journal-pnl-filter" className="block text-xs text-dashboard-muted mb-1">
                P&amp;L
              </label>
              <select
                id="journal-pnl-filter"
                value={filters.pnl_filter}
                onChange={(e) => setFilters((f) => ({ ...f, pnl_filter: e.target.value as JournalFilters['pnl_filter'] }))}
                className="bg-dashboard-bg border border-dashboard-border rounded-lg px-2 py-1.5 text-sm text-dashboard-text focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="all">All</option>
                <option value="profit">Profit Only</option>
                <option value="loss">Loss Only</option>
              </select>
            </div>
            <div>
              <label htmlFor="journal-symbol" className="block text-xs text-dashboard-muted mb-1">
                Symbol
              </label>
              <input
                id="journal-symbol"
                type="text"
                placeholder="e.g. NIFTY"
                value={filters.symbol}
                onChange={(e) => setFilters((f) => ({ ...f, symbol: e.target.value }))}
                className="bg-dashboard-bg border border-dashboard-border rounded-lg px-2 py-1.5 text-sm text-dashboard-text focus:outline-none focus:ring-2 focus:ring-blue-500 w-28"
              />
            </div>
            {hasActiveFilters && (
              <Button variant="ghost" size="sm" onClick={clearFilters}>
                Clear Filters
              </Button>
            )}
          </div>
        </Card>

        {/* Error */}
        {error && (
          <div className="bg-loss/10 border border-loss/30 rounded-lg p-3 text-sm text-loss" role="alert">
            {error}
          </div>
        )}

        {/* Trade Table */}
        <Card padding="none">
          {loading ? (
            <div className="p-8 text-center text-dashboard-muted">Loading journal entries...</div>
          ) : entries.length === 0 ? (
            <div className="p-8 text-center text-dashboard-muted">No trades found matching filters</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm" role="table" aria-label="Trade journal entries">
                <thead>
                  <tr className="border-b border-dashboard-border text-left">
                    <th className="px-4 py-3 text-xs font-medium text-dashboard-muted">
                      <button
                        onClick={() => handleSort('date')}
                        className="inline-flex items-center hover:text-dashboard-text"
                        aria-label="Sort by date"
                      >
                        Date<SortIcon field="date" />
                      </button>
                    </th>
                    <th className="px-4 py-3 text-xs font-medium text-dashboard-muted">
                      <button
                        onClick={() => handleSort('symbol')}
                        className="inline-flex items-center hover:text-dashboard-text"
                        aria-label="Sort by symbol"
                      >
                        Symbol<SortIcon field="symbol" />
                      </button>
                    </th>
                    <th className="px-4 py-3 text-xs font-medium text-dashboard-muted text-right">
                      <button
                        onClick={() => handleSort('entry_price')}
                        className="inline-flex items-center hover:text-dashboard-text"
                        aria-label="Sort by entry price"
                      >
                        Entry<SortIcon field="entry_price" />
                      </button>
                    </th>
                    <th className="px-4 py-3 text-xs font-medium text-dashboard-muted text-right">
                      <button
                        onClick={() => handleSort('exit_price')}
                        className="inline-flex items-center hover:text-dashboard-text"
                        aria-label="Sort by exit price"
                      >
                        Exit<SortIcon field="exit_price" />
                      </button>
                    </th>
                    <th className="px-4 py-3 text-xs font-medium text-dashboard-muted text-right">
                      <button
                        onClick={() => handleSort('pnl')}
                        className="inline-flex items-center hover:text-dashboard-text"
                        aria-label="Sort by profit and loss"
                      >
                        P&amp;L<SortIcon field="pnl" />
                      </button>
                    </th>
                    <th className="px-4 py-3 text-xs font-medium text-dashboard-muted">
                      <button
                        onClick={() => handleSort('setup_type')}
                        className="inline-flex items-center hover:text-dashboard-text"
                        aria-label="Sort by setup type"
                      >
                        Setup<SortIcon field="setup_type" />
                      </button>
                    </th>
                    <th className="px-4 py-3 text-xs font-medium text-dashboard-muted text-right">
                      <button
                        onClick={() => handleSort('confidence_score')}
                        className="inline-flex items-center hover:text-dashboard-text"
                        aria-label="Sort by confidence score"
                      >
                        Confidence<SortIcon field="confidence_score" />
                      </button>
                    </th>
                    <th className="px-4 py-3 text-xs font-medium text-dashboard-muted">Trend</th>
                    <th className="px-4 py-3 text-xs font-medium text-dashboard-muted">Exit Reason</th>
                    <th className="px-4 py-3 text-xs font-medium text-dashboard-muted">AI Grade</th>
                    <th className="px-4 py-3 text-xs font-medium text-dashboard-muted">Review</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((entry) => (
                    <tr
                      key={entry.id}
                      className="border-b border-dashboard-border/50 hover:bg-dashboard-bg/50"
                    >
                      <td className="px-4 py-3 text-xs text-dashboard-muted whitespace-nowrap">
                        {formatDate(entry.date)}
                      </td>
                      <td className="px-4 py-3 font-medium text-dashboard-text">
                        {entry.symbol}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-dashboard-text">
                        ₹{entry.entry_price.toFixed(2)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-dashboard-text">
                        ₹{entry.exit_price.toFixed(2)}
                      </td>
                      <td className={`px-4 py-3 text-right font-mono font-medium ${entry.pnl >= 0 ? 'text-profit' : 'text-loss'}`}>
                        {formatCurrency(entry.pnl)}
                      </td>
                      <td className="px-4 py-3 text-dashboard-muted text-xs">
                        {entry.setup_type}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-dashboard-text">
                        {entry.confidence_score}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`text-xs font-medium ${
                          entry.trend_direction === 'bullish' ? 'text-profit' :
                          entry.trend_direction === 'bearish' ? 'text-loss' :
                          'text-dashboard-muted'
                        }`}>
                          {entry.trend_direction}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs text-dashboard-muted max-w-[120px] truncate" title={entry.exit_reason}>
                        {entry.exit_reason}
                      </td>
                      <td className="px-4 py-3">
                        {entry.ai_grade ? (
                          <span className={`inline-block px-2 py-0.5 text-xs font-medium rounded border ${GRADE_COLORS[entry.ai_grade] || 'text-dashboard-muted'}`}>
                            {entry.ai_grade}
                          </span>
                        ) : (
                          <span className="text-xs text-dashboard-muted">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleReviewTrade(entry)}
                          aria-label={`AI review for ${entry.symbol} trade`}
                        >
                          {reviewingTradeId === entry.id && reviewLoading ? '...' : '📝'}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* AI Trade Review Panel */}
        {selectedReview && reviewingTradeId && (
          <Card padding="md">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-medium text-dashboard-text">
                AI Trade Review
              </h2>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => { setSelectedReview(null); setReviewingTradeId(null); }}
                aria-label="Close AI review panel"
              >
                ✕
              </Button>
            </div>

            <div className="flex items-center gap-3 mb-4">
              <span className={`inline-block px-3 py-1 text-sm font-bold rounded border ${GRADE_COLORS[selectedReview.grade] || 'text-dashboard-muted'}`}>
                Grade: {selectedReview.grade}
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
              <div>
                <h3 className="text-xs font-medium text-dashboard-muted mb-1">Entry Feedback</h3>
                <p className="text-dashboard-text">{selectedReview.entryFeedback}</p>
              </div>
              <div>
                <h3 className="text-xs font-medium text-dashboard-muted mb-1">Exit Feedback</h3>
                <p className="text-dashboard-text">{selectedReview.exitFeedback}</p>
              </div>
              <div>
                <h3 className="text-xs font-medium text-dashboard-muted mb-1">Position Sizing</h3>
                <p className="text-dashboard-text">{selectedReview.sizingFeedback}</p>
              </div>
              <div>
                <h3 className="text-xs font-medium text-dashboard-muted mb-1">Risk Management</h3>
                <p className="text-dashboard-text">{selectedReview.riskFeedback}</p>
              </div>
            </div>

            {selectedReview.optimalComparison && (
              <div className="mt-4 p-3 bg-dashboard-bg rounded-lg">
                <h3 className="text-xs font-medium text-dashboard-muted mb-1">Optimal Comparison</h3>
                <p className="text-sm text-dashboard-text">{selectedReview.optimalComparison}</p>
              </div>
            )}

            {selectedReview.patternsIdentified.length > 0 && (
              <div className="mt-4">
                <h3 className="text-xs font-medium text-dashboard-muted mb-2">Patterns Identified</h3>
                <div className="flex flex-wrap gap-2">
                  {selectedReview.patternsIdentified.map((pattern, idx) => (
                    <span
                      key={idx}
                      className="inline-block px-2 py-1 text-xs bg-blue-500/10 text-blue-400 rounded border border-blue-500/20"
                    >
                      {pattern}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </Card>
        )}
      </div>
    </DashboardLayout>
  );
}
