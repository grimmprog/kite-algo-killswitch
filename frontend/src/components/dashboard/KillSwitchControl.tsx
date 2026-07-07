import { useState } from 'react';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { useWebSocket } from '../../contexts/WebSocketContext';
import { apiClient } from '../../api/client';

export function KillSwitchControl() {
  const { killSwitchStatus } = useWebSocket();
  const [isLoading, setIsLoading] = useState(false);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [pendingAction, setPendingAction] = useState<'activate' | 'deactivate' | null>(null);

  const isActive = killSwitchStatus?.active ?? false;

  function handleActionClick(action: 'activate' | 'deactivate') {
    setPendingAction(action);
    setShowConfirmDialog(true);
  }

  async function confirmAction() {
    if (!pendingAction) return;

    setIsLoading(true);
    setShowConfirmDialog(false);

    try {
      if (pendingAction === 'activate') {
        await apiClient.post('/api/v1/risk/killswitch/activate');
      } else {
        await apiClient.post('/api/v1/risk/killswitch/deactivate');
      }
    } catch (err) {
      console.error('Kill switch action failed:', err);
    } finally {
      setIsLoading(false);
      setPendingAction(null);
    }
  }

  function cancelAction() {
    setShowConfirmDialog(false);
    setPendingAction(null);
  }

  return (
    <Card title="Kill Switch">
      <div className="space-y-3">
        {/* Status indicator */}
        <div className="flex items-center gap-3">
          <div
            className={`w-3 h-3 rounded-full ${isActive ? 'bg-loss animate-pulse' : 'bg-profit'}`}
            aria-hidden="true"
          />
          <div>
            <p className={`text-sm font-medium ${isActive ? 'text-loss' : 'text-profit'}`}>
              {isActive ? 'ACTIVE — Trading Halted' : 'Inactive — Trading Normal'}
            </p>
            {killSwitchStatus?.reason && (
              <p className="text-xs text-dashboard-muted mt-0.5">
                Reason: {killSwitchStatus.reason}
              </p>
            )}
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex gap-2">
          {!isActive ? (
            <Button
              variant="danger"
              size="sm"
              isLoading={isLoading}
              onClick={() => handleActionClick('activate')}
              aria-label="Activate kill switch to halt all trading"
            >
              Activate Kill Switch
            </Button>
          ) : (
            <Button
              variant="success"
              size="sm"
              isLoading={isLoading}
              onClick={() => handleActionClick('deactivate')}
              aria-label="Deactivate kill switch to resume trading"
            >
              Deactivate Kill Switch
            </Button>
          )}
        </div>
      </div>

      {/* Confirmation Dialog */}
      {showConfirmDialog && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
          role="dialog"
          aria-modal="true"
          aria-labelledby="killswitch-dialog-title"
        >
          <div className="bg-dashboard-card border border-dashboard-border rounded-xl p-6 w-full max-w-sm mx-4">
            <h3
              id="killswitch-dialog-title"
              className="text-lg font-bold text-dashboard-text"
            >
              {pendingAction === 'activate' ? 'Activate Kill Switch?' : 'Deactivate Kill Switch?'}
            </h3>
            <p className="text-sm text-dashboard-muted mt-2">
              {pendingAction === 'activate'
                ? 'This will immediately halt all trading activity and close open orders. Are you sure?'
                : 'This will resume normal trading activity. Are you sure?'
              }
            </p>
            <div className="flex gap-3 mt-5">
              <Button
                variant="secondary"
                size="sm"
                onClick={cancelAction}
              >
                Cancel
              </Button>
              <Button
                variant={pendingAction === 'activate' ? 'danger' : 'success'}
                size="sm"
                onClick={confirmAction}
              >
                {pendingAction === 'activate' ? 'Yes, Activate' : 'Yes, Deactivate'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
