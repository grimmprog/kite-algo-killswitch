import { useCallback, useEffect, useRef, useState } from 'react';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { getKiteStatus, reconnectKite } from '../../api/settings';
import type { KiteStatusResponse } from '../../api/types';
import { AutoLoginConfig } from './AutoLoginConfig';

/** Color mapping for connection status indicators. */
const STATUS_INDICATOR_CLASSES: Record<string, string> = {
  Connected: 'bg-profit',
  'Token Expired': 'bg-yellow-500',
  Disconnected: 'bg-loss',
};

/** Format ISO token expiry to local "YYYY-MM-DD HH:MM" format. */
function formatExpiryLocal(isoExpiry: string): string {
  const date = new Date(isoExpiry);
  if (isNaN(date.getTime())) return isoExpiry;
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  return `${year}-${month}-${day} ${hours}:${minutes}`;
}

interface KiteConnectionPanelProps {
  /** Optional initial status data to avoid redundant fetch when parent already has it. */
  initialStatus?: KiteStatusResponse | null;
  /** Optional error from parent's initial fetch. */
  initialError?: string | null;
}

export function KiteConnectionPanel({ initialStatus, initialError }: KiteConnectionPanelProps) {
  const [status, setStatus] = useState<KiteStatusResponse | null>(initialStatus ?? null);
  const [loading, setLoading] = useState(!initialStatus && !initialError);
  const [error, setError] = useState<string | null>(initialError ?? null);
  const [reconnecting, setReconnecting] = useState(false);
  const [reconnectError, setReconnectError] = useState<string | null>(null);
  const popupRef = useRef<Window | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getKiteStatus();
      setStatus(data);
      setError(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch Kite status';
      setError(msg);
    }
  }, []);

  // Initial fetch if no initial data provided
  useEffect(() => {
    if (!initialStatus && !initialError) {
      fetchStatus().finally(() => setLoading(false));
    }
  }, [fetchStatus, initialStatus, initialError]);

  // Sync with parent-provided data changes
  useEffect(() => {
    if (initialStatus !== undefined) {
      setStatus(initialStatus);
      setLoading(false);
    }
  }, [initialStatus]);

  useEffect(() => {
    if (initialError !== undefined) {
      setError(initialError);
    }
  }, [initialError]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, []);

  /** Handle reconnect: open OAuth popup and poll for completion. */
  const handleReconnect = useCallback(async () => {
    setReconnecting(true);
    setReconnectError(null);

    try {
      const { login_url } = await reconnectKite();

      // Open OAuth flow in a popup window
      const width = 600;
      const height = 700;
      const left = window.screenX + (window.outerWidth - width) / 2;
      const top = window.screenY + (window.outerHeight - height) / 2;
      const popup = window.open(
        login_url,
        'kite_oauth',
        `width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=yes`
      );
      popupRef.current = popup;

      // Poll: check if popup closed, then refetch status
      pollIntervalRef.current = setInterval(async () => {
        if (!popupRef.current || popupRef.current.closed) {
          if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current);
            pollIntervalRef.current = null;
          }
          // Popup closed — refetch status to see if OAuth succeeded
          try {
            const updatedStatus = await getKiteStatus();
            setStatus(updatedStatus);
            setError(null);
            if (updatedStatus.status !== 'Connected') {
              setReconnectError('OAuth flow was cancelled or did not complete.');
            }
          } catch (fetchErr) {
            const msg = fetchErr instanceof Error
              ? fetchErr.message
              : 'Failed to verify connection after OAuth.';
            setReconnectError(msg);
          }
          setReconnecting(false);
        }
      }, 1000);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to initiate reconnection.';
      setReconnectError(msg);
      setReconnecting(false);
    }
  }, []);

  if (loading) {
    return (
      <Card title="Kite Connect" subtitle="Zerodha Kite API connection management">
        <p className="text-sm text-dashboard-muted">Loading Kite status…</p>
      </Card>
    );
  }

  const indicatorColor = status
    ? STATUS_INDICATOR_CLASSES[status.status] || 'bg-dashboard-muted'
    : 'bg-dashboard-muted';

  return (
    <Card title="Kite Connect" subtitle="Zerodha Kite API connection management">
      {error ? (
        <div role="alert" className="p-3 rounded-lg bg-loss/10 border border-loss/20 text-loss text-sm">
          {error}
        </div>
      ) : status ? (
        <div className="space-y-3">
          {/* Connection Status */}
          <div className="flex items-center justify-between">
            <span className="text-sm text-dashboard-muted">Connection Status</span>
            <span className="inline-flex items-center gap-2">
              <span
                className={`w-2 h-2 rounded-full ${indicatorColor}`}
                aria-hidden="true"
              />
              <span className="text-sm font-medium text-dashboard-text">
                {status.status}
              </span>
            </span>
          </div>

          {/* Token Expiry */}
          {status.token_expiry && (
            <div className="flex items-center justify-between">
              <span className="text-sm text-dashboard-muted">Token Expiry</span>
              <span className="text-sm text-dashboard-text">
                {formatExpiryLocal(status.token_expiry)}
              </span>
            </div>
          )}

          {/* Time Remaining */}
          {status.time_remaining && (
            <div className="flex items-center justify-between">
              <span className="text-sm text-dashboard-muted">Time Remaining</span>
              <span className="text-sm text-dashboard-text">{status.time_remaining}</span>
            </div>
          )}

          {/* Reconnect Button */}
          <div className="pt-2 border-t border-dashboard-border">
            <Button
              variant="primary"
              size="sm"
              isLoading={reconnecting}
              onClick={handleReconnect}
              disabled={reconnecting}
            >
              Reconnect
            </Button>
          </div>

          {/* Reconnect Error */}
          {reconnectError && (
            <div
              role="alert"
              className="p-3 rounded-lg bg-loss/10 border border-loss/20 text-loss text-sm"
            >
              {reconnectError}
            </div>
          )}

          {/* Auto-Login Configuration */}
          <AutoLoginConfig kiteStatus={status} onUpdated={fetchStatus} />
        </div>
      ) : null}
    </Card>
  );
}
