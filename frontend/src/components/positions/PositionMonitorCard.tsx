import { useState, useCallback } from 'react';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import type { MonitoredPosition } from '../../hooks/usePositionMonitor';

interface PositionMonitorCardProps {
  position: MonitoredPosition;
  onManualExit: (positionId: number) => Promise<void>;
  onViewExitConditions?: (positionId: number) => void;
}

/**
 * Per-position card showing SL/Target visual tracker with:
 * - Symbol and status badge (active/sl_hit/target_hit/trailing_stop_hit)
 * - Current price, entry price, unrealized P&L (green/red)
 * - Visual progress bar showing price position between SL and Target
 * - Distance to SL and Target as percentages
 * - "Exit Now" button (manual exit / error fallback)
 *
 * Validates: Requirements 7.1-7.7
 */
export function PositionMonitorCard({
  position,
  onManualExit,
  onViewExitConditions,
}: PositionMonitorCardProps) {
  const [isExiting, setIsExiting] = useState(false);

  const handleExit = useCallback(async () => {
    setIsExiting(true);
    try {
      await onManualExit(position.positionId);
    } finally {
      setIsExiting(false);
    }
  }, [onManualExit, position.positionId]);

  const formatPrice = (price: number) =>
    `₹${price.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  const formatPnl = (pnl: number) => {
    const prefix = pnl >= 0 ? '+' : '';
    return `${prefix}₹${pnl.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  const pnlVariant = position.unrealizedPnl >= 0 ? 'profit' : 'loss';
  const isActive = position.status === 'active';

  // Calculate progress position: 0% = at SL, 100% = at Target
  const range = position.target - position.stopLoss;
  const progressPct = range !== 0
    ? Math.max(0, Math.min(100, ((position.currentPrice - position.stopLoss) / range) * 100))
    : 50;

  return (
    <Card
      className={`relative ${!isActive ? 'opacity-75' : ''}`}
      padding="md"
      role="article"
      aria-label={`Position monitor for ${position.symbol}`}
    >
      {/* Header: Symbol + Status */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-lg font-bold text-dashboard-text">{position.symbol}</h3>
        <StatusBadge status={position.status} />
      </div>

      {/* Price Info */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <PriceBox label="Entry" value={formatPrice(position.entryPrice)} />
        <PriceBox
          label="Current"
          value={formatPrice(position.currentPrice)}
          variant={position.currentPrice >= position.entryPrice ? 'profit' : 'loss'}
        />
        <PriceBox
          label="Unrealized P&L"
          value={formatPnl(position.unrealizedPnl)}
          variant={pnlVariant}
        />
      </div>

      {/* SL/Target Progress Bar */}
      <div className="mb-4">
        <div className="flex justify-between text-xs text-dashboard-muted mb-1">
          <span>SL: {formatPrice(position.stopLoss)}</span>
          <span>Target: {formatPrice(position.target)}</span>
        </div>
        <div
          className="relative h-3 bg-dashboard-bg rounded-full overflow-hidden border border-dashboard-border"
          role="progressbar"
          aria-valuenow={Math.round(progressPct)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Price position between stop loss and target: ${Math.round(progressPct)}%`}
        >
          {/* Gradient bar from red (SL) to green (Target) */}
          <div
            className="absolute inset-0 bg-gradient-to-r from-loss/30 via-yellow-500/30 to-profit/30"
          />
          {/* Current price indicator */}
          <div
            className="absolute top-0 bottom-0 w-1 bg-blue-400 shadow-lg shadow-blue-400/50 transition-all duration-300"
            style={{ left: `${progressPct}%`, transform: 'translateX(-50%)' }}
          />
        </div>
        {/* Distance Percentages */}
        <div className="flex justify-between text-xs mt-1">
          <span className="text-loss">
            {position.distanceToSlPct.toFixed(1)}% to SL
          </span>
          <span className="text-profit">
            {position.distanceToTargetPct.toFixed(1)}% to Target
          </span>
        </div>
      </div>

      {/* Trailing Stop Indicator (inline) */}
      {position.trailingStopEnabled && position.trailingStopLevel != null && (
        <div className="mb-4 flex items-center gap-2 bg-blue-500/10 border border-blue-500/20 rounded-lg px-3 py-2">
          <span className="text-blue-400 text-sm" aria-hidden="true">⟳</span>
          <span className="text-xs text-blue-300">
            Trailing Stop: {formatPrice(position.trailingStopLevel)}
          </span>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2">
        {onViewExitConditions && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onViewExitConditions(position.positionId)}
            aria-label={`View exit conditions for ${position.symbol}`}
          >
            Exit Rules
          </Button>
        )}
        <Button
          variant="danger"
          size="sm"
          onClick={handleExit}
          isLoading={isExiting}
          disabled={!isActive}
          className="ml-auto"
          aria-label={`Exit position for ${position.symbol}`}
        >
          Exit Now
        </Button>
      </div>
    </Card>
  );
}

// --- Sub-components ---

interface PriceBoxProps {
  label: string;
  value: string;
  variant?: 'default' | 'profit' | 'loss';
}

function PriceBox({ label, value, variant = 'default' }: PriceBoxProps) {
  const colorMap = {
    default: 'text-dashboard-text',
    profit: 'text-profit',
    loss: 'text-loss',
  };

  return (
    <div className="bg-dashboard-bg/50 rounded-lg p-2">
      <p className="text-xs text-dashboard-muted">{label}</p>
      <p className={`text-sm font-mono font-semibold ${colorMap[variant]}`}>{value}</p>
    </div>
  );
}

interface StatusBadgeProps {
  status: string;
}

function StatusBadge({ status }: StatusBadgeProps) {
  const statusConfig: Record<string, { label: string; color: string }> = {
    active: { label: 'Active', color: 'bg-profit/20 text-profit' },
    sl_hit: { label: 'SL Hit', color: 'bg-loss/20 text-loss' },
    target_hit: { label: 'Target Hit', color: 'bg-profit/20 text-profit' },
    trailing_stop_hit: { label: 'Trailing Stop Hit', color: 'bg-yellow-500/20 text-yellow-400' },
  };

  const config = statusConfig[status] ?? { label: status, color: 'bg-dashboard-border text-dashboard-muted' };

  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${config.color}`}
      aria-label={`Position status: ${config.label}`}
    >
      {config.label}
    </span>
  );
}
