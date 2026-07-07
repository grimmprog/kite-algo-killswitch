import { useState, useCallback } from 'react';
import { DashboardLayout } from '../components/dashboard/DashboardLayout';
import { Card, CardStat } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { usePaperTrading } from '../hooks/usePaperTrading';
import type { PaperTradeEntry, PaperTrade } from '../hooks/usePaperTrading';

// --- Account Stats Section ---

function AccountStats({
  balance,
  totalPnl,
  winRate,
  profitFactor,
  roiPct,
}: {
  balance: number;
  totalPnl: number;
  winRate: number;
  profitFactor: number;
  roiPct: number;
}) {
  return (
    <Card>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        <CardStat label="Balance" value={`₹${balance.toLocaleString('en-IN')}`} />
        <CardStat
          label="Total P&L"
          value={`${totalPnl >= 0 ? '+' : ''}₹${totalPnl.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          variant={totalPnl > 0 ? 'profit' : totalPnl < 0 ? 'loss' : 'neutral'}
        />
        <CardStat
          label="Win Rate"
          value={`${winRate.toFixed(1)}%`}
          variant={winRate >= 50 ? 'profit' : winRate > 0 ? 'loss' : 'neutral'}
        />
        <CardStat
          label="Profit Factor"
          value={profitFactor.toFixed(2)}
          variant={profitFactor >= 1 ? 'profit' : 'loss'}
        />
        <CardStat
          label="ROI"
          value={`${roiPct >= 0 ? '+' : ''}${roiPct.toFixed(1)}%`}
          variant={roiPct > 0 ? 'profit' : roiPct < 0 ? 'loss' : 'neutral'}
        />
      </div>
    </Card>
  );
}

// --- Trade Entry Form ---

interface FormErrors {
  symbol?: string;
  strike?: string;
  entryPrice?: string;
  quantity?: string;
  stopLoss?: string;
  target?: string;
  capital?: string;
}

const INITIAL_FORM: PaperTradeEntry = {
  symbol: '',
  strike: 0,
  optionType: 'CE',
  entryPrice: 0,
  quantity: 0,
  stopLoss: 0,
  target: 0,
};

function TradeEntryForm({
  availableBalance,
  onSubmit,
  isSubmitting,
}: {
  availableBalance: number;
  onSubmit: (trade: PaperTradeEntry) => Promise<void>;
  isSubmitting: boolean;
}) {
  const [form, setForm] = useState<PaperTradeEntry>(INITIAL_FORM);
  const [errors, setErrors] = useState<FormErrors>({});

  const validate = useCallback((): FormErrors => {
    const errs: FormErrors = {};
    if (!form.symbol.trim()) errs.symbol = 'Symbol is required';
    if (form.strike <= 0) errs.strike = 'Strike must be positive';
    if (form.entryPrice <= 0) errs.entryPrice = 'Entry price must be positive';
    if (form.quantity <= 0) errs.quantity = 'Quantity must be positive';
    if (form.stopLoss <= 0) errs.stopLoss = 'Stop loss must be positive';
    if (form.target <= 0) errs.target = 'Target must be positive';
    if (form.entryPrice > 0 && form.quantity > 0) {
      const investmentAmount = form.entryPrice * form.quantity;
      if (investmentAmount > availableBalance) {
        errs.capital = `Insufficient capital. Required: ₹${investmentAmount.toLocaleString('en-IN')}, Available: ₹${availableBalance.toLocaleString('en-IN')}`;
      }
    }
    return errs;
  }, [form, availableBalance]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const validationErrors = validate();
    setErrors(validationErrors);
    if (Object.keys(validationErrors).length > 0) return;

    try {
      await onSubmit(form);
      setForm(INITIAL_FORM);
      setErrors({});
    } catch {
      // Error is handled by the hook
    }
  };

  const updateField = (field: keyof PaperTradeEntry, value: string | number) => {
    setForm((prev) => ({ ...prev, [field]: value }));
    // Clear the field error on change
    if (errors[field as keyof FormErrors]) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[field as keyof FormErrors];
        return next;
      });
    }
  };

  return (
    <Card title="Enter Paper Trade" subtitle="Place a virtual trade to practice">
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <Input
            label="Symbol"
            placeholder="e.g. NIFTY"
            value={form.symbol}
            onChange={(e) => updateField('symbol', e.target.value.toUpperCase())}
            error={errors.symbol}
          />
          <Input
            label="Strike"
            type="number"
            placeholder="e.g. 19500"
            value={form.strike || ''}
            onChange={(e) => updateField('strike', parseFloat(e.target.value) || 0)}
            error={errors.strike}
          />
          <div className="w-full">
            <label
              htmlFor="option-type"
              className="block text-sm font-medium text-dashboard-text mb-1.5"
            >
              Option Type
            </label>
            <select
              id="option-type"
              value={form.optionType}
              onChange={(e) => updateField('optionType', e.target.value as 'CE' | 'PE')}
              className="w-full px-3 py-2 rounded-lg bg-dashboard-bg border border-dashboard-border text-dashboard-text text-sm font-mono transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="CE">CE (Call)</option>
              <option value="PE">PE (Put)</option>
            </select>
          </div>
          <Input
            label="Entry Price"
            type="number"
            placeholder="e.g. 250.50"
            value={form.entryPrice || ''}
            onChange={(e) => updateField('entryPrice', parseFloat(e.target.value) || 0)}
            error={errors.entryPrice}
            step="0.05"
          />
          <Input
            label="Quantity"
            type="number"
            placeholder="e.g. 50"
            value={form.quantity || ''}
            onChange={(e) => updateField('quantity', parseInt(e.target.value, 10) || 0)}
            error={errors.quantity}
          />
          <Input
            label="Stop Loss"
            type="number"
            placeholder="e.g. 230.00"
            value={form.stopLoss || ''}
            onChange={(e) => updateField('stopLoss', parseFloat(e.target.value) || 0)}
            error={errors.stopLoss}
            step="0.05"
          />
          <Input
            label="Target"
            type="number"
            placeholder="e.g. 280.00"
            value={form.target || ''}
            onChange={(e) => updateField('target', parseFloat(e.target.value) || 0)}
            error={errors.target}
            step="0.05"
          />
        </div>

        {errors.capital && (
          <p className="text-xs text-loss" role="alert">
            {errors.capital}
          </p>
        )}

        <div className="flex items-center justify-between pt-2">
          <p className="text-xs text-dashboard-muted">
            Available: ₹{availableBalance.toLocaleString('en-IN')}
            {form.entryPrice > 0 && form.quantity > 0 && (
              <span className="ml-2">
                | Required: ₹{(form.entryPrice * form.quantity).toLocaleString('en-IN')}
              </span>
            )}
          </p>
          <Button type="submit" isLoading={isSubmitting} disabled={isSubmitting}>
            Enter Trade
          </Button>
        </div>
      </form>
    </Card>
  );
}

// --- Open Positions List ---

function OpenPositionsList({
  positions,
  onExit,
  isExiting,
}: {
  positions: PaperTrade[];
  onExit: (tradeId: number) => void;
  isExiting: boolean;
}) {
  if (positions.length === 0) {
    return (
      <Card title="Open Positions">
        <div className="text-center py-6">
          <p className="text-sm text-dashboard-muted">No open positions</p>
        </div>
      </Card>
    );
  }

  return (
    <Card title="Open Positions" subtitle={`${positions.length} active`} padding="none">
      <div className="overflow-x-auto">
        <table className="w-full text-sm" aria-label="Open paper trading positions">
          <thead>
            <tr className="border-b border-dashboard-border">
              <th className="text-left py-2 px-4 text-xs text-dashboard-muted font-medium">Symbol</th>
              <th className="text-right py-2 px-4 text-xs text-dashboard-muted font-medium">Strike</th>
              <th className="text-center py-2 px-4 text-xs text-dashboard-muted font-medium">Type</th>
              <th className="text-right py-2 px-4 text-xs text-dashboard-muted font-medium">Entry</th>
              <th className="text-right py-2 px-4 text-xs text-dashboard-muted font-medium">Qty</th>
              <th className="text-right py-2 px-4 text-xs text-dashboard-muted font-medium">Current</th>
              <th className="text-right py-2 px-4 text-xs text-dashboard-muted font-medium">P&L</th>
              <th className="text-right py-2 px-4 text-xs text-dashboard-muted font-medium">SL</th>
              <th className="text-right py-2 px-4 text-xs text-dashboard-muted font-medium">Target</th>
              <th className="text-right py-2 px-4 text-xs text-dashboard-muted font-medium">Action</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((pos) => {
              const pnl = pos.unrealizedPnl ?? (pos.currentPrice ? (pos.currentPrice - pos.entryPrice) * pos.quantity : 0);
              return (
                <tr
                  key={pos.id}
                  className="border-b border-dashboard-border last:border-0 hover:bg-dashboard-bg/50 transition-colors"
                >
                  <td className="py-2.5 px-4 font-mono font-medium text-dashboard-text">
                    {pos.symbol}
                  </td>
                  <td className="py-2.5 px-4 text-right font-mono text-dashboard-text">
                    {pos.strike}
                  </td>
                  <td className="py-2.5 px-4 text-center">
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                        pos.optionType === 'CE'
                          ? 'bg-profit/10 text-profit'
                          : 'bg-loss/10 text-loss'
                      }`}
                    >
                      {pos.optionType}
                    </span>
                  </td>
                  <td className="py-2.5 px-4 text-right font-mono text-dashboard-text">
                    ₹{pos.entryPrice.toFixed(2)}
                  </td>
                  <td className="py-2.5 px-4 text-right font-mono text-dashboard-text">
                    {pos.quantity}
                  </td>
                  <td className="py-2.5 px-4 text-right font-mono text-dashboard-text">
                    {pos.currentPrice != null ? `₹${pos.currentPrice.toFixed(2)}` : '—'}
                  </td>
                  <td className={`py-2.5 px-4 text-right font-mono font-medium ${pnl > 0 ? 'text-profit' : pnl < 0 ? 'text-loss' : 'text-dashboard-muted'}`}>
                    {pnl >= 0 ? '+' : ''}₹{pnl.toFixed(2)}
                  </td>
                  <td className="py-2.5 px-4 text-right font-mono text-loss">
                    ₹{pos.stopLoss.toFixed(2)}
                  </td>
                  <td className="py-2.5 px-4 text-right font-mono text-profit">
                    ₹{pos.target.toFixed(2)}
                  </td>
                  <td className="py-2.5 px-4 text-right">
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => onExit(pos.id)}
                      disabled={isExiting}
                      aria-label={`Exit position ${pos.symbol} ${pos.strike} ${pos.optionType}`}
                    >
                      Exit
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

// --- Trade History Table ---

function TradeHistoryTable({ trades }: { trades: PaperTrade[] }) {
  if (trades.length === 0) {
    return (
      <Card title="Trade History">
        <div className="text-center py-6">
          <p className="text-sm text-dashboard-muted">No completed trades yet</p>
        </div>
      </Card>
    );
  }

  return (
    <Card title="Trade History" subtitle={`${trades.length} completed`} padding="none">
      <div className="overflow-x-auto">
        <table className="w-full text-sm" aria-label="Paper trading history">
          <thead>
            <tr className="border-b border-dashboard-border">
              <th className="text-left py-2 px-4 text-xs text-dashboard-muted font-medium">Symbol</th>
              <th className="text-right py-2 px-4 text-xs text-dashboard-muted font-medium">Strike</th>
              <th className="text-center py-2 px-4 text-xs text-dashboard-muted font-medium">Type</th>
              <th className="text-right py-2 px-4 text-xs text-dashboard-muted font-medium">Entry</th>
              <th className="text-right py-2 px-4 text-xs text-dashboard-muted font-medium">Exit</th>
              <th className="text-right py-2 px-4 text-xs text-dashboard-muted font-medium">Qty</th>
              <th className="text-right py-2 px-4 text-xs text-dashboard-muted font-medium">P&L</th>
              <th className="text-left py-2 px-4 text-xs text-dashboard-muted font-medium">Exit Reason</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((trade) => (
              <tr
                key={trade.id}
                className="border-b border-dashboard-border last:border-0 hover:bg-dashboard-bg/50 transition-colors"
              >
                <td className="py-2.5 px-4 font-mono font-medium text-dashboard-text">
                  {trade.symbol}
                </td>
                <td className="py-2.5 px-4 text-right font-mono text-dashboard-text">
                  {trade.strike}
                </td>
                <td className="py-2.5 px-4 text-center">
                  <span
                    className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                      trade.optionType === 'CE'
                        ? 'bg-profit/10 text-profit'
                        : 'bg-loss/10 text-loss'
                    }`}
                  >
                    {trade.optionType}
                  </span>
                </td>
                <td className="py-2.5 px-4 text-right font-mono text-dashboard-text">
                  ₹{trade.entryPrice.toFixed(2)}
                </td>
                <td className="py-2.5 px-4 text-right font-mono text-dashboard-text">
                  {trade.exitPrice != null ? `₹${trade.exitPrice.toFixed(2)}` : '—'}
                </td>
                <td className="py-2.5 px-4 text-right font-mono text-dashboard-text">
                  {trade.quantity}
                </td>
                <td className={`py-2.5 px-4 text-right font-mono font-medium ${(trade.pnl ?? 0) > 0 ? 'text-profit' : (trade.pnl ?? 0) < 0 ? 'text-loss' : 'text-dashboard-muted'}`}>
                  {(trade.pnl ?? 0) >= 0 ? '+' : ''}₹{(trade.pnl ?? 0).toFixed(2)}
                </td>
                <td className="py-2.5 px-4 text-dashboard-muted text-xs">
                  {trade.exitReason || '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

// --- Reset Account Confirmation Dialog ---

function ResetConfirmDialog({
  isOpen,
  onConfirm,
  onCancel,
  isResetting,
}: {
  isOpen: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  isResetting: boolean;
}) {
  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="reset-dialog-title"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60"
        onClick={onCancel}
        aria-hidden="true"
      />
      {/* Dialog content */}
      <div className="relative bg-dashboard-card border border-dashboard-border rounded-xl p-6 max-w-sm w-full mx-4 shadow-xl">
        <h2
          id="reset-dialog-title"
          className="text-lg font-bold text-dashboard-text"
        >
          Reset Paper Account?
        </h2>
        <p className="text-sm text-dashboard-muted mt-2">
          This will restore your virtual balance to ₹40,000 and clear all trade history. This action cannot be undone.
        </p>
        <div className="flex items-center justify-end gap-3 mt-6">
          <Button
            variant="secondary"
            onClick={onCancel}
            disabled={isResetting}
          >
            Cancel
          </Button>
          <Button
            variant="danger"
            onClick={onConfirm}
            isLoading={isResetting}
            disabled={isResetting}
          >
            Reset Account
          </Button>
        </div>
      </div>
    </div>
  );
}

// --- Main Page ---

export function PaperTradingPage() {
  const {
    account,
    openPositions,
    tradeHistory,
    isLoading,
    error,
    enterTrade,
    exitTrade,
    fetchTradeHistory,
    resetAccount,
  } = usePaperTrading();

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isExiting, setIsExiting] = useState(false);
  const [showResetDialog, setShowResetDialog] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);

  const handleEnterTrade = async (trade: PaperTradeEntry) => {
    setIsSubmitting(true);
    try {
      await enterTrade(trade);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleExitTrade = async (tradeId: number) => {
    setIsExiting(true);
    try {
      await exitTrade(tradeId);
    } finally {
      setIsExiting(false);
    }
  };

  const handleReset = async () => {
    setIsResetting(true);
    try {
      await resetAccount();
      setShowResetDialog(false);
    } finally {
      setIsResetting(false);
    }
  };

  const handleLoadHistory = async () => {
    await fetchTradeHistory();
    setHistoryLoaded(true);
  };

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Page header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-dashboard-text">Paper Trading</h1>
            <p className="text-sm text-dashboard-muted mt-1">
              Practice trading with virtual capital — no real money at risk
            </p>
          </div>
          <Button
            variant="danger"
            size="sm"
            onClick={() => setShowResetDialog(true)}
            aria-label="Reset paper trading account"
          >
            Reset Account
          </Button>
        </div>

        {/* Error display */}
        {error && (
          <Card className="border-loss/30 bg-loss/5" role="alert" aria-live="assertive">
            <div className="flex items-start gap-3">
              <span className="text-loss text-lg" aria-hidden="true">⚠</span>
              <div>
                <p className="text-sm font-medium text-loss">Error</p>
                <p className="text-xs text-dashboard-muted mt-0.5">{error}</p>
              </div>
            </div>
          </Card>
        )}

        {/* Loading state */}
        {isLoading && !account && (
          <Card className="flex items-center justify-center py-8" role="status" aria-live="polite">
            <div className="flex flex-col items-center gap-3">
              <svg
                className="animate-spin h-6 w-6 text-blue-500"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <p className="text-sm text-dashboard-muted">Loading paper trading account...</p>
            </div>
          </Card>
        )}

        {/* Account stats */}
        {account && (
          <AccountStats
            balance={account.balance}
            totalPnl={account.totalPnl}
            winRate={account.winRate}
            profitFactor={account.profitFactor}
            roiPct={account.roiPct}
          />
        )}

        {/* Trade entry form */}
        {account && (
          <TradeEntryForm
            availableBalance={account.balance}
            onSubmit={handleEnterTrade}
            isSubmitting={isSubmitting}
          />
        )}

        {/* Open positions */}
        <OpenPositionsList
          positions={openPositions}
          onExit={handleExitTrade}
          isExiting={isExiting}
        />

        {/* Trade history */}
        {historyLoaded ? (
          <TradeHistoryTable trades={tradeHistory} />
        ) : (
          <Card title="Trade History">
            <div className="text-center py-4">
              <Button variant="secondary" size="sm" onClick={handleLoadHistory}>
                Load Trade History
              </Button>
            </div>
          </Card>
        )}

        {/* Reset confirmation dialog */}
        <ResetConfirmDialog
          isOpen={showResetDialog}
          onConfirm={handleReset}
          onCancel={() => setShowResetDialog(false)}
          isResetting={isResetting}
        />
      </div>
    </DashboardLayout>
  );
}
