import { useState } from 'react';
import { DashboardLayout } from '../components/dashboard/DashboardLayout';
import { PnLCard } from '../components/dashboard/PnLCard';
import { RiskMeter } from '../components/dashboard/RiskMeter';
import { KillSwitchControl } from '../components/dashboard/KillSwitchControl';
import { GreeksDisplay } from '../components/dashboard/GreeksDisplay';
import { LiveMarketPanel } from '../components/dashboard/LiveMarketPanel';
import { AccountSummary } from '../components/dashboard/AccountSummary';
import { useWebSocket } from '../contexts/WebSocketContext';
import { Card } from '../components/ui/Card';

function PositionsOverview() {
  const { positions } = useWebSocket();

  if (positions.length === 0) {
    return (
      <Card title="Open Positions">
        <p className="text-sm text-dashboard-muted py-4 text-center">
          No open positions
        </p>
      </Card>
    );
  }

  return (
    <Card title="Open Positions" subtitle={`${positions.length} active`}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm" aria-label="Open positions">
          <thead>
            <tr className="border-b border-dashboard-border">
              <th className="text-left py-2 px-1 text-xs text-dashboard-muted font-medium">Symbol</th>
              <th className="text-right py-2 px-1 text-xs text-dashboard-muted font-medium">Qty</th>
              <th className="text-right py-2 px-1 text-xs text-dashboard-muted font-medium">Entry</th>
              <th className="text-right py-2 px-1 text-xs text-dashboard-muted font-medium">LTP</th>
              <th className="text-right py-2 px-1 text-xs text-dashboard-muted font-medium">P&L</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((pos) => {
              const isProfit = pos.pnl >= 0;
              return (
                <tr
                  key={pos.symbol}
                  className="border-b border-dashboard-border last:border-0"
                >
                  <td className="py-2 px-1 font-mono text-dashboard-text">{pos.symbol}</td>
                  <td className="py-2 px-1 text-right font-mono text-dashboard-muted">
                    {pos.quantity}
                  </td>
                  <td className="py-2 px-1 text-right font-mono text-dashboard-muted">
                    ₹{pos.entryPrice.toFixed(2)}
                  </td>
                  <td className="py-2 px-1 text-right font-mono text-dashboard-text">
                    ₹{pos.currentPrice.toFixed(2)}
                  </td>
                  <td
                    className={`py-2 px-1 text-right font-mono font-medium ${
                      isProfit ? 'text-profit' : 'text-loss'
                    }`}
                  >
                    {isProfit ? '+' : ''}₹{pos.pnl.toFixed(2)}
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

export function DashboardPage() {
  const [activeBroker, setActiveBroker] = useState<'kite' | 'dhan'>('kite');

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Live market data */}
        <LiveMarketPanel />

        {/* Broker Tab Toggle */}
        <div className="flex items-center gap-1 bg-dashboard-card border border-dashboard-border rounded-lg p-1 w-fit">
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

        {/* Account Summary (broker-aware) */}
        <AccountSummary broker={activeBroker} />

        {/* Top row: P&L and Risk */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <PnLCard />
          <RiskMeter />
          <KillSwitchControl />
        </div>

        {/* Bottom row: Greeks and Positions */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <GreeksDisplay />
          <div className="lg:col-span-2">
            <PositionsOverview />
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
