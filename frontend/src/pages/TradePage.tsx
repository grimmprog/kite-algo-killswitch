import { useState, useEffect, useCallback, useRef } from 'react';
import { DashboardLayout } from '../components/dashboard/DashboardLayout';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { TradeConfirmModal } from '../components/trade/TradeConfirmModal';
import { GTTOrderForm } from '../components/trade/GTTOrderForm';
import { DhanOrderForm } from '../components/trade/DhanOrderForm';
import { post } from '../api/client';
import { getOptionChain, searchInstruments } from '../api/instruments';
import type { OptionChainResponse, InstrumentSearchResult } from '../api/types';

type Side = 'BUY' | 'SELL';
type OrderType = 'MARKET' | 'LIMIT';
type Exchange = 'NSE' | 'NFO' | 'BSE' | 'BFO';
type TabId = 'option-chain' | 'stock-search' | 'manual-order' | 'gtt-order' | 'dhan-order';

interface TradeForm {
  symbol: string;
  exchange: Exchange;
  quantity: string;
  side: Side;
  orderType: OrderType;
  price: string;
}

interface TradeResult {
  trade_id?: number;
  order_id?: string;
  status: string;
  message: string;
}

export function TradePage() {
  const [activeTab, setActiveTab] = useState<TabId>('option-chain');
  const [activeBroker, setActiveBroker] = useState<'kite' | 'dhan'>('kite');
  const [form, setForm] = useState<TradeForm>({
    symbol: '',
    exchange: 'NSE',
    quantity: '',
    side: 'BUY',
    orderType: 'MARKET',
    price: '',
  });

  const [showConfirm, setShowConfirm] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  const [result, setResult] = useState<TradeResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleChange = (field: keyof TradeForm, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
    setError(null);
    setResult(null);
  };

  const validateForm = (): string | null => {
    if (!form.symbol.trim()) return 'Symbol is required';
    if (!form.quantity || Number(form.quantity) <= 0) return 'Quantity must be positive';
    if (!Number.isInteger(Number(form.quantity))) return 'Quantity must be a whole number';
    if (form.orderType === 'LIMIT' && (!form.price || Number(form.price) <= 0)) {
      return 'Price is required for LIMIT orders';
    }
    return null;
  };

  const handleSubmit = () => {
    const validationError = validateForm();
    if (validationError) {
      setError(validationError);
      return;
    }
    setShowConfirm(true);
  };

  const handleConfirm = async () => {
    setIsExecuting(true);
    setError(null);

    try {
      const payload = {
        symbol: form.symbol.trim().toUpperCase(),
        exchange: form.exchange,
        quantity: Number(form.quantity),
        side: form.side,
        order_type: form.orderType,
        price: form.orderType === 'LIMIT' ? Number(form.price) : 0,
        broker: activeBroker,
        risk_snapshot: {},
      };

      const response = await post<TradeResult>('/api/v1/trades/execute', payload);
      setResult(response);
      setShowConfirm(false);
      setForm({
        symbol: '',
        exchange: 'NSE',
        quantity: '',
        side: 'BUY',
        orderType: 'MARKET',
        price: '',
      });
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Trade execution failed. Please try again.';
      setError(message);
      setShowConfirm(false);
    } finally {
      setIsExecuting(false);
    }
  };

  // Pre-fill trade form from option chain or search
  const prefillTrade = (symbol: string, exchange: Exchange, lotSize: number) => {
    setForm({
      symbol,
      exchange,
      quantity: String(lotSize),
      side: 'BUY',
      orderType: 'MARKET',
      price: '',
    });
    setActiveTab('manual-order');
    setError(null);
    setResult(null);
  };

  const tabs: { id: TabId; label: string }[] = [
    { id: 'option-chain', label: 'Option Chain' },
    { id: 'stock-search', label: 'Stock Search' },
    { id: 'manual-order', label: 'Manual Order' },
    { id: 'gtt-order', label: 'GTT (Kite)' },
    { id: 'dhan-order', label: 'Dhan + Trail SL' },
  ];

  return (
    <DashboardLayout>
      <div className="space-y-4">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold text-dashboard-text">Execute Trade</h1>
            <p className="text-sm text-dashboard-muted mt-1">
              Browse option chains, search stocks, or place manual orders
            </p>
          </div>
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
        </div>

        {/* Tab Bar */}
        <div className="flex gap-1 bg-dashboard-card border border-dashboard-border rounded-lg p-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? 'bg-blue-600 text-white'
                  : 'text-dashboard-muted hover:text-dashboard-text hover:bg-dashboard-bg'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        {activeTab === 'option-chain' && (
          <OptionChainTab onSelect={prefillTrade} />
        )}

        {activeTab === 'stock-search' && (
          <StockSearchTab onSelect={prefillTrade} />
        )}

        {activeTab === 'manual-order' && (
          <div className="max-w-2xl mx-auto space-y-6">
            {/* Success result */}
            {result && result.status === 'success' && (
              <div className="bg-profit/10 border border-profit/30 rounded-lg p-4" role="alert">
                <p className="text-sm font-medium text-profit">Trade executed successfully</p>
                {result.order_id && (
                  <p className="text-xs text-dashboard-muted mt-1">Order ID: {result.order_id}</p>
                )}
                <p className="text-xs text-dashboard-muted mt-0.5">{result.message}</p>
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="bg-loss/10 border border-loss/30 rounded-lg p-3 text-sm text-loss" role="alert">
                {error}
              </div>
            )}

            {/* Trade Form */}
            <Card title="Trade Details" padding="lg">
              <div className="space-y-4">
                <Input
                  label="Symbol"
                  placeholder="e.g. NIFTY24DEC19000CE"
                  value={form.symbol}
                  onChange={(e) => handleChange('symbol', e.target.value)}
                />

                <div>
                  <label htmlFor="exchange" className="block text-sm font-medium text-dashboard-text mb-1.5">
                    Exchange
                  </label>
                  <select
                    id="exchange"
                    value={form.exchange}
                    onChange={(e) => handleChange('exchange', e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-dashboard-bg border border-dashboard-border text-dashboard-text text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="NSE">NSE</option>
                    <option value="NFO">NFO</option>
                    <option value="BSE">BSE</option>
                    <option value="BFO">BFO</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-dashboard-text mb-1.5">Side</label>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => handleChange('side', 'BUY')}
                      className={`flex-1 py-2 rounded-lg text-sm font-semibold transition-colors ${
                        form.side === 'BUY'
                          ? 'bg-profit text-white'
                          : 'bg-dashboard-bg border border-dashboard-border text-dashboard-muted hover:text-dashboard-text'
                      }`}
                    >
                      BUY
                    </button>
                    <button
                      type="button"
                      onClick={() => handleChange('side', 'SELL')}
                      className={`flex-1 py-2 rounded-lg text-sm font-semibold transition-colors ${
                        form.side === 'SELL'
                          ? 'bg-loss text-white'
                          : 'bg-dashboard-bg border border-dashboard-border text-dashboard-muted hover:text-dashboard-text'
                      }`}
                    >
                      SELL
                    </button>
                  </div>
                </div>

                <Input
                  label="Quantity"
                  type="number"
                  placeholder="e.g. 50"
                  min="1"
                  step="1"
                  value={form.quantity}
                  onChange={(e) => handleChange('quantity', e.target.value)}
                />

                <div>
                  <label htmlFor="order-type" className="block text-sm font-medium text-dashboard-text mb-1.5">
                    Order Type
                  </label>
                  <select
                    id="order-type"
                    value={form.orderType}
                    onChange={(e) => handleChange('orderType', e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-dashboard-bg border border-dashboard-border text-dashboard-text text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="MARKET">MARKET</option>
                    <option value="LIMIT">LIMIT</option>
                  </select>
                </div>

                {form.orderType === 'LIMIT' && (
                  <Input
                    label="Price"
                    type="number"
                    placeholder="Enter limit price"
                    min="0.01"
                    step="0.05"
                    value={form.price}
                    onChange={(e) => handleChange('price', e.target.value)}
                  />
                )}

                <Button variant="primary" size="lg" className="w-full mt-4" onClick={handleSubmit}>
                  Review & Execute
                </Button>
              </div>
            </Card>

            {/* Risk Disclosure */}
            <div className="bg-dashboard-bg border border-dashboard-border rounded-lg p-4">
              <p className="text-xs text-dashboard-muted leading-relaxed">
                <strong className="text-dashboard-text">Risk Disclosure:</strong> Trading in derivatives involves
                substantial risk of loss. This platform is an execution tool and does not provide investment advice.
                All trades require your manual confirmation.
              </p>
            </div>
          </div>
        )}

        {activeTab === 'gtt-order' && (
          <GTTOrderForm
            prefillSymbol={form.symbol || undefined}
            prefillExchange={form.exchange || undefined}
            prefillPrice={form.price ? Number(form.price) : undefined}
          />
        )}

        {activeTab === 'dhan-order' && (
          <DhanOrderForm
            prefillSymbol={form.symbol || undefined}
            prefillPrice={form.price ? Number(form.price) : undefined}
          />
        )}
      </div>

      {/* Confirmation Modal */}
      {showConfirm && (
        <TradeConfirmModal
          trade={{
            symbol: form.symbol.trim().toUpperCase(),
            exchange: form.exchange,
            quantity: Number(form.quantity),
            side: form.side,
            orderType: form.orderType,
            price: Number(form.price) || 0,
          }}
          isLoading={isExecuting}
          onConfirm={handleConfirm}
          onCancel={() => setShowConfirm(false)}
        />
      )}
    </DashboardLayout>
  );
}

// ===========================================================================
// Option Chain Tab
// ===========================================================================

function OptionChainTab({ onSelect }: { onSelect: (symbol: string, exchange: Exchange, lotSize: number) => void }) {
  const [selectedIndex, setSelectedIndex] = useState<'NIFTY' | 'BANKNIFTY'>('NIFTY');
  const [data, setData] = useState<OptionChainResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const result = await getOptionChain(selectedIndex);
      setData(result);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load option chain';
      setError(message);
    }
  }, [selectedIndex]);

  // Initial fetch
  useEffect(() => {
    setLoading(true);
    fetchData().finally(() => setLoading(false));
  }, [fetchData]);

  // Auto-refresh every 10 seconds during market hours (9:15 - 15:30 IST)
  useEffect(() => {
    const isMarketHours = () => {
      const now = new Date();
      // Convert to IST (UTC+5:30)
      const istOffset = 5.5 * 60;
      const utcMinutes = now.getUTCHours() * 60 + now.getUTCMinutes();
      const istMinutes = utcMinutes + istOffset;
      const marketOpen = 9 * 60 + 15;  // 9:15
      const marketClose = 15 * 60 + 30; // 15:30
      const day = now.getDay();
      return day >= 1 && day <= 5 && istMinutes >= marketOpen && istMinutes <= marketClose;
    };

    if (isMarketHours()) {
      intervalRef.current = setInterval(fetchData, 10000);
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [fetchData]);

  const handleCellClick = (symbol: string, lotSize: number) => {
    if (symbol) {
      onSelect(symbol, 'NFO', lotSize);
    }
  };

  // Find ATM strike
  const atmStrike = data
    ? data.strikes.reduce((closest, s) =>
        Math.abs(s.strike - data.spot_price) < Math.abs(closest.strike - data.spot_price) ? s : closest,
        data.strikes[0]
      )?.strike
    : 0;

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          {(['NIFTY', 'BANKNIFTY'] as const).map((idx) => (
            <button
              key={idx}
              onClick={() => setSelectedIndex(idx)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                selectedIndex === idx
                  ? 'bg-blue-600 text-white'
                  : 'bg-dashboard-card border border-dashboard-border text-dashboard-muted hover:text-dashboard-text'
              }`}
            >
              {idx}
            </button>
          ))}
        </div>

        {data && (
          <div className="text-right">
            <p className="text-sm text-dashboard-text font-mono font-medium">
              Spot: ₹{data.spot_price.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </p>
            <p className="text-xs text-dashboard-muted">
              Expiry: {data.expiry} · Lot: {data.lot_size}
            </p>
          </div>
        )}
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-loss/10 border border-loss/30 rounded-lg p-3 text-sm text-loss">
          {error}
          <button onClick={fetchData} className="ml-2 underline">Retry</button>
        </div>
      )}

      {/* Option Chain Table */}
      {data && !loading && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="border-b border-dashboard-border">
                <th colSpan={4} className="text-center py-2 text-profit font-semibold text-sm">
                  CALLS (CE)
                </th>
                <th className="py-2 text-dashboard-text font-semibold text-sm">Strike</th>
                <th colSpan={4} className="text-center py-2 text-loss font-semibold text-sm">
                  PUTS (PE)
                </th>
              </tr>
              <tr className="border-b border-dashboard-border text-dashboard-muted">
                <th className="py-1.5 px-2 text-right">OI</th>
                <th className="py-1.5 px-2 text-right">Vol</th>
                <th className="py-1.5 px-2 text-right">Bid</th>
                <th className="py-1.5 px-2 text-right font-semibold text-profit">LTP</th>
                <th className="py-1.5 px-2 text-center">Price</th>
                <th className="py-1.5 px-2 text-left font-semibold text-loss">LTP</th>
                <th className="py-1.5 px-2 text-left">Ask</th>
                <th className="py-1.5 px-2 text-left">Vol</th>
                <th className="py-1.5 px-2 text-left">OI</th>
              </tr>
            </thead>
            <tbody>
              {data.strikes.map((strike) => {
                const isATM = strike.strike === atmStrike;
                return (
                  <tr
                    key={strike.strike}
                    className={`border-b border-dashboard-border/50 hover:bg-dashboard-bg/50 ${
                      isATM ? 'bg-blue-500/10 border-blue-500/30' : ''
                    }`}
                  >
                    {/* CE side */}
                    <td className="py-1.5 px-2 text-right text-dashboard-muted font-mono">
                      {strike.ce_oi ? (strike.ce_oi / 1000).toFixed(0) + 'K' : '-'}
                    </td>
                    <td className="py-1.5 px-2 text-right text-dashboard-muted font-mono">
                      {strike.ce_volume ? (strike.ce_volume / 1000).toFixed(0) + 'K' : '-'}
                    </td>
                    <td className="py-1.5 px-2 text-right text-dashboard-muted font-mono">
                      {strike.ce_bid || '-'}
                    </td>
                    <td
                      className="py-1.5 px-2 text-right font-mono font-medium text-profit cursor-pointer hover:bg-profit/20 rounded"
                      onClick={() => handleCellClick(strike.ce_symbol, data.lot_size)}
                      title={`Click to trade ${strike.ce_symbol}`}
                    >
                      {strike.ce_ltp || '-'}
                    </td>

                    {/* Strike */}
                    <td className={`py-1.5 px-2 text-center font-mono font-bold ${
                      isATM ? 'text-blue-400' : 'text-dashboard-text'
                    }`}>
                      {strike.strike}
                      {isATM && <span className="ml-1 text-[10px] text-blue-400">ATM</span>}
                    </td>

                    {/* PE side */}
                    <td
                      className="py-1.5 px-2 text-left font-mono font-medium text-loss cursor-pointer hover:bg-loss/20 rounded"
                      onClick={() => handleCellClick(strike.pe_symbol, data.lot_size)}
                      title={`Click to trade ${strike.pe_symbol}`}
                    >
                      {strike.pe_ltp || '-'}
                    </td>
                    <td className="py-1.5 px-2 text-left text-dashboard-muted font-mono">
                      {strike.pe_ask || '-'}
                    </td>
                    <td className="py-1.5 px-2 text-left text-dashboard-muted font-mono">
                      {strike.pe_volume ? (strike.pe_volume / 1000).toFixed(0) + 'K' : '-'}
                    </td>
                    <td className="py-1.5 px-2 text-left text-dashboard-muted font-mono">
                      {strike.pe_oi ? (strike.pe_oi / 1000).toFixed(0) + 'K' : '-'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Legend */}
      <p className="text-xs text-dashboard-muted">
        Click on any LTP value to pre-fill the trade form. OI and Volume shown in thousands.
      </p>
    </div>
  );
}

// ===========================================================================
// Stock Search Tab
// ===========================================================================

function StockSearchTab({ onSelect }: { onSelect: (symbol: string, exchange: Exchange, lotSize: number) => void }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<InstrumentSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleSearch = useCallback(async (searchQuery: string) => {
    if (searchQuery.length < 2) {
      setResults([]);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const data = await searchInstruments(searchQuery, 'NSE');
      setResults(data);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Search failed';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleInputChange = (value: string) => {
    setQuery(value);

    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    debounceRef.current = setTimeout(() => {
      handleSearch(value.trim());
    }, 300);
  };

  // Cleanup debounce on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, []);

  const handleSelect = (result: InstrumentSearchResult) => {
    const exchange = (result.exchange || 'NSE') as Exchange;
    const lotSize = result.lot_size || 1;
    onSelect(result.tradingsymbol, exchange, lotSize);
  };

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      <Card title="Search Instruments" padding="lg">
        <div className="space-y-4">
          <Input
            label="Search"
            placeholder="Type stock name or symbol (e.g. RELIANCE, TCS, INFY)"
            value={query}
            onChange={(e) => handleInputChange(e.target.value)}
          />

          {/* Loading */}
          {loading && (
            <div className="flex items-center gap-2 text-sm text-dashboard-muted">
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-500" />
              Searching...
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="text-sm text-loss">{error}</div>
          )}

          {/* Results */}
          {results.length > 0 && (
            <div className="border border-dashboard-border rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-dashboard-bg border-b border-dashboard-border text-dashboard-muted text-xs">
                    <th className="py-2 px-3 text-left">Symbol</th>
                    <th className="py-2 px-3 text-left">Name</th>
                    <th className="py-2 px-3 text-left">Exchange</th>
                    <th className="py-2 px-3 text-right">LTP</th>
                    <th className="py-2 px-3 text-right">Change %</th>
                    <th className="py-2 px-3 text-center">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((r) => (
                    <tr
                      key={`${r.exchange}:${r.tradingsymbol}`}
                      className="border-b border-dashboard-border/50 hover:bg-dashboard-bg/50 cursor-pointer"
                      onClick={() => handleSelect(r)}
                    >
                      <td className="py-2 px-3 font-mono font-medium text-dashboard-text">
                        {r.tradingsymbol}
                      </td>
                      <td className="py-2 px-3 text-dashboard-muted truncate max-w-[200px]">
                        {r.name}
                      </td>
                      <td className="py-2 px-3 text-dashboard-muted">
                        {r.exchange}
                      </td>
                      <td className="py-2 px-3 text-right font-mono text-dashboard-text">
                        {r.last_price ? `₹${r.last_price.toLocaleString('en-IN')}` : '-'}
                      </td>
                      <td className={`py-2 px-3 text-right font-mono ${
                        r.change_percent > 0 ? 'text-profit' : r.change_percent < 0 ? 'text-loss' : 'text-dashboard-muted'
                      }`}>
                        {r.change_percent ? `${r.change_percent > 0 ? '+' : ''}${r.change_percent.toFixed(2)}%` : '-'}
                      </td>
                      <td className="py-2 px-3 text-center">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleSelect(r);
                          }}
                          className="px-2 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
                        >
                          Trade
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Empty state */}
          {query.length >= 2 && !loading && results.length === 0 && !error && (
            <p className="text-sm text-dashboard-muted text-center py-4">
              No instruments found for "{query}"
            </p>
          )}

          {query.length < 2 && (
            <p className="text-sm text-dashboard-muted text-center py-4">
              Type at least 2 characters to search
            </p>
          )}
        </div>
      </Card>
    </div>
  );
}
