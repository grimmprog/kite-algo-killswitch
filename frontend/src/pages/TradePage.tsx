import { useState, useEffect, useCallback, useRef } from 'react';
import { DashboardLayout } from '../components/dashboard/DashboardLayout';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { TradeConfirmModal } from '../components/trade/TradeConfirmModal';
import { GTTOrderForm } from '../components/trade/GTTOrderForm';
import { DhanOrderForm } from '../components/trade/DhanOrderForm';
import { post } from '../api/client';
import { getOptionChain } from '../api/instruments';
import type { OptionChainResponse } from '../api/types';

type Side = 'BUY' | 'SELL';
type OrderType = 'MARKET' | 'LIMIT';
type Exchange = 'NSE' | 'NFO' | 'BSE' | 'BFO';
type TabId = 'option-chain' | 'quick-order' | 'gtt-order' | 'dhan-order';
type IndexName = 'NIFTY' | 'BANKNIFTY' | 'SENSEX';

// Index-specific lot sizes and exchanges
const INDEX_CONFIG: Record<IndexName, { lotSize: number; exchange: Exchange; strikeStep: number }> = {
  NIFTY: { lotSize: 75, exchange: 'NFO', strikeStep: 50 },
  BANKNIFTY: { lotSize: 30, exchange: 'NFO', strikeStep: 100 },
  SENSEX: { lotSize: 20, exchange: 'BFO', strikeStep: 100 },
};

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
  const [selectedIndex, setSelectedIndex] = useState<IndexName>('NIFTY');
  const [form, setForm] = useState<TradeForm>({
    symbol: '',
    exchange: 'NFO',
    quantity: '75',
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

  // Pre-fill trade form from option chain
  const prefillTrade = (symbol: string, exchange: Exchange, lotSize: number) => {
    setForm({
      symbol,
      exchange,
      quantity: String(lotSize),
      side: 'BUY',
      orderType: 'MARKET',
      price: '',
    });
    setActiveTab('quick-order');
    setError(null);
    setResult(null);
  };

  // Update lot size when index changes
  const handleIndexChange = (index: IndexName) => {
    setSelectedIndex(index);
    const config = INDEX_CONFIG[index];
    setForm(prev => ({
      ...prev,
      exchange: config.exchange,
      quantity: String(config.lotSize),
    }));
  };

  const tabs: { id: TabId; label: string }[] = [
    { id: 'option-chain', label: 'Option Chain' },
    { id: 'quick-order', label: 'Quick Order' },
    { id: 'gtt-order', label: 'GTT (Kite)' },
    { id: 'dhan-order', label: 'Dhan + Trail SL' },
  ];

  return (
    <DashboardLayout>
      <div className="space-y-4">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold text-dashboard-text">Index Options Trading</h1>
            <p className="text-sm text-dashboard-muted mt-1">
              NIFTY · BANKNIFTY · SENSEX — Option chains, GTT orders, trailing SL
            </p>
          </div>
          {/* Index + Broker Toggle */}
          <div className="flex items-center gap-3">
            {/* Index Selector */}
            <div className="flex items-center gap-1 bg-dashboard-card border border-dashboard-border rounded-lg p-1">
              {(Object.keys(INDEX_CONFIG) as IndexName[]).map((idx) => (
                <button
                  key={idx}
                  onClick={() => handleIndexChange(idx)}
                  className={`px-3 py-1.5 text-xs font-bold rounded-md transition-colors ${
                    selectedIndex === idx
                      ? 'bg-purple-600 text-white'
                      : 'text-dashboard-muted hover:text-dashboard-text'
                  }`}
                >
                  {idx === 'BANKNIFTY' ? 'BNIFTY' : idx}
                </button>
              ))}
            </div>
            {/* Broker Toggle */}
            <div className="flex items-center gap-1 bg-dashboard-card border border-dashboard-border rounded-lg p-1">
              <button
                onClick={() => setActiveBroker('kite')}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                  activeBroker === 'kite'
                    ? 'bg-blue-600 text-white'
                    : 'text-dashboard-muted hover:text-dashboard-text'
                }`}
              >
                Kite
              </button>
              <button
                onClick={() => setActiveBroker('dhan')}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                  activeBroker === 'dhan'
                    ? 'bg-blue-600 text-white'
                    : 'text-dashboard-muted hover:text-dashboard-text'
                }`}
              >
                Dhan
              </button>
            </div>
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
          <OptionChainTab onSelect={prefillTrade} selectedIndex={selectedIndex} />
        )}

        {activeTab === 'quick-order' && (
          <div className="max-w-2xl mx-auto space-y-6">
            {/* Index info badge */}
            <div className="flex items-center gap-3 bg-dashboard-card border border-dashboard-border rounded-lg p-3">
              <span className="text-xs font-bold text-purple-400 bg-purple-500/10 px-2 py-1 rounded">
                {selectedIndex}
              </span>
              <span className="text-xs text-dashboard-muted">
                Lot: {INDEX_CONFIG[selectedIndex].lotSize} · Exchange: {INDEX_CONFIG[selectedIndex].exchange} · Strike step: {INDEX_CONFIG[selectedIndex].strikeStep}
              </span>
            </div>

            {/* Success result */}
            {result && result.status === 'success' && (
              <div className="bg-profit/10 border border-profit/30 rounded-lg p-4" role="alert">
                <p className="text-sm font-medium text-profit">Trade executed successfully</p>
                {result.order_id && (
                  <p className="text-xs text-dashboard-muted mt-1">Order ID: {result.order_id}</p>
                )}
              </div>
            )}

            {error && (
              <div className="bg-loss/10 border border-loss/30 rounded-lg p-3 text-sm text-loss" role="alert">
                {error}
              </div>
            )}

            {/* Quick Order Form — optimized for index options */}
            <Card title="Quick Order" padding="lg">
              <div className="space-y-4">
                <Input
                  label="Symbol"
                  placeholder={`e.g. ${selectedIndex === 'BANKNIFTY' ? 'BANKNIFTY2470952000CE' : selectedIndex + '2470924400CE'}`}
                  value={form.symbol}
                  onChange={(e) => handleChange('symbol', e.target.value)}
                />

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-sm font-medium text-dashboard-text mb-1.5">Exchange</label>
                    <select
                      value={form.exchange}
                      onChange={(e) => handleChange('exchange', e.target.value)}
                      className="w-full px-3 py-2 rounded-lg bg-dashboard-bg border border-dashboard-border text-dashboard-text text-sm font-mono"
                    >
                      <option value="NFO">NFO</option>
                      <option value="BFO">BFO</option>
                      <option value="NSE">NSE</option>
                    </select>
                  </div>
                  <Input
                    label="Lots"
                    type="number"
                    min="1"
                    value={String(Math.round(Number(form.quantity) / INDEX_CONFIG[selectedIndex].lotSize) || 1)}
                    onChange={(e) => handleChange('quantity', String(Number(e.target.value) * INDEX_CONFIG[selectedIndex].lotSize))}
                  />
                </div>

                <div className="text-xs text-dashboard-muted">
                  Quantity: <span className="font-mono font-medium text-dashboard-text">{form.quantity}</span> ({Math.round(Number(form.quantity) / INDEX_CONFIG[selectedIndex].lotSize)} lot × {INDEX_CONFIG[selectedIndex].lotSize})
                </div>

                {/* Side — large buttons */}
                <div className="flex gap-3">
                  <button
                    onClick={() => handleChange('side', 'BUY')}
                    className={`flex-1 py-3 rounded-lg text-sm font-bold transition-colors ${
                      form.side === 'BUY'
                        ? 'bg-profit text-white shadow-lg shadow-profit/20'
                        : 'bg-dashboard-bg border border-dashboard-border text-dashboard-muted'
                    }`}
                  >BUY</button>
                  <button
                    onClick={() => handleChange('side', 'SELL')}
                    className={`flex-1 py-3 rounded-lg text-sm font-bold transition-colors ${
                      form.side === 'SELL'
                        ? 'bg-loss text-white shadow-lg shadow-loss/20'
                        : 'bg-dashboard-bg border border-dashboard-border text-dashboard-muted'
                    }`}
                  >SELL</button>
                </div>

                {/* Order type */}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-sm font-medium text-dashboard-text mb-1.5">Type</label>
                    <select
                      value={form.orderType}
                      onChange={(e) => handleChange('orderType', e.target.value)}
                      className="w-full px-3 py-2 rounded-lg bg-dashboard-bg border border-dashboard-border text-dashboard-text text-sm font-mono"
                    >
                      <option value="MARKET">MARKET</option>
                      <option value="LIMIT">LIMIT</option>
                    </select>
                  </div>
                  {form.orderType === 'LIMIT' && (
                    <Input label="Price" type="number" step="0.05" value={form.price} onChange={(e) => handleChange('price', e.target.value)} />
                  )}
                </div>

                <Button variant="primary" size="lg" className="w-full mt-2" onClick={handleSubmit}>
                  Review & Execute ({activeBroker.toUpperCase()})
                </Button>
              </div>
            </Card>
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

function OptionChainTab({ onSelect, selectedIndex }: { onSelect: (symbol: string, exchange: Exchange, lotSize: number) => void; selectedIndex: IndexName }) {
  const [localIndex, setLocalIndex] = useState<IndexName>(selectedIndex);
  const [data, setData] = useState<OptionChainResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Sync with parent selectedIndex
  useEffect(() => {
    setLocalIndex(selectedIndex);
  }, [selectedIndex]);

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const result = await getOptionChain(localIndex);
      setData(result);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load option chain';
      setError(message);
    }
  }, [localIndex]);

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
      const exchange = localIndex === 'SENSEX' ? 'BFO' : 'NFO';
      onSelect(symbol, exchange as Exchange, lotSize);
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
          {(['NIFTY', 'BANKNIFTY', 'SENSEX'] as const).map((idx) => (
            <button
              key={idx}
              onClick={() => setLocalIndex(idx)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                localIndex === idx
                  ? 'bg-purple-600 text-white'
                  : 'bg-dashboard-card border border-dashboard-border text-dashboard-muted hover:text-dashboard-text'
              }`}
            >
              {idx === 'BANKNIFTY' ? 'BANK NIFTY' : idx}
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
        Click on any LTP to pre-fill the Quick Order form. OI and Volume in thousands. Lot size: {data?.lot_size || INDEX_CONFIG[localIndex].lotSize}
      </p>
    </div>
  );
}
