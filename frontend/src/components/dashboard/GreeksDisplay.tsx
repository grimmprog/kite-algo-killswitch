import { Card } from '../ui/Card';
import { useWebSocket } from '../../contexts/WebSocketContext';

interface GreekItemProps {
  label: string;
  value: number;
  description: string;
}

function GreekItem({ label, value, description }: GreekItemProps) {
  const isPositive = value >= 0;

  return (
    <div className="flex items-center justify-between py-2 border-b border-dashboard-border last:border-0">
      <div>
        <p className="text-sm font-medium text-dashboard-text">{label}</p>
        <p className="text-xs text-dashboard-muted">{description}</p>
      </div>
      <p
        className={`text-sm font-mono font-semibold ${
          isPositive ? 'text-profit' : 'text-loss'
        }`}
        aria-label={`${label}: ${value >= 0 ? '+' : ''}${value.toFixed(4)}`}
      >
        {value >= 0 ? '+' : ''}{value.toFixed(4)}
      </p>
    </div>
  );
}

export function GreeksDisplay() {
  const { riskMetrics } = useWebSocket();

  const netDelta = riskMetrics?.netDelta ?? 0;
  const netGamma = riskMetrics?.netGamma ?? 0;
  const netVega = riskMetrics?.netVega ?? 0;

  return (
    <Card title="Portfolio Greeks" subtitle="Real-time net exposure">
      <div className="divide-y divide-dashboard-border">
        <GreekItem
          label="Delta (Δ)"
          value={netDelta}
          description="Directional exposure"
        />
        <GreekItem
          label="Gamma (Γ)"
          value={netGamma}
          description="Rate of delta change"
        />
        <GreekItem
          label="Vega (ν)"
          value={netVega}
          description="Volatility sensitivity"
        />
      </div>

      {/* Last updated */}
      {riskMetrics?.updatedAt && (
        <p className="text-xs text-dashboard-muted mt-3">
          Updated: {new Date(riskMetrics.updatedAt).toLocaleTimeString()}
        </p>
      )}
    </Card>
  );
}
