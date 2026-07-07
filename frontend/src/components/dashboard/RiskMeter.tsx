import { Card } from '../ui/Card';
import { useWebSocket } from '../../contexts/WebSocketContext';
import { useAuth } from '../../contexts/AuthContext';

function getColorClass(percent: number): string {
  if (percent < 50) return 'bg-profit';
  if (percent < 80) return 'bg-yellow-500';
  return 'bg-loss';
}

function getTextColorClass(percent: number): string {
  if (percent < 50) return 'text-profit';
  if (percent < 80) return 'text-yellow-500';
  return 'text-loss';
}

interface ProgressBarProps {
  label: string;
  value: number;
  max: number;
  unit?: string;
}

function ProgressBar({ label, value, max, unit = '%' }: ProgressBarProps) {
  const percent = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  const colorClass = getColorClass(percent);
  const textColorClass = getTextColorClass(percent);

  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs text-dashboard-muted">{label}</span>
        <span className={`text-xs font-mono font-medium ${textColorClass}`}>
          {value.toFixed(1)}{unit}
        </span>
      </div>
      <div
        className="h-2 rounded-full bg-dashboard-border overflow-hidden"
        role="progressbar"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-label={`${label}: ${value.toFixed(1)}${unit}`}
      >
        <div
          className={`h-full rounded-full transition-all duration-500 ${colorClass}`}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}

export function RiskMeter() {
  const { riskMetrics } = useWebSocket();
  const { user } = useAuth();

  const capital = user?.capital ?? 100000;
  const dailyLossLimit = user?.dailyLossLimitPercent ?? 2.0;
  const pnl = riskMetrics?.pnl ?? 0;
  const marginUsed = riskMetrics?.marginUsed ?? 0;

  // Daily loss as a percentage of capital (only counts losses, positive means losing)
  const dailyLossPercent = capital > 0 ? Math.max(0, (-pnl / capital) * 100) : 0;
  // Margin usage as a percentage of capital
  const marginUsagePercent = capital > 0 ? (marginUsed / capital) * 100 : 0;

  return (
    <Card title="Risk Meter">
      <div className="space-y-4">
        <ProgressBar
          label="Daily Loss"
          value={dailyLossPercent}
          max={dailyLossLimit}
          unit={`% / ${dailyLossLimit}%`}
        />
        <ProgressBar
          label="Margin Usage"
          value={marginUsagePercent}
          max={100}
          unit="%"
        />

        {/* Warning indicator */}
        {dailyLossPercent >= dailyLossLimit * 0.8 && (
          <div
            className="flex items-center gap-2 p-2 rounded-lg bg-loss/10 border border-loss/20"
            role="alert"
          >
            <span className="text-loss text-sm" aria-hidden="true">⚠️</span>
            <span className="text-xs text-loss font-medium">
              Approaching daily loss limit
            </span>
          </div>
        )}
      </div>
    </Card>
  );
}
