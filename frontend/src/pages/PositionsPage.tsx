import { useState, useEffect, useMemo, useCallback } from 'react';
import { DashboardLayout } from '../components/dashboard/DashboardLayout';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { useWebSocket } from '../contexts/WebSocketContext';
import { get, post } from '../api/client';

interface Position {
  symbol: string;
  quantity: number;
  entryPrice: number;
  currentPrice: number;
  pnl: number;
  marginUsed: number;
  exchange?: string;
}

type SortKey = 'symbol' | 'pnl' | 'marginUsed';
type SortDirection = 'asc' | 'desc';
type ExchangeFilter = 'ALL' | 'NSE' | 'NFO' | 'BSE' | 'BFO';
type PnlFilter = 'ALL' | 'PROFIT' | 'LOSS';

export function PositionsPage() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>('symbol');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');
  const [exchangeFilter, setExchangeFilter] = useState<ExchangeFilter>('ALL');
  const [pnlFilter, setPnlFilter] = useState<PnlFilter>('ALL');
  const [exitingSymbol, setExitingSymbol] = useState<string | null>(null);
  const [confirmExit, setConfirmExit] = useState<string | null>(null);
  const [activeBroker, setActiveBroker] = useState<'kite' | 'dhan'>('kite');

  const { positions: wsPositions } = useWebSocket();

  // Fetch initial positions from REST API
  useEffect(() => {
    async function fetchPositions() {
      try {
        setLoading(true);
        const endpoint = activeBroker === 'dhan'
          ? '/api/v1/dashboard/dhan-account'
          : '/api/v1/positions';
        if (activeBroker === 'dhan') {
          // For Dhan, extract positions from the dashboard endpoint
          const data = await get<{ positions: Array<{ symbol: string; qty: number; avg_price: number; ltp: number; pnl: number; product: string }> }>(endpoint);
          const mapped = (data.positions || []).map((p) => ({
            symbol: p.symbol || '',
            quantity: p.qty || 0,
            entryPrice: p.avg_price || 0,
            currentPrice: p.ltp || 0,
            pnl: p.pnl || 0,
            marginUsed: 0,
            exchange: 'NSE',
          }));
          setPositions(mapped);
        } else {
          const data = await get<Position[]>(endpoint);
          setPositions(data);
        }
        setError(null);
      } catch (err) {
        setError('Failed to load positions. Please try again.');
      } finally {
        setLoading(false);
      }
    }
    fetchPositions();
  }, [activeBroker]);

  // Update positions from WebSocket
  useEffect(() => {
    if (wsPositions.length > 0) {
      setPositions((prev) => {
        const updated = [...prev];
        for (const wsPos of wsPositions) {
          const idx = updated.findIndex((p) => p.symbol === wsPos.symbol);
          if (idx >= 0) {
            updated[idx] = { ...updated[idx], ...wsPos };
          } else {
            updated.push({ ...wsPos, marginUsed: 0, exchange: 'NSE' });
          }
        }
        return updated;
      });
    }
  }, [wsPositions]);

  // Sorting
  const handleSort = useCallback(
    (key: SortKey) => {
      if (sortKey === key) {
        setSortDirection((d) => (d === 'asc' ? 'desc' : 'asc'));
      } else {
        setSortKey(key);
        setSortDirection('asc');
      }
    },
    [sortKey]
  );

  // Filtered and sorted positions
  const filteredPositions = useMemo(() => {
    let filtered = [...positions];

    // Exchange filter
    if (exchangeFilter !== 'ALL') {
      filtered = filtered.filter((p) => p.exchange === exchangeFilter);
    }

    // P&L filter
    if (pnlFilter === 'PROFIT') {
      filtered = filtered.filter((p) => p.pnl > 0);
    } else if (pnlFilter === 'LOSS') {
      filtered = filtered.filter((p) => p.pnl < 0);
    }

    // Sort
    filtered.sort((a, b) => {
      let cmp = 0;
      if (sortKey === 'symbol') {
        cmp = a.symbol.localeCompare(b.symbol);
      } else if (sortKey === 'pnl') {
        cmp = a.pnl - b.pnl;
      } else if (sortKey === 'marginUsed') {
        cmp = a.marginUsed - b.marginUsed;
      }
      return sortDirection === 'asc' ? cmp : -cmp;
    });

    return filtered;
  }, [positions, exchangeFilter, pnlFilter, sortKey, sortDirection]);

  // Exit position
  const handleExitPosition = async (symbol: string) => {
    const position = positions.find((p) => p.symbol === symbol);
    if (!position) return;

    setExitingSymbol(symbol);
    try {
      await post('/api/v1/trades/execute', {
        symbol: position.symbol,
        exchange: position.exchange || 'NSE',
        quantity: Math.abs(position.quantity),
        side: position.quantity > 0 ? 'SELL' : 'BUY',
        order_type: 'MARKET',
        price: 0,
      });
      // Remove from local state on success
      setPositions((prev) => prev.filter((p) => p.symbol !== symbol));
    } catch {
      setError(`Failed to exit position for ${symbol}`);
    } finally {
      setExitingSymbol(null);
      setConfirmExit(null);
    }
  };

  const SortIndicator = ({ column }: { column: SortKey }) => {
    if (sortKey !== column) return <span className="text-dashboard-muted ml-1">↕</span>;
    return <span className="text-blue-400 ml-1">{sortDirection === 'asc' ? '↑' : '↓'}</span>;
  };

  const totalPnl = positions.reduce((sum, p) => sum + p.pnl, 0);
  const totalMargin = positions.reduce((sum, p) => sum + p.marginUsed, 0);

  return (
    <DashboardLayout>
      <div className="space-y-4">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold text-dashboard-text">Positions</h1>
            <p className="text-sm text-dashboard-muted">
              {positions.length} open position{positions.length !== 1 ? 's' : ''}
            </p>
          </div>
          <div className="flex items-center gap-4">
            {/* Broker Toggle */}
            <div className="flex items-center gap-1 bg-dashboard-card border border-dashboard-border rounded-lg p-1">
              <button
                onClick={() => setActiveBroker('kite')}
                className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors ${
                  activeBroker === 'kite'
                    ? 'bg-blue-600 text-white'
                    : 'text-dashboard-muted hover:text-dashboard-text'
                }`}
              >
                Kite
              </button>
              <button
                onClick={() => setActiveBroker('dhan')}
                className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors ${
                  activeBroker === 'dhan'
                    ? 'bg-blue-600 text-white'
                    : 'text-dashboard-muted hover:text-dashboard-text'
                }`}
              >
                Dhan
              </button>
            </div>
            <div className="flex items-center gap-4 text-sm">
              <span className="text-dashboard-muted">
                Total P&L:{' '}
                <span className={`font-mono font-semibold ${totalPnl >= 0 ? 'text-profit' : 'text-loss'}`}>
                  ₹{totalPnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </span>
              </span>
              <span className="text-dashboard-muted">
                Margin:{' '}
                <span className="font-mono text-dashboard-text">
                  ₹{totalMargin.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </span>
              </span>
            </div>
          </div>
        </div>

        {/* Filters */}
        <Card padding="sm">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <label className="text-xs text-dashboard-muted" htmlFor="exchange-filter">Exchange:</label>
              <select
                id="exchange-filter"
                value={exchangeFilter}
                onChange={(e) => setExchangeFilter(e.target.value as ExchangeFilter)}
                className="bg-dashboard-bg border border-dashboard-border rounded-lg px-2 py-1 text-sm text-dashboard-text focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="ALL">All</option>
                <option value="NSE">NSE</option>
                <option value="NFO">NFO</option>
                <option value="BSE">BSE</option>
                <option value="BFO">BFO</option>
              </select>
            </div>
            <div className="flex items-center gap-2">
              <label className="text-xs text-dashboard-muted" htmlFor="pnl-filter">P&L:</label>
              <select
                id="pnl-filter"
                value={pnlFilter}
                onChange={(e) => setPnlFilter(e.target.value as PnlFilter)}
                className="bg-dashboard-bg border border-dashboard-border rounded-lg px-2 py-1 text-sm text-dashboard-text focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="ALL">All</option>
                <option value="PROFIT">Profit Only</option>
                <option value="LOSS">Loss Only</option>
              </select>
            </div>
          </div>
        </Card>

        {/* Error */}
        {error && (
          <div className="bg-loss/10 border border-loss/30 rounded-lg p-3 text-sm text-loss" role="alert">
            {error}
            <button onClick={() => setError(null)} className="ml-2 underline">Dismiss</button>
          </div>
        )}

        {/* Table */}
        <Card padding="none">
          {loading ? (
            <div className="p-8 text-center text-dashboard-muted">Loading positions...</div>
          ) : filteredPositions.length === 0 ? (
            <div className="p-8 text-center text-dashboard-muted">No positions found</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm" role="table">
                <thead>
                  <tr className="border-b border-dashboard-border text-left">
                    <th
                      className="px-4 py-3 text-xs font-medium text-dashboard-muted cursor-pointer select-none hover:text-dashboard-text"
                      onClick={() => handleSort('symbol')}
                    >
                      Symbol <SortIndicator column="symbol" />
                    </th>
                    <th className="px-4 py-3 text-xs font-medium text-dashboard-muted text-right">Qty</th>
                    <th className="px-4 py-3 text-xs font-medium text-dashboard-muted text-right">Entry Price</th>
                    <th className="px-4 py-3 text-xs font-medium text-dashboard-muted text-right">Current Price</th>
                    <th
                      className="px-4 py-3 text-xs font-medium text-dashboard-muted text-right cursor-pointer select-none hover:text-dashboard-text"
                      onClick={() => handleSort('pnl')}
                    >
                      P&L <SortIndicator column="pnl" />
                    </th>
                    <th
                      className="px-4 py-3 text-xs font-medium text-dashboard-muted text-right cursor-pointer select-none hover:text-dashboard-text"
                      onClick={() => handleSort('marginUsed')}
                    >
                      Margin Used <SortIndicator column="marginUsed" />
                    </th>
                    <th className="px-4 py-3 text-xs font-medium text-dashboard-muted text-right">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredPositions.map((pos) => (
                    <tr key={pos.symbol} className="border-b border-dashboard-border/50 hover:bg-dashboard-bg/50">
                      <td className="px-4 py-3 font-medium text-dashboard-text">{pos.symbol}</td>
                      <td className="px-4 py-3 text-right font-mono text-dashboard-text">
                        {pos.quantity}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-dashboard-text">
                        ₹{pos.entryPrice.toFixed(2)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-dashboard-text">
                        ₹{pos.currentPrice.toFixed(2)}
                      </td>
                      <td className={`px-4 py-3 text-right font-mono font-semibold ${pos.pnl >= 0 ? 'text-profit' : 'text-loss'}`}>
                        ₹{pos.pnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-dashboard-text">
                        ₹{pos.marginUsed.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {confirmExit === pos.symbol ? (
                          <div className="flex items-center justify-end gap-2">
                            <Button
                              variant="danger"
                              size="sm"
                              isLoading={exitingSymbol === pos.symbol}
                              onClick={() => handleExitPosition(pos.symbol)}
                            >
                              Confirm
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setConfirmExit(null)}
                            >
                              Cancel
                            </Button>
                          </div>
                        ) : (
                          <Button
                            variant="danger"
                            size="sm"
                            onClick={() => setConfirmExit(pos.symbol)}
                          >
                            Exit
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </DashboardLayout>
  );
}
