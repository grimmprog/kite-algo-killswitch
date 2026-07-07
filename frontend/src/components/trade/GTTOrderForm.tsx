import { useState } from 'react';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { placeGTTOrder, estimateMargin } from '../../api/orders';
import type { GTTOrderRequest, MarginEstimateResponse } from '../../api/orders';
import { MarginDisplay } from './MarginDisplay';

interface GTTOrderFormProps {
  prefillSymbol?: string;
  prefillExchange?: string;
  prefillPrice?: number;
}

export function GTTOrderForm({ prefillSymbol, prefillExchange, prefillPrice }: GTTOrderFormProps) {
  const [symbol, setSymbol] = useState(prefillSymbol || '');
  const [exchange, setExchange] = useState(prefillExchange || 'NFO');
  const [side, setSide] = useState<'BUY' | 'SELL'>('SELL');
  const [gttType, setGttType] = useState<'single' | 'two-leg'>('two-leg');
  const [lastPrice, setLastPrice] = useState(prefillPrice?.toString() || '');
  const [quantity, setQuantity] = useState('75');

  // Condition 1 (Stop-loss)
  const [slTrigger, setSlTrigger] = useState('');
  const [slPrice, setSlPrice] = useState('');

  // Condition 2 (Target) — for two-leg
  const [targetTrigger, setTargetTrigger] = useState('');
  const [targetPrice, setTargetPrice] = useState('');

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ success: boolean; message: string } | null>(null);
  const [marginData, setMarginData] = useState<MarginEstimateResponse | null>(null);
  const [marginLoading, setMarginLoading] = useState(false);

  const handleEstimateMargin = async () => {
    if (!symbol || !quantity) return;
    setMarginLoading(true);
    try {
      const data = await estimateMargin({
        broker: 'kite',
        symbol,
        exchange,
        quantity: Number(quantity),
        side,
        price: Number(lastPrice) || undefined,
      });
      setMarginData(data);
    } catch {
      setMarginData(null);
    } finally {
      setMarginLoading(false);
    }
  };

  const handleSubmit = async () => {
    if (!symbol || !lastPrice || !slTrigger || !quantity) {
      setResult({ success: false, message: 'Fill all required fields' });
      return;
    }

    setLoading(true);
    setResult(null);

    const payload: GTTOrderRequest = {
      symbol: symbol.trim().toUpperCase(),
      exchange,
      side,
      gtt_type: gttType,
      last_price: Number(lastPrice),
      condition: {
        trigger_price: Number(slTrigger),
        order_price: Number(slPrice) || 0,
        quantity: Number(quantity),
      },
    };

    if (gttType === 'two-leg' && targetTrigger) {
      payload.second_condition = {
        trigger_price: Number(targetTrigger),
        order_price: Number(targetPrice) || 0,
        quantity: Number(quantity),
      };
    }

    try {
      const resp = await placeGTTOrder(payload);
      setResult({ success: resp.success, message: resp.message });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'GTT order failed';
      setResult({ success: false, message: msg });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4 max-w-2xl mx-auto">
      <Card title="GTT Order (Kite)" padding="lg">
        <div className="space-y-4">
          {/* Symbol + Exchange */}
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Symbol"
              placeholder="e.g. NIFTY2470924400CE"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
            />
            <div>
              <label className="block text-sm font-medium text-dashboard-text mb-1.5">Exchange</label>
              <select
                value={exchange}
                onChange={(e) => setExchange(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-dashboard-bg border border-dashboard-border text-dashboard-text text-sm font-mono"
              >
                <option value="NFO">NFO</option>
                <option value="NSE">NSE</option>
                <option value="BFO">BFO</option>
              </select>
            </div>
          </div>

          {/* Side + GTT Type */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-dashboard-text mb-1.5">Side</label>
              <div className="flex gap-2">
                <button
                  onClick={() => setSide('BUY')}
                  className={`flex-1 py-2 rounded-lg text-sm font-semibold ${
                    side === 'BUY' ? 'bg-profit text-white' : 'bg-dashboard-bg border border-dashboard-border text-dashboard-muted'
                  }`}
                >BUY</button>
                <button
                  onClick={() => setSide('SELL')}
                  className={`flex-1 py-2 rounded-lg text-sm font-semibold ${
                    side === 'SELL' ? 'bg-loss text-white' : 'bg-dashboard-bg border border-dashboard-border text-dashboard-muted'
                  }`}
                >SELL</button>
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-dashboard-text mb-1.5">GTT Type</label>
              <div className="flex gap-2">
                <button
                  onClick={() => setGttType('single')}
                  className={`flex-1 py-2 rounded-lg text-xs font-medium ${
                    gttType === 'single' ? 'bg-blue-600 text-white' : 'bg-dashboard-bg border border-dashboard-border text-dashboard-muted'
                  }`}
                >Single</button>
                <button
                  onClick={() => setGttType('two-leg')}
                  className={`flex-1 py-2 rounded-lg text-xs font-medium ${
                    gttType === 'two-leg' ? 'bg-blue-600 text-white' : 'bg-dashboard-bg border border-dashboard-border text-dashboard-muted'
                  }`}
                >OCO (SL + Target)</button>
              </div>
            </div>
          </div>

          {/* Quantity + LTP */}
          <div className="grid grid-cols-2 gap-3">
            <Input label="Quantity" type="number" min="1" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
            <Input label="Last Price (LTP)" type="number" step="0.05" value={lastPrice} onChange={(e) => setLastPrice(e.target.value)} />
          </div>

          {/* Condition 1: Stop-Loss */}
          <div className="border border-dashboard-border rounded-lg p-3 space-y-2">
            <p className="text-xs font-semibold text-loss">Leg 1: Stop-Loss Trigger</p>
            <div className="grid grid-cols-2 gap-3">
              <Input label="Trigger Price" type="number" step="0.05" placeholder="SL trigger" value={slTrigger} onChange={(e) => setSlTrigger(e.target.value)} />
              <Input label="Order Price (0=Market)" type="number" step="0.05" placeholder="0 for market" value={slPrice} onChange={(e) => setSlPrice(e.target.value)} />
            </div>
          </div>

          {/* Condition 2: Target (only for two-leg) */}
          {gttType === 'two-leg' && (
            <div className="border border-dashboard-border rounded-lg p-3 space-y-2">
              <p className="text-xs font-semibold text-profit">Leg 2: Target Trigger</p>
              <div className="grid grid-cols-2 gap-3">
                <Input label="Trigger Price" type="number" step="0.05" placeholder="Target trigger" value={targetTrigger} onChange={(e) => setTargetTrigger(e.target.value)} />
                <Input label="Order Price" type="number" step="0.05" placeholder="Limit price" value={targetPrice} onChange={(e) => setTargetPrice(e.target.value)} />
              </div>
            </div>
          )}

          {/* Margin Estimate */}
          <Button variant="ghost" size="sm" onClick={handleEstimateMargin} isLoading={marginLoading}>
            Check Margin Required
          </Button>
          {marginData && <MarginDisplay data={marginData} />}

          {/* Result */}
          {result && (
            <div className={`rounded-lg p-3 text-sm ${result.success ? 'bg-profit/10 text-profit' : 'bg-loss/10 text-loss'}`}>
              {result.message}
            </div>
          )}

          {/* Submit */}
          <Button variant="primary" size="lg" className="w-full" onClick={handleSubmit} isLoading={loading}>
            Place GTT Order
          </Button>
        </div>
      </Card>
    </div>
  );
}
