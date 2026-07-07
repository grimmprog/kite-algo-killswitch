import { useState, useEffect, useCallback, useRef } from 'react';
import { Card, CardStat } from '../ui/Card';
import { getAccountDashboard, getDhanAccountDashboard } from '../../api/dashboard';
import type { AccountDashboardResponse, AccountPosition } from '../../api/types';

const POLL_INTERVAL_MS = 30_000; // 30 seconds

interface AccountSummaryProps {
  /** Which broker to fetch data from. Defaults to 'kite'. */
  broker?: 'kite' | 'dhan';
}

/**
 * AccountSummary — Dashboard widget displaying live account data.
 * - Capital card: available balance, used margin
 * - P&L card: total P&L (green/red), realized vs unrealized
 * - Trades card: number of trades today, buy/sell breakdown
 * - Positions table: symbol, qty, avg price, LTP, P&L per position
 * - Auto-refreshes every 30 seconds
 * - Shows loading skeleton while fetching
 */
export function AccountSummary({ broker = 'kite' }: AccountSummaryProps) {
  const [data, setData] = useState<AccountDashboardResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const result = broker === 'dhan'
        ? await getDhanAccountDashboard()
        : await getAccountDashboard();
      setData(result);
      setError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch account data';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, [broker]);

  // Reset state and refetch when broker changes
  useEffect(() => {
    setData(null);
    setIsLoading(true);
    setError(null);
  }, [broker]);

  useEffect(() => {
    fetchData();
    intervalRef.current = setInterval(fetchData, POLL_INTERVAL_MS);
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [fetchData]);

  if (isLoading && !data) {
    return <AccountSummarySkeleton />;
  }

  if (error && !data) {
    return (
      <Card title="Account Summary">
        <div className="py-4 text-center">
          <p className="text-sm text-loss" role="alert">{error}</p>
          <p className="text-xs text-dashboard-muted mt-2">
            {broker === 'dhan'
              ? 'Make sure your Dhan connection is active'
              : 'Make sure your Kite session is active'}
          </p>
        </div>
      </Card>
    );
  }

  if (!data) return null;

  const { margins, pnl_summary, trades_today, positions, orders_today } = data;

  // Buy/sell breakdown from orders (not fills)
  const buyCount = orders_today.orders.filter(o => o.transaction_type === 'BUY' && o.status === 'COMPLETE').length;
  const sellCount = orders_today.orders.filter(o => o.transaction_type === 'SELL' && o.status === 'COMPLETE').length;

  return (
    <div className="space-y-4">
      {/* Top cards row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Capital Card */}
        <Card title="Capital">
          <div className="space-y-3">
            <CardStat
              label="Available Balance"
              value={`₹${formatNumber(margins.available_capital)}`}
            />
            <div className="flex justify-between">
              <div>
                <p className="text-xs text-dashboard-muted">Used Margin</p>
                <p className="text-sm font-mono text-dashboard-text">
                  ₹{formatNumber(margins.used)}
                </p>
              </div>
              <div className="text-right">
                <p className="text-xs text-dashboard-muted">Net</p>
                <p className="text-sm font-mono text-dashboard-text">
                  ₹{formatNumber(margins.net)}
                </p>
              </div>
            </div>
          </div>
        </Card>

        {/* P&L Card */}
        <Card title="Today's P&L">
          <div className="space-y-3">
            <CardStat
              label="Net Profit (after charges)"
              value={`${pnl_summary.net_pnl >= 0 ? '+' : ''}₹${formatNumber(pnl_summary.net_pnl)}`}
              variant={pnl_summary.net_pnl >= 0 ? 'profit' : 'loss'}
            />
            <div className="flex justify-between">
              <div>
                <p className="text-xs text-dashboard-muted">Gross P&L</p>
                <p className={`text-sm font-mono ${pnl_summary.total_pnl >= 0 ? 'text-profit' : 'text-loss'}`}>
                  {pnl_summary.total_pnl >= 0 ? '+' : ''}₹{formatNumber(pnl_summary.total_pnl)}
                </p>
              </div>
              <div className="text-right">
                <p className="text-xs text-dashboard-muted">Total Charges</p>
                <p className="text-sm font-mono text-loss">
                  -₹{formatNumber(pnl_summary.total_charges)}
                </p>
              </div>
            </div>
            <div className="border-t border-dashboard-border pt-2 grid grid-cols-2 gap-x-4 gap-y-1">
              <div className="flex justify-between">
                <span className="text-[10px] text-dashboard-muted">Brokerage</span>
                <span className="text-[10px] font-mono text-dashboard-muted">₹{pnl_summary.brokerage.toFixed(0)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[10px] text-dashboard-muted">STT</span>
                <span className="text-[10px] font-mono text-dashboard-muted">₹{pnl_summary.stt.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[10px] text-dashboard-muted">Exchange + SEBI</span>
                <span className="text-[10px] font-mono text-dashboard-muted">₹{pnl_summary.exchange_charges.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[10px] text-dashboard-muted">GST</span>
                <span className="text-[10px] font-mono text-dashboard-muted">₹{pnl_summary.gst.toFixed(2)}</span>
              </div>
            </div>
          </div>
        </Card>

        {/* Trades Card */}
        <Card title="Orders Today">
          <div className="space-y-3">
            <CardStat
              label="Executed Orders"
              value={trades_today.count.toString()}
            />
            <div className="flex justify-between">
              <div>
                <p className="text-xs text-dashboard-muted">Buy Orders</p>
                <p className="text-sm font-mono text-profit">{buyCount}</p>
              </div>
              <div className="text-right">
                <p className="text-xs text-dashboard-muted">Sell Orders</p>
                <p className="text-sm font-mono text-loss">{sellCount}</p>
              </div>
            </div>
            {trades_today.fills > 0 && (
              <div className="border-t border-dashboard-border pt-2">
                <p className="text-xs text-dashboard-muted">
                  Trade fills: {trades_today.fills}
                </p>
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* Positions Table */}
      <PositionsTable positions={positions} />

      {/* Error banner (shown when data exists but refresh failed) */}
      {error && data && (
        <p className="text-xs text-amber-400 text-center" role="alert">
          Failed to refresh — showing last known data
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface PositionsTableProps {
  positions: AccountPosition[];
}

function PositionsTable({ positions }: PositionsTableProps) {
  if (positions.length === 0) {
    return (
      <Card title="Positions">
        <p className="text-sm text-dashboard-muted py-4 text-center">
          All positions closed
        </p>
      </Card>
    );
  }

  return (
    <Card title="Positions" subtitle={`${positions.length} open`}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm" aria-label="Open positions from Kite">
          <thead>
            <tr className="border-b border-dashboard-border">
              <th className="text-left py-2 px-1 text-xs text-dashboard-muted font-medium">Symbol</th>
              <th className="text-right py-2 px-1 text-xs text-dashboard-muted font-medium">Qty</th>
              <th className="text-right py-2 px-1 text-xs text-dashboard-muted font-medium">Avg Price</th>
              <th className="text-right py-2 px-1 text-xs text-dashboard-muted font-medium">LTP</th>
              <th className="text-right py-2 px-1 text-xs text-dashboard-muted font-medium">P&L</th>
              <th className="text-right py-2 px-1 text-xs text-dashboard-muted font-medium">Product</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((pos) => {
              const isProfit = pos.pnl >= 0;
              return (
                <tr
                  key={`${pos.symbol}-${pos.product}`}
                  className="border-b border-dashboard-border last:border-0"
                >
                  <td className="py-2 px-1 font-mono text-dashboard-text text-xs">
                    {pos.symbol}
                  </td>
                  <td className={`py-2 px-1 text-right font-mono text-xs ${pos.qty > 0 ? 'text-profit' : 'text-loss'}`}>
                    {pos.qty}
                  </td>
                  <td className="py-2 px-1 text-right font-mono text-dashboard-muted text-xs">
                    ₹{pos.avg_price.toFixed(2)}
                  </td>
                  <td className="py-2 px-1 text-right font-mono text-dashboard-text text-xs">
                    ₹{pos.ltp.toFixed(2)}
                  </td>
                  <td className={`py-2 px-1 text-right font-mono font-medium text-xs ${isProfit ? 'text-profit' : 'text-loss'}`}>
                    {isProfit ? '+' : ''}₹{pos.pnl.toFixed(2)}
                  </td>
                  <td className="py-2 px-1 text-right font-mono text-dashboard-muted text-xs">
                    {pos.product}
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

function AccountSummarySkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[1, 2, 3].map((i) => (
          <Card key={i}>
            <div className="animate-pulse space-y-3" aria-label="Loading account data">
              <div className="h-3 bg-dashboard-border rounded w-1/3" />
              <div className="h-6 bg-dashboard-border rounded w-2/3" />
              <div className="flex justify-between">
                <div className="h-4 bg-dashboard-border rounded w-1/4" />
                <div className="h-4 bg-dashboard-border rounded w-1/4" />
              </div>
            </div>
          </Card>
        ))}
      </div>
      <Card>
        <div className="animate-pulse space-y-3" aria-label="Loading positions">
          <div className="h-3 bg-dashboard-border rounded w-1/4" />
          <div className="h-4 bg-dashboard-border rounded w-full" />
          <div className="h-4 bg-dashboard-border rounded w-full" />
          <div className="h-4 bg-dashboard-border rounded w-3/4" />
        </div>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatNumber(num: number): string {
  return Math.abs(num).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}
