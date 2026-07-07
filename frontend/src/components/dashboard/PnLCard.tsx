import { Card } from '../ui/Card';
import { useWebSocket } from '../../contexts/WebSocketContext';
import { useAuth } from '../../contexts/AuthContext';

export function PnLCard() {
  const { riskMetrics } = useWebSocket();
  const { user } = useAuth();

  const pnl = riskMetrics?.pnl ?? 0;
  const capital = user?.capital ?? 100000;
  const pnlPercent = capital > 0 ? (pnl / capital) * 100 : 0;
  const isProfit = pnl >= 0;

  return (
    <Card className="relative overflow-hidden">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-dashboard-muted uppercase tracking-wide">
            Today&apos;s P&amp;L
          </p>
          <p
            className={`text-2xl font-mono font-bold mt-1 ${
              isProfit ? 'text-profit' : 'text-loss'
            }`}
            aria-label={`Profit and loss: ${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)} rupees`}
          >
            {pnl >= 0 ? '+' : ''}₹{Math.abs(pnl).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </p>
          <p
            className={`text-sm font-mono mt-0.5 ${
              isProfit ? 'text-profit' : 'text-loss'
            }`}
          >
            {pnlPercent >= 0 ? '+' : ''}{pnlPercent.toFixed(2)}%
          </p>
        </div>

        <div
          className={`w-10 h-10 rounded-full flex items-center justify-center ${
            isProfit ? 'bg-profit/10' : 'bg-loss/10'
          }`}
          aria-hidden="true"
        >
          <span className="text-lg">{isProfit ? '↑' : '↓'}</span>
        </div>
      </div>

      {/* Visual indicator bar at bottom */}
      <div className="mt-4 h-1 rounded-full bg-dashboard-border overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            isProfit ? 'bg-profit' : 'bg-loss'
          }`}
          style={{ width: `${Math.min(Math.abs(pnlPercent) * 10, 100)}%` }}
          aria-hidden="true"
        />
      </div>
    </Card>
  );
}
