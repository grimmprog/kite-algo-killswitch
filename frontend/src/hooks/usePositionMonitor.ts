import { useState, useEffect, useCallback } from 'react';
import { useWebSocket } from '../contexts/WebSocketContext';
import type {
  PositionMonitorUpdateEvent,
  ExitConditionUpdateEvent,
  AutoExitTriggeredEvent,
} from '../contexts/WebSocketContext';
import { get, post, put } from '../api/client';

// --- Types ---

export interface MonitoredPosition {
  positionId: number;
  symbol: string;
  entryPrice: number;
  currentPrice: number;
  stopLoss: number;
  target: number;
  trailingStopEnabled: boolean;
  trailingStopLevel?: number;
  unrealizedPnl: number;
  distanceToSlPct: number;
  distanceToTargetPct: number;
  status: string;
}

export interface ExitCondition {
  name: string;
  description: string;
  isMet: boolean;
  details?: string;
}

export interface AutoExitEvent {
  positionId: number;
  symbol: string;
  reason: string;
  exitPrice: number;
  pnl: number;
  timestamp: string;
}

interface UsePositionMonitorReturn {
  monitoredPositions: MonitoredPosition[];
  exitConditions: Map<number, ExitCondition[]>;
  autoExitEvents: AutoExitEvent[];
  isMonitorActive: boolean;
  isLoading: boolean;
  error: string | null;
  fetchMonitoredPositions: () => Promise<void>;
  fetchExitConditions: (positionId: number) => Promise<ExitCondition[]>;
  manualExit: (positionId: number) => Promise<void>;
  toggleMonitor: (active: boolean) => Promise<void>;
  clearAutoExitEvents: () => void;
}

/**
 * Hook for position monitoring with SL/Target tracking.
 * - Subscribes to position_monitor_update, exit_condition_update, auto_exit_triggered events
 * - Manages monitored positions state with real-time updates
 * - Provides manual exit and monitor toggle actions
 */
export function usePositionMonitor(): UsePositionMonitorReturn {
  const { on, off } = useWebSocket();

  const [monitoredPositions, setMonitoredPositions] = useState<MonitoredPosition[]>([]);
  const [exitConditions, setExitConditions] = useState<Map<number, ExitCondition[]>>(new Map());
  const [autoExitEvents, setAutoExitEvents] = useState<AutoExitEvent[]>([]);
  const [isMonitorActive, setIsMonitorActive] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Subscribe to WebSocket events
  useEffect(() => {
    const handlePositionUpdate = (data: PositionMonitorUpdateEvent) => {
      setMonitoredPositions((prev) => {
        const idx = prev.findIndex((p) => p.positionId === data.positionId);
        if (idx >= 0) {
          const updated = [...prev];
          updated[idx] = data;
          return updated;
        }
        return [...prev, data];
      });
    };

    const handleExitConditionUpdate = (data: ExitConditionUpdateEvent) => {
      setExitConditions((prev) => {
        const updated = new Map(prev);
        updated.set(data.positionId, data.conditions);
        return updated;
      });
    };

    const handleAutoExit = (data: AutoExitTriggeredEvent) => {
      setAutoExitEvents((prev) => [data, ...prev]);
      // Remove position from monitored list
      setMonitoredPositions((prev) =>
        prev.filter((p) => p.positionId !== data.positionId)
      );
    };

    on<PositionMonitorUpdateEvent>('position_monitor_update', handlePositionUpdate);
    on<ExitConditionUpdateEvent>('exit_condition_update', handleExitConditionUpdate);
    on<AutoExitTriggeredEvent>('auto_exit_triggered', handleAutoExit);

    return () => {
      off<PositionMonitorUpdateEvent>('position_monitor_update', handlePositionUpdate);
      off<ExitConditionUpdateEvent>('exit_condition_update', handleExitConditionUpdate);
      off<AutoExitTriggeredEvent>('auto_exit_triggered', handleAutoExit);
    };
  }, [on, off]);

  const fetchMonitoredPositions = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const result = await get<MonitoredPosition[]>('/api/v1/positions/monitor');
      setMonitoredPositions(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch monitored positions';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const fetchExitConditions = useCallback(async (positionId: number) => {
    try {
      const result = await get<ExitCondition[]>(`/api/v1/positions/${positionId}/exit-rules`);
      setExitConditions((prev) => {
        const updated = new Map(prev);
        updated.set(positionId, result);
        return updated;
      });
      return result;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch exit conditions';
      setError(message);
      return [];
    }
  }, []);

  const manualExit = useCallback(async (positionId: number) => {
    try {
      setError(null);
      await post(`/api/v1/positions/${positionId}/exit`);
      setMonitoredPositions((prev) => prev.filter((p) => p.positionId !== positionId));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to execute manual exit';
      setError(message);
    }
  }, []);

  const toggleMonitor = useCallback(async (active: boolean) => {
    try {
      setError(null);
      await put('/api/v1/monitor/toggle', { active });
      setIsMonitorActive(active);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to toggle monitor';
      setError(message);
    }
  }, []);

  const clearAutoExitEvents = useCallback(() => {
    setAutoExitEvents([]);
  }, []);

  // Fetch initial data on mount
  useEffect(() => {
    fetchMonitoredPositions();
  }, [fetchMonitoredPositions]);

  return {
    monitoredPositions,
    exitConditions,
    autoExitEvents,
    isMonitorActive,
    isLoading,
    error,
    fetchMonitoredPositions,
    fetchExitConditions,
    manualExit,
    toggleMonitor,
    clearAutoExitEvents,
  };
}
