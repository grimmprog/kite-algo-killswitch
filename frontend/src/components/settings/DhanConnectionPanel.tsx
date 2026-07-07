import { useState, type FormEvent } from 'react';
import { Card } from '../ui/Card';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';
import { connectDhan, disconnectDhan } from '../../api/settings';
import type { DhanStatusResponse } from '../../api/types';
import { AxiosError } from 'axios';

const STATUS_COLORS: Record<string, string> = {
  Connected: 'bg-profit',
  Disconnected: 'bg-loss',
  Error: 'bg-loss',
};

function StatusIndicator({ status }: { status: string }) {
  const color = STATUS_COLORS[status] || 'bg-dashboard-muted';
  return (
    <span className="inline-flex items-center gap-2">
      <span className={`w-2 h-2 rounded-full ${color}`} aria-hidden="true" />
      <span className="text-sm font-medium text-dashboard-text">{status}</span>
    </span>
  );
}

interface DhanConnectionPanelProps {
  status: DhanStatusResponse | null;
  onStatusChange: () => void;
  error?: string | null;
}

export function DhanConnectionPanel({ status, onStatusChange, error: fetchError }: DhanConnectionPanelProps) {
  const [clientId, setClientId] = useState('');
  const [accessToken, setAccessToken] = useState('');
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const isConnected = status?.status === 'Connected';

  async function handleConnect(e: FormEvent) {
    e.preventDefault();
    setErrorMessage(null);

    if (!clientId.trim() || !accessToken.trim()) {
      setErrorMessage('Both Client ID and Access Token are required');
      return;
    }

    setConnecting(true);
    try {
      await connectDhan({ client_id: clientId.trim(), access_token: accessToken.trim() });
      setClientId('');
      setAccessToken('');
      onStatusChange();
    } catch (err) {
      if (err instanceof AxiosError && err.response?.status === 422) {
        const detail = err.response.data?.detail;
        setErrorMessage(typeof detail === 'string' ? detail : 'Connection failed: invalid credentials');
      } else if (err instanceof AxiosError && err.response?.data?.detail) {
        setErrorMessage(err.response.data.detail);
      } else {
        setErrorMessage('Failed to connect. Please try again.');
      }
    } finally {
      setConnecting(false);
    }
  }

  async function handleDisconnect() {
    setErrorMessage(null);
    setDisconnecting(true);
    try {
      await disconnectDhan();
      onStatusChange();
    } catch (err) {
      if (err instanceof AxiosError && err.response?.data?.detail) {
        setErrorMessage(err.response.data.detail);
      } else {
        setErrorMessage('Failed to disconnect. Please try again.');
      }
    } finally {
      setDisconnecting(false);
    }
  }

  return (
    <Card title="Dhan Broker" subtitle="Dhan trading account connection management">
      {fetchError ? (
        <div role="alert" className="p-3 rounded-lg bg-loss/10 border border-loss/20 text-loss text-sm">
          {fetchError}
        </div>
      ) : (
        <div className="space-y-4">
          {/* Status Display */}
          <div className="flex items-center justify-between">
            <span className="text-sm text-dashboard-muted">Connection Status</span>
            <StatusIndicator status={status?.status || 'Disconnected'} />
          </div>

          {/* Connected State */}
          {isConnected && (
            <>
              {status.account_name && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-dashboard-muted">Account Holder</span>
                  <span className="text-sm text-dashboard-text">{status.account_name}</span>
                </div>
              )}
              <Button
                variant="danger"
                size="sm"
                onClick={handleDisconnect}
                isLoading={disconnecting}
                disabled={disconnecting}
              >
                Disconnect
              </Button>
            </>
          )}

          {/* Disconnected / Error State — Show Connect Form */}
          {!isConnected && (
            <form onSubmit={handleConnect} className="space-y-3">
              <Input
                label="Client ID"
                placeholder="Enter Dhan Client ID"
                value={clientId}
                onChange={(e) => setClientId(e.target.value)}
                disabled={connecting}
              />
              <Input
                label="Access Token"
                type="password"
                placeholder="Enter Dhan Access Token"
                value={accessToken}
                onChange={(e) => setAccessToken(e.target.value)}
                disabled={connecting}
              />
              <Button
                type="submit"
                variant="primary"
                size="sm"
                isLoading={connecting}
                disabled={connecting}
              >
                Connect
              </Button>
            </form>
          )}

          {/* Error Message Display */}
          {errorMessage && (
            <div role="alert" className="p-3 rounded-lg bg-loss/10 border border-loss/20 text-loss text-sm">
              {errorMessage}
            </div>
          )}

          {/* Dhan status error from backend */}
          {status?.error_message && !errorMessage && (
            <div role="alert" className="p-3 rounded-lg bg-loss/10 border border-loss/20 text-loss text-sm">
              {status.error_message}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
