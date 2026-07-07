import { useState, useEffect, useCallback } from 'react';
import { Card } from '../ui/Card';
import { get } from '../../api/client';

// --- Types ---

type WorkerStatus = 'running' | 'stopped' | 'unknown';
type SessionStatus = 'connected' | 'disconnected' | 'expired';

interface WorkerInfo {
  name: string;
  status: WorkerStatus;
  lastHeartbeat?: string;
}

interface SystemStatusData {
  marketCountdown: string;
  marketState: 'pre_market' | 'open' | 'closed';
  timeToMarketEvent: number; // seconds until open or close
  sessionStatus: SessionStatus;
  workers: WorkerInfo[];
}

const REFRESH_INTERVAL_MS = 30_000; // 30 seconds

const sessionStatusStyles: Record<SessionStatus, { label: string; color: string }> = {
  connected: { label: 'Connected', color: 'bg-profit' },
  disconnected: { label: 'Disconnected', color: 'bg-loss' },
  expired: { label: 'Session Expired', color: 'bg-amber-400' },
};

const workerStatusStyles: Record<WorkerStatus, { dot: string; label: string }> = {
  running: { dot: 'bg-profit', label: 'Running' },
  stopped: { dot: 'bg-loss', label: 'Stopped' },
  unknown: { dot: 'bg-dashboard-muted', label: 'Unknown' },
};

/**
 * SystemStatus — Dashboard widget for market countdown, session status, and worker statuses.
 * - Shows time remaining until market open (pre-market) or close (during hours)
 * - Displays Zerodha session status (connected/disconnected/expired)
 * - Shows background worker statuses with warning for non-running workers
 * - Auto-refreshes every 30 seconds
 * - Validates: Requirements 16.1-16.5
 */
export function SystemStatus() {
  const [data, setData] = useState<SystemStatusData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [countdown, setCountdown] = useState<number>(0);

  const fetchStatus = useCallback(async () => {
    try {
      setError(null);
      const result = await get<SystemStatusData>('/api/v1/status/system');
      setData(result);
      setCountdown(result.timeToMarketEvent);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch system status';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Initial fetch and 30s refresh interval
  useEffect(() => {
    fetchStatus();

    const interval = setInterval(fetchStatus, REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  // Client-side countdown tick (update every second between fetches)
  useEffect(() => {
    if (countdown <= 0) return;

    const timer = setInterval(() => {
      setCountdown((prev) => Math.max(prev - 1, 0));
    }, 1000);

    return () => clearInterval(timer);
  }, [countdown]);

  const formatCountdown = (totalSeconds: number): string => {
    if (totalSeconds <= 0) return '00:00:00';
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
  };

  const hasUnhealthyWorkers = data?.workers.some((w) => w.status !== 'running') ?? false;
  const session = data?.sessionStatus ?? 'disconnected';
  const sessionStyle = sessionStatusStyles[session];

  if (isLoading && !data) {
    return (
      <Card title="System Status">
        <div className="animate-pulse space-y-3" aria-label="Loading system status">
          <div className="h-6 bg-dashboard-border rounded w-1/2" />
          <div className="h-4 bg-dashboard-border rounded w-3/4" />
          <div className="h-4 bg-dashboard-border rounded w-2/3" />
        </div>
      </Card>
    );
  }

  if (error && !data) {
    return (
      <Card title="System Status">
        <p className="text-xs text-loss" role="alert">
          {error}
        </p>
      </Card>
    );
  }

  return (
    <Card title="System Status">
      <div className="space-y-3">
        {/* Market countdown */}
        <div>
          <p className="text-xs text-dashboard-muted">
            {data?.marketState === 'pre_market'
              ? 'Market Opens In'
              : data?.marketState === 'open'
                ? 'Market Closes In'
                : 'Market Closed'}
          </p>
          <p
            className="text-xl font-mono font-bold text-dashboard-text mt-0.5"
            aria-label={`${
              data?.marketState === 'pre_market'
                ? 'Time until market opens'
                : data?.marketState === 'open'
                  ? 'Time until market closes'
                  : 'Market is closed'
            }: ${formatCountdown(countdown)}`}
            aria-live="polite"
            aria-atomic="true"
          >
            {data?.marketState === 'closed' ? '—' : formatCountdown(countdown)}
          </p>
        </div>

        {/* Session status */}
        <div className="flex items-center justify-between pt-2 border-t border-dashboard-border">
          <span className="text-xs text-dashboard-muted">Zerodha Session</span>
          <div className="flex items-center gap-1.5">
            <span
              className={`w-2 h-2 rounded-full ${sessionStyle.color}`}
              aria-hidden="true"
            />
            <span
              className={`text-xs font-medium ${
                session === 'connected'
                  ? 'text-profit'
                  : session === 'expired'
                    ? 'text-amber-400'
                    : 'text-loss'
              }`}
            >
              {sessionStyle.label}
            </span>
          </div>
        </div>

        {/* Worker statuses */}
        <div className="pt-2 border-t border-dashboard-border">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-dashboard-muted">Workers</span>
            {hasUnhealthyWorkers && (
              <span
                className="text-[10px] text-amber-400 font-medium"
                role="alert"
              >
                ⚠ Issue detected
              </span>
            )}
          </div>
          <div className="space-y-1.5" role="list" aria-label="Background worker statuses">
            {data?.workers.map((worker) => {
              const style = workerStatusStyles[worker.status];
              return (
                <div
                  key={worker.name}
                  className="flex items-center justify-between"
                  role="listitem"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={`w-2 h-2 rounded-full ${style.dot} ${
                        worker.status === 'running' ? '' : 'animate-pulse'
                      }`}
                      aria-hidden="true"
                    />
                    <span className="text-xs text-dashboard-text">
                      {worker.name}
                    </span>
                  </div>
                  <span
                    className={`text-[10px] font-medium ${
                      worker.status === 'running'
                        ? 'text-profit'
                        : worker.status === 'stopped'
                          ? 'text-loss'
                          : 'text-dashboard-muted'
                    }`}
                  >
                    {style.label}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </Card>
  );
}
