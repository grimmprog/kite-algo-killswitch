import type { MonitoredPosition } from '../../hooks/usePositionMonitor';

interface TrailingStopIndicatorProps {
  position: MonitoredPosition;
}

/**
 * Trailing stop level indicator that shows:
 * - Current trailing stop level
 * - Visual representation of trailing stop relative to entry and current price
 * - Updates as price moves favorably (trailing stop ratchets up)
 *
 * Validates: Requirements 7.5, 7.6
 */
export function TrailingStopIndicator({ position }: TrailingStopIndicatorProps) {
  if (!position.trailingStopEnabled || position.trailingStopLevel == null) {
    return null;
  }

  const formatPrice = (price: number) =>
    `₹${price.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  // Calculate percentages for the visual bar
  const low = Math.min(position.stopLoss, position.trailingStopLevel, position.entryPrice);
  const high = Math.max(position.target, position.currentPrice);
  const range = high - low || 1;

  const entryPct = ((position.entryPrice - low) / range) * 100;
  const trailingPct = ((position.trailingStopLevel - low) / range) * 100;
  const currentPricePct = ((position.currentPrice - low) / range) * 100;

  // Distance from current price to trailing stop
  const distanceToTrailingPct =
    position.currentPrice !== 0
      ? ((position.currentPrice - position.trailingStopLevel) / position.currentPrice) * 100
      : 0;

  const isNearTrailing = distanceToTrailingPct < 1; // within 1%

  return (
    <div
      className={`rounded-lg border p-3 ${
        isNearTrailing
          ? 'bg-yellow-500/10 border-yellow-500/30'
          : 'bg-blue-500/10 border-blue-500/20'
      }`}
      role="region"
      aria-label={`Trailing stop indicator for ${position.symbol}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-blue-400" aria-hidden="true">⟳</span>
          <span className="text-sm font-medium text-dashboard-text">Trailing Stop</span>
        </div>
        {isNearTrailing && (
          <span
            className="text-xs font-medium text-yellow-400 animate-pulse"
            role="alert"
            aria-live="polite"
          >
            ⚠ Near trailing stop
          </span>
        )}
      </div>

      {/* Visual Bar */}
      <div className="relative h-2 bg-dashboard-bg rounded-full mb-2 overflow-visible">
        {/* Entry marker */}
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-dashboard-muted"
          style={{ left: `${entryPct}%` }}
          title="Entry Price"
        />
        {/* Trailing stop marker */}
        <div
          className="absolute -top-0.5 -bottom-0.5 w-1.5 rounded-full bg-yellow-400 shadow-sm shadow-yellow-400/50 transition-all duration-500"
          style={{ left: `${trailingPct}%`, transform: 'translateX(-50%)' }}
          title={`Trailing Stop: ${formatPrice(position.trailingStopLevel)}`}
        />
        {/* Current price marker */}
        <div
          className="absolute -top-1 -bottom-1 w-2 rounded-full bg-blue-400 shadow-sm shadow-blue-400/50 transition-all duration-300"
          style={{ left: `${currentPricePct}%`, transform: 'translateX(-50%)' }}
          title={`Current: ${formatPrice(position.currentPrice)}`}
        />
      </div>

      {/* Labels */}
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div>
          <p className="text-dashboard-muted">Entry</p>
          <p className="text-dashboard-text font-mono">{formatPrice(position.entryPrice)}</p>
        </div>
        <div className="text-center">
          <p className="text-yellow-400">Trailing SL</p>
          <p className="text-yellow-300 font-mono font-semibold">
            {formatPrice(position.trailingStopLevel)}
          </p>
        </div>
        <div className="text-right">
          <p className="text-dashboard-muted">Current</p>
          <p className="text-blue-300 font-mono">{formatPrice(position.currentPrice)}</p>
        </div>
      </div>

      {/* Distance info */}
      <div className="mt-2 pt-2 border-t border-dashboard-border/50">
        <p className={`text-xs ${isNearTrailing ? 'text-yellow-400' : 'text-dashboard-muted'}`}>
          Distance to trailing stop:{' '}
          <span className="font-mono font-medium">{distanceToTrailingPct.toFixed(2)}%</span>
        </p>
      </div>
    </div>
  );
}
