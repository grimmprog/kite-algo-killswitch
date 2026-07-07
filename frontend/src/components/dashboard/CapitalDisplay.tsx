import { useState, useEffect, useCallback } from 'react';
import { Card } from '../ui/Card';
import { get } from '../../api/client';

// --- Types ---

interface SegmentMargin {
  segment: string;
  used: number;
  available: number;
}

interface CapitalData {
  availableBalance: number;
  configuredCapital: number;
  usedMargin: number;
  availableMargin: number;
  segments: SegmentMargin[];
}

const REFRESH_INTERVAL_MS = 60_000; // 60 seconds

/**
 * CapitalDisplay — Dashboard widget showing balance, capital, and margin breakdown.
 * - Fetches capital data from /api/v1/status/capital
 * - Displays available balance, configured capital, used/available margin
 * - Shows margin breakdown by segment (equity, commodity, F&O)
 * - Auto-refreshes every 60 seconds
 * - Validates: Requirements 13.1-13.4
 */
export function CapitalDisplay() {
  const [data, setData] = useState<CapitalData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchCapitalData = useCallback(async () => {
    try {
      setError(null);
      const result = await get<CapitalData>('/api/v1/status/capital');
      setData(result);
      setLastUpdated(new Date());
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch capital data';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Initial fetch and 60s interval
  useEffect(() => {
    fetchCapitalData();

    const interval = setInterval(fetchCapitalData, REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchCapitalData]);

  const formatCurrency = (value: number) =>
    `₹${value.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  if (isLoading && !data) {
    return (
      <Card title="Capital & Margin">
        <div className="animate-pulse space-y-3" aria-label="Loading capital data">
          <div className="h-4 bg-dashboard-border rounded w-3/4" />
          <div className="h-4 bg-dashboard-border rounded w-1/2" />
          <div className="h-4 bg-dashboard-border rounded w-2/3" />
        </div>
      </Card>
    );
  }

  if (error && !data) {
    return (
      <Card title="Capital & Margin">
        <p className="text-xs text-loss" role="alert">
          {error}
        </p>
      </Card>
    );
  }

  const marginUtilization = data
    ? data.usedMargin + data.availableMargin > 0
      ? (data.usedMargin / (data.usedMargin + data.availableMargin)) * 100
      : 0
    : 0;

  return (
    <Card title="Capital & Margin" subtitle={lastUpdated ? `Updated ${formatTime(lastUpdated)}` : undefined}>
      <div className="space-y-3">
        {/* Main figures */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <p className="text-xs text-dashboard-muted">Available Balance</p>
            <p
              className="text-sm font-mono font-semibold text-dashboard-text mt-0.5"
              aria-label={`Available balance: ${formatCurrency(data?.availableBalance ?? 0)}`}
            >
              {formatCurrency(data?.availableBalance ?? 0)}
            </p>
          </div>
          <div>
            <p className="text-xs text-dashboard-muted">Configured Capital</p>
            <p
              className="text-sm font-mono font-semibold text-dashboard-text mt-0.5"
              aria-label={`Configured capital: ${formatCurrency(data?.configuredCapital ?? 0)}`}
            >
              {formatCurrency(data?.configuredCapital ?? 0)}
            </p>
          </div>
        </div>

        {/* Margin utilization bar */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-dashboard-muted">Margin Used</span>
            <span className="text-xs font-mono text-dashboard-text">
              {formatCurrency(data?.usedMargin ?? 0)} / {formatCurrency((data?.usedMargin ?? 0) + (data?.availableMargin ?? 0))}
            </span>
          </div>
          <div className="h-2 rounded-full bg-dashboard-border overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                marginUtilization > 80 ? 'bg-loss' : marginUtilization > 50 ? 'bg-amber-400' : 'bg-blue-500'
              }`}
              style={{ width: `${Math.min(marginUtilization, 100)}%` }}
              role="progressbar"
              aria-valuenow={Math.round(marginUtilization)}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={`Margin utilization: ${Math.round(marginUtilization)}%`}
            />
          </div>
        </div>

        {/* Segment breakdown */}
        {data?.segments && data.segments.length > 0 && (
          <div className="pt-2 border-t border-dashboard-border">
            <p className="text-xs text-dashboard-muted mb-2">Segment Breakdown</p>
            <div className="space-y-1.5" role="list" aria-label="Margin breakdown by segment">
              {data.segments.map((seg) => (
                <div
                  key={seg.segment}
                  className="flex items-center justify-between"
                  role="listitem"
                >
                  <span className="text-xs text-dashboard-text capitalize">
                    {seg.segment}
                  </span>
                  <div className="flex items-center gap-3">
                    <span className="text-[10px] text-dashboard-muted">
                      Used: {formatCurrency(seg.used)}
                    </span>
                    <span className="text-[10px] text-dashboard-muted">
                      Free: {formatCurrency(seg.available)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
  });
}
