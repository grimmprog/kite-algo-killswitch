import { Button } from '../ui/Button';

interface TradeDetails {
  symbol: string;
  exchange: string;
  quantity: number;
  side: 'BUY' | 'SELL';
  orderType: 'MARKET' | 'LIMIT';
  price: number;
  maxLoss?: number;
  riskLevel?: string;
}

interface TradeConfirmModalProps {
  trade: TradeDetails;
  isLoading: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function TradeConfirmModal({ trade, isLoading, onConfirm, onCancel }: TradeConfirmModalProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      role="dialog"
      aria-modal="true"
      aria-labelledby="trade-confirm-title"
    >
      <div className="bg-dashboard-card border border-dashboard-border rounded-xl p-6 w-full max-w-md mx-4 shadow-2xl">
        <h2 id="trade-confirm-title" className="text-lg font-bold text-dashboard-text mb-4">
          Confirm Trade
        </h2>

        {/* Trade summary */}
        <div className="space-y-3 mb-6">
          <div className="flex justify-between text-sm">
            <span className="text-dashboard-muted">Symbol</span>
            <span className="font-mono font-medium text-dashboard-text">{trade.symbol}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-dashboard-muted">Exchange</span>
            <span className="font-mono text-dashboard-text">{trade.exchange}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-dashboard-muted">Side</span>
            <span className={`font-semibold ${trade.side === 'BUY' ? 'text-profit' : 'text-loss'}`}>
              {trade.side}
            </span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-dashboard-muted">Quantity</span>
            <span className="font-mono text-dashboard-text">{trade.quantity}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-dashboard-muted">Order Type</span>
            <span className="text-dashboard-text">{trade.orderType}</span>
          </div>
          {trade.orderType === 'LIMIT' && (
            <div className="flex justify-between text-sm">
              <span className="text-dashboard-muted">Price</span>
              <span className="font-mono text-dashboard-text">₹{trade.price.toFixed(2)}</span>
            </div>
          )}
          {trade.maxLoss !== undefined && (
            <div className="flex justify-between text-sm">
              <span className="text-dashboard-muted">Max Loss</span>
              <span className="font-mono text-loss">₹{trade.maxLoss.toFixed(2)}</span>
            </div>
          )}
          {trade.riskLevel && (
            <div className="flex justify-between text-sm">
              <span className="text-dashboard-muted">Risk Level</span>
              <span
                className={`font-medium ${
                  trade.riskLevel === 'LOW'
                    ? 'text-profit'
                    : trade.riskLevel === 'MEDIUM'
                      ? 'text-yellow-400'
                      : 'text-loss'
                }`}
              >
                {trade.riskLevel}
              </span>
            </div>
          )}
        </div>

        {/* Risk disclosure */}
        <div className="bg-dashboard-bg border border-dashboard-border rounded-lg p-3 mb-6">
          <p className="text-xs text-dashboard-muted">
            By confirming, you acknowledge the risks involved in this trade.
            Past performance does not guarantee future results.
          </p>
        </div>

        {/* Actions */}
        <div className="flex gap-3">
          <Button
            variant="ghost"
            size="md"
            className="flex-1"
            onClick={onCancel}
            disabled={isLoading}
          >
            Cancel
          </Button>
          <Button
            variant={trade.side === 'BUY' ? 'success' : 'danger'}
            size="md"
            className="flex-1"
            isLoading={isLoading}
            onClick={onConfirm}
          >
            {isLoading ? 'Executing...' : `Confirm ${trade.side}`}
          </Button>
        </div>
      </div>
    </div>
  );
}
