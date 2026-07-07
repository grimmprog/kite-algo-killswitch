import { useState } from 'react';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { placeDhanOrder, estimateMargin } from '../../api/orders';
import type { DhanOrderRequest, MarginEstimateResponse } from '../../api/orders';
import { MarginDisplay } from './MarginDisplay';

interface DhanOrderFormProps {
  prefillSymbol?: string;
  prefillPrice?: number;
}

export function DhanOrderForm({ prefillSymbol, prefillPrice }: DhanOrderFormProps) {
  const [symbol, setSymbol] = useState(prefillSymbol || '');
  const [securityId, setSecurityId] = useState('');
  const [exchange, setExchange] = useState('NSE_FNO');
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  const [quantity, setQuantity] = useState('75');
  const [orderType, setOrderType] = useState<'MARKET' | 'LIMIT'>('MARKET');
  const [price, setPrice] = useState(prefillPrice?.toString() || '');
  const [product, setProduct] = useState<'INTRADAY' | 'CNC' | 'MARGIN'>('INTRADAY');

  // Trailing SL
  const [stopLossPrice, setStopLossPrice] = useState('');
  const [trailingSl, setTrailingSl] = useState('');

  // Targets
  const [targetPrice, setTargetPrice] = useState('');
  const [target2Price, setTarget2Price] = useState('');

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ success: boolean; message: string; details?: string } | null>(null);
  const [marginData, setMarginData] = useState<MarginEstimateResponse | null>(null);
  const [marginLoading, setMarginLoading] = useState(false);

  const handleEstimateMargin = async () => {
    if (!symbol || !quantity) return;
    setMarginLoading(true);
    try {
      const data = await estimateMargin({
        broker: 'dhan',
        symbol,
        exchange,
        quantity: Number(quantity),
        side,
        price: Number(price) || undefined,
        security_id: securityId || undefined,
        product,
      });
      setMarginData(data);
    } catch {
      setMarginData(null);
    } finally {
      setMarginLoading(false);
    }
  };

  const handleSubmit = async () => {
    if (!symbol || !securityId || !quantity) {
      setResult({ success: false, message: 'Fill symbol, security ID, and quantity' });
      return;
    }

    setLoading(true);
    setResult(null);

    const payload: DhanOrderRequest = {
      symbol: symbol.trim().toUpperCase(),
      exchange,
      security_id: securityId.trim(),
      side,
      quantity: Number(quantity),
      order_type: orderType,
      product,
      price: orderType === 'LIMIT' ? Number(price) : undefined,
      stop_loss_price: stopLossPrice ? Number(stopLossPrice) : undefined,
      trailing_sl: trailingSl ? Number(trailingSl) : undefined,
      target_price: targetPrice ? Number(targetPrice) : undefined,
      target_2_price: target2Price ? Number(target2Price) : undefined,
    };

    try {
      const resp = await placeDhanOrder(payload);
      const details = [
        resp.order_id ? `Order: ${resp.order_id}` : '',
        resp.sl_order_id ? `SL: ${resp.sl_order_id}` : '',
        resp.target_order_id ? `Target: ${resp.target_order_id}` : '',
      ].filter(Boolean).join(' | ');

      setResult({ success: resp.success, message: resp.message, details });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Order failed';
      setResult({ success: false, message: msg });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4 max-w-2xl mx-auto">
      <Card title="Dhan Order with Trailing SL & Targets" padding="lg">
        <div className="space-y-4">
          {/* Symbol + Security ID */}
          <div className="grid grid-cols-2 gap-3">
            <Input label="Symbol" placeholder="e.g. NIFTY JUL 24400 CE" value={symbol} onChange={(e) => setSymbol(e.target.value)} />
            <Input label="Security ID" placeholder="Dhan security ID" value={securityId} onChange={(e) => setSecurityId(e.target.value)} />
          </div>

          {/* Exchange + Product */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-dashboard-text mb-1.5">Exchange</label>
              <select value={exchange} onChange={(e) => setExchange(e.target.value)} className="w-full px-3 py-2 rounded-lg bg-dashboard-bg border border-dashboard-border text-dashboard-text text-sm font-mono">
                <option value="NSE_FNO">NSE F&O</option>
                <option value="NSE_EQ">NSE Equity</option>
                <option value="BSE_FNO">BSE F&O</option>
                <option value="BSE_EQ">BSE Equity</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-dashboard-text mb-1.5">Product</label>
              <select value={product} onChange={(e) => setProduct(e.target.value as typeof product)} className="w-full px-3 py-2 rounded-lg bg-dashboard-bg border border-dashboard-border text-dashboard-text text-sm font-mono">
                <option value="INTRADAY">Intraday (MIS)</option>
                <option value="CNC">CNC (Delivery)</option>
                <option value="MARGIN">Margin</option>
              </select>
            </div>
          </div>

          {/* Side */}
          <div>
            <label className="block text-sm font-medium text-dashboard-text mb-1.5">Side</label>
            <div className="flex gap-2">
              <button onClick={() => setSide('BUY')} className={`flex-1 py-2 rounded-lg text-sm font-semibold ${side === 'BUY' ? 'bg-profit text-white' : 'bg-dashboard-bg border border-dashboard-border text-dashboard-muted'}`}>BUY</button>
              <button onClick={() => setSide('SELL')} className={`flex-1 py-2 rounded-lg text-sm font-semibold ${side === 'SELL' ? 'bg-loss text-white' : 'bg-dashboard-bg border border-dashboard-border text-dashboard-muted'}`}>SELL</button>
            </div>
          </div>

          {/* Quantity + Order Type + Price */}
          <div className="grid grid-cols-3 gap-3">
            <Input label="Quantity" type="number" min="1" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
            <div>
              <label className="block text-sm font-medium text-dashboard-text mb-1.5">Order Type</label>
              <select value={orderType} onChange={(e) => setOrderType(e.target.value as typeof orderType)} className="w-full px-3 py-2 rounded-lg bg-dashboard-bg border border-dashboard-border text-dashboard-text text-sm font-mono">
                <option value="MARKET">Market</option>
                <option value="LIMIT">Limit</option>
              </select>
            </div>
            {orderType === 'LIMIT' && (
              <Input label="Price" type="number" step="0.05" value={price} onChange={(e) => setPrice(e.target.value)} />
            )}
          </div>

          {/* Stop-Loss & Trailing */}
          <div className="border border-loss/30 rounded-lg p-3 space-y-3">
            <p className="text-xs font-semibold text-loss">Stop-Loss & Trailing</p>
            <div className="grid grid-cols-2 gap-3">
              <Input label="Stop-Loss Price" type="number" step="0.05" placeholder="Initial SL price" value={stopLossPrice} onChange={(e) => setStopLossPrice(e.target.value)} />
              <Input label="Trail By (₹ points)" type="number" step="0.5" placeholder="e.g. 10 = trail by ₹10" value={trailingSl} onChange={(e) => setTrailingSl(e.target.value)} />
            </div>
            <p className="text-[10px] text-dashboard-muted">
              Trailing SL moves the stop-loss up by the trail value as price moves in your favor.
              E.g., if you buy at ₹200 with SL=₹190 and trail=₹5, when price hits ₹210 the SL moves to ₹195.
            </p>
          </div>

          {/* Targets */}
          <div className="border border-profit/30 rounded-lg p-3 space-y-3">
            <p className="text-xs font-semibold text-profit">Target Prices</p>
            <div className="grid grid-cols-2 gap-3">
              <Input label="Target 1" type="number" step="0.05" placeholder="Primary target" value={targetPrice} onChange={(e) => setTargetPrice(e.target.value)} />
              <Input label="Target 2 (optional)" type="number" step="0.05" placeholder="Second target" value={target2Price} onChange={(e) => setTarget2Price(e.target.value)} />
            </div>
          </div>

          {/* Margin Check */}
          <Button variant="ghost" size="sm" onClick={handleEstimateMargin} isLoading={marginLoading}>
            Check Margin Required
          </Button>
          {marginData && <MarginDisplay data={marginData} />}

          {/* Result */}
          {result && (
            <div className={`rounded-lg p-3 text-sm ${result.success ? 'bg-profit/10 text-profit' : 'bg-loss/10 text-loss'}`}>
              <p>{result.message}</p>
              {result.details && <p className="text-xs mt-1 opacity-80">{result.details}</p>}
            </div>
          )}

          {/* Submit */}
          <Button variant="primary" size="lg" className="w-full" onClick={handleSubmit} isLoading={loading}>
            Place Dhan Order
          </Button>
        </div>
      </Card>
    </div>
  );
}
