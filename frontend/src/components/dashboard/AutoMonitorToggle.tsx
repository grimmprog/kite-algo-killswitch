import { useState, useCallback } from 'react';
import { Card } from '../ui/Card';
import { useNotifications } from '../../hooks/useNotifications';
import { put } from '../../api/client';

interface MonitorToggleResponse {
  isActive: boolean;
  message: string;
}

/**
 * AutoMonitorToggle — Dashboard widget for background P&L monitoring.
 * - Shows active/inactive status toggle
 * - Displays current P&L and distance to nearest threshold
 * - Validates: Requirements 10.1-10.5
 */
export function AutoMonitorToggle() {
  const { monitorStatus } = useNotifications();
  const [isToggling, setIsToggling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isActive = monitorStatus?.isActive ?? false;
  const currentPnl = monitorStatus?.currentPnl ?? 0;
  const nearestThreshold = monitorStatus?.nearestThreshold ?? 0;
  const distanceToThreshold = monitorStatus?.distanceToThreshold ?? 0;
  const thresholdType = monitorStatus?.thresholdType ?? '';

  const handleToggle = useCallback(async () => {
    setIsToggling(true);
    setError(null);

    try {
      await put<MonitorToggleResponse>('/api/v1/monitor/toggle', {
        active: !isActive,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to toggle monitor';
      setError(message);
    } finally {
      setIsToggling(false);
    }
  }, [isActive]);

  const pnlIsProfit = currentPnl >= 0;
  const isNearThreshold = distanceToThreshold > 0 && distanceToThreshold <= 10;

  return (
    <Card title="Auto Monitor">
      <div className="space-y-3">
        {/* Toggle control */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div
              className={`w-2.5 h-2.5 rounded-full ${
                isActive ? 'bg-profit animate-pulse' : 'bg-dashboard-muted'
              }`}
              aria-hidden="true"
            />
            <span className="text-sm text-dashboard-text font-medium">
              {isActive ? 'Active' : 'Inactive'}
            </span>
          </div>

          <button
            type="button"
            role="switch"
            aria-checked={isActive}
            aria-label={`P&L monitoring is ${isActive ? 'active' : 'inactive'}. Click to ${isActive ? 'stop' : 'start'} monitoring.`}
            disabled={isToggling}
            onClick={handleToggle}
            className={`
              relative inline-flex h-6 w-11 items-center rounded-full
              transition-colors duration-200 ease-in-out
              focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-dashboard-bg
              disabled:opacity-50 disabled:cursor-not-allowed
              ${isActive ? 'bg-profit' : 'bg-dashboard-border'}
            `}
          >
            <span
              className={`
                inline-block h-4 w-4 transform rounded-full bg-white shadow-sm
                transition-transform duration-200 ease-in-out
                ${isActive ? 'translate-x-6' : 'translate-x-1'}
              `}
              aria-hidden="true"
            />
          </button>
        </div>

        {/* P&L Display — visible when monitor is active */}
        {isActive && (
          <div className="space-y-2 pt-2 border-t border-dashboard-border">
            <div className="flex items-center justify-between">
              <span className="text-xs text-dashboard-muted">Current P&L</span>
              <span
                className={`text-sm font-mono font-semibold ${
                  pnlIsProfit ? 'text-profit' : 'text-loss'
                }`}
                aria-label={`Current profit and loss: ${currentPnl >= 0 ? '+' : ''}${currentPnl.toFixed(2)} rupees`}
              >
                {currentPnl >= 0 ? '+' : ''}₹{Math.abs(currentPnl).toLocaleString('en-IN', {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </span>
            </div>

            {nearestThreshold > 0 && (
              <div className="flex items-center justify-between">
                <span className="text-xs text-dashboard-muted">
                  Distance to {thresholdType || 'threshold'}
                </span>
                <span
                  className={`text-xs font-mono font-medium ${
                    isNearThreshold ? 'text-amber-400' : 'text-dashboard-text'
                  }`}
                >
                  {distanceToThreshold.toFixed(1)}%
                </span>
              </div>
            )}

            {/* Warning bar when close to threshold */}
            {isNearThreshold && (
              <div
                className="flex items-center gap-2 px-2 py-1.5 rounded-md bg-amber-500/10 border border-amber-500/20"
                role="alert"
                aria-live="polite"
              >
                <span className="text-amber-400 text-xs" aria-hidden="true">⚠</span>
                <span className="text-xs text-amber-300">
                  Approaching {thresholdType} threshold
                </span>
              </div>
            )}

            {/* Threshold progress bar */}
            {nearestThreshold > 0 && (
              <div className="mt-1">
                <div className="h-1.5 rounded-full bg-dashboard-border overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      isNearThreshold ? 'bg-amber-400' : pnlIsProfit ? 'bg-profit' : 'bg-loss'
                    }`}
                    style={{
                      width: `${Math.min(
                        (Math.abs(currentPnl) / nearestThreshold) * 100,
                        100
                      )}%`,
                    }}
                    aria-hidden="true"
                  />
                </div>
                <div className="flex justify-between mt-1">
                  <span className="text-[10px] text-dashboard-muted">₹0</span>
                  <span className="text-[10px] text-dashboard-muted">
                    ₹{nearestThreshold.toLocaleString('en-IN')}
                  </span>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Error display */}
        {error && (
          <p className="text-xs text-loss" role="alert">
            {error}
          </p>
        )}
      </div>
    </Card>
  );
}
