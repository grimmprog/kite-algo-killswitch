import { useState, useEffect, useCallback } from 'react';
import { useWebSocket } from '../contexts/WebSocketContext';
import { get } from '../api/client';

interface Position {
  symbol: string;
  quantity: number;
  entryPrice: number;
  currentPrice: number;
  pnl: number;
}

interface RiskMetrics {
  pnl: number;
  netDelta: number;
  netGamma: number;
  netVega: number;
  marginUsed: number;
  updatedAt: string;
}

interface KillSwitchStatus {
  active: boolean;
  reason?: string;
  timestamp: string;
}

interface RealtimeData {
  positions: Position[];
  riskMetrics: RiskMetrics | null;
  killSwitchStatus: KillSwitchStatus | null;
  isConnected: boolean;
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

/**
 * Hook that combines WebSocket real-time data with REST API fallback for initial load.
 *
 * On mount, fetches initial data from the REST API (/api/v1/positions, /api/v1/risk).
 * Once WebSocket updates arrive, those take priority as the source of truth.
 * Provides a `refresh` method to manually re-fetch from REST if needed.
 */
export function useRealtimeData(): RealtimeData {
  const {
    isConnected,
    positions: wsPositions,
    riskMetrics: wsRiskMetrics,
    killSwitchStatus: wsKillSwitchStatus,
  } = useWebSocket();

  const [restPositions, setRestPositions] = useState<Position[]>([]);
  const [restRiskMetrics, setRestRiskMetrics] = useState<RiskMetrics | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchInitialData = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);

      const [positionsData, riskData] = await Promise.allSettled([
        get<Position[]>('/api/v1/positions'),
        get<RiskMetrics>('/api/v1/risk'),
      ]);

      if (positionsData.status === 'fulfilled') {
        setRestPositions(positionsData.value);
      }
      if (riskData.status === 'fulfilled') {
        setRestRiskMetrics(riskData.value);
      }

      // Only set error if both failed
      if (positionsData.status === 'rejected' && riskData.status === 'rejected') {
        setError('Failed to load initial data. Waiting for live updates...');
      }
    } catch {
      setError('Failed to load initial data.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Fetch initial data on mount
  useEffect(() => {
    fetchInitialData();
  }, [fetchInitialData]);

  // Use WebSocket data when available, fall back to REST data
  const positions: Position[] = wsPositions.length > 0 ? wsPositions : restPositions;
  const riskMetrics: RiskMetrics | null = wsRiskMetrics || restRiskMetrics;
  const killSwitchStatus: KillSwitchStatus | null = wsKillSwitchStatus;

  return {
    positions,
    riskMetrics,
    killSwitchStatus,
    isConnected,
    isLoading,
    error,
    refresh: fetchInitialData,
  };
}
