import { useCallback, useEffect, useState } from 'react';
import { Card } from '../ui/Card';
import { KiteConnectionPanel } from './KiteConnectionPanel';
import { DhanConnectionPanel } from './DhanConnectionPanel';
import { getKiteStatus, getDhanStatus } from '../../api/settings';
import type { KiteStatusResponse, DhanStatusResponse } from '../../api/types';

export function BrokersTab() {
  const [kiteStatus, setKiteStatus] = useState<KiteStatusResponse | null>(null);
  const [dhanStatus, setDhanStatus] = useState<DhanStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [kiteError, setKiteError] = useState<string | null>(null);
  const [dhanError, setDhanError] = useState<string | null>(null);

  const fetchStatuses = useCallback(async () => {
    setLoading(true);
    setKiteError(null);
    setDhanError(null);

    const [kiteResult, dhanResult] = await Promise.allSettled([
      getKiteStatus(),
      getDhanStatus(),
    ]);

    if (kiteResult.status === 'fulfilled') {
      setKiteStatus(kiteResult.value);
    } else {
      const msg = kiteResult.reason instanceof Error
        ? kiteResult.reason.message
        : 'Failed to fetch Kite status';
      setKiteError(msg);
    }

    if (dhanResult.status === 'fulfilled') {
      setDhanStatus(dhanResult.value);
    } else {
      const msg = dhanResult.reason instanceof Error
        ? dhanResult.reason.message
        : 'Failed to fetch Dhan status';
      setDhanError(msg);
    }

    setLoading(false);
  }, []);

  useEffect(() => {
    fetchStatuses();
  }, [fetchStatuses]);

  if (loading) {
    return (
      <div className="space-y-4">
        <Card title="Kite Connect">
          <p className="text-sm text-dashboard-muted">Loading Kite status…</p>
        </Card>
        <Card title="Dhan Broker">
          <p className="text-sm text-dashboard-muted">Loading Dhan status…</p>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Kite Connect Section — dedicated panel with Reconnect support */}
      <KiteConnectionPanel initialStatus={kiteStatus} initialError={kiteError} />

      {/* Dhan Broker Section — dedicated panel with Connect/Disconnect support */}
      <DhanConnectionPanel
        status={dhanStatus}
        onStatusChange={fetchStatuses}
        error={dhanError}
      />
    </div>
  );
}
