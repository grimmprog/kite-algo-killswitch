import { useState, useEffect, useCallback } from 'react';
import { useWebSocket } from '../contexts/WebSocketContext';
import type { ScanSignalEvent, ConsolidationUpdateEvent } from '../contexts/WebSocketContext';
import { get, post } from '../api/client';

// --- Types ---

export interface ScanSignal {
  id: string;
  symbol: string;
  scanType: 'trend_pullback' | 'consolidation_breakout' | 'multi_touch_breakout';
  confidenceScore: number;
  entryPrice: number;
  stopLoss: number;
  targetPrice: number;
  maxPotentialLoss: number;
  timestamp: string;
  metadata: Record<string, unknown>;
}

export interface BreakoutSignal {
  symbol: string;
  direction: number;
  directionLabel: 'BUY_CALL' | 'BUY_PUT';
  levelValue: number;
  touchCount: number;
  breakoutPrice: number;
  volumeConfirmed: boolean;
  atrValue: number;
  initialStopLoss: number;
  trailingStopLoss: number | null;
  confidenceScore: number;
  timestamp: string;
}

export interface ConsolidationPattern {
  symbol: string;
  rangeHigh: number;
  rangeLow: number;
  avgPrice: number;
  candleCount: number;
  durationMinutes: number;
  isBreakout: boolean;
  breakoutPrice?: number;
}

interface ScannerState {
  signals: ScanSignal[];
  breakoutSignals: BreakoutSignal[];
  consolidations: ConsolidationPattern[];
  isScanning: boolean;
  isBreakoutScanning: boolean;
  scanError: string | null;
  lastScanTime: string | null;
  lastBreakoutScanTime: string | null;
}

interface UseScannerReturn extends ScannerState {
  triggerTrendPullbackScan: () => Promise<void>;
  triggerBreakoutScan: () => Promise<void>;
  fetchConsolidations: () => Promise<void>;
  fetchSignalHistory: () => Promise<ScanSignal[]>;
}

/**
 * Hook for scanner functionality.
 * - Triggers trend pullback scans via API
 * - Subscribes to real-time signal_detected and consolidation_update events
 * - Manages scanner state (signals, consolidations, loading, errors)
 */
export function useScanner(): UseScannerReturn {
  const { on, off } = useWebSocket();

  const [signals, setSignals] = useState<ScanSignal[]>([]);
  const [breakoutSignals, setBreakoutSignals] = useState<BreakoutSignal[]>([]);
  const [consolidations, setConsolidations] = useState<ConsolidationPattern[]>([]);
  const [isScanning, setIsScanning] = useState(false);
  const [isBreakoutScanning, setIsBreakoutScanning] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [lastScanTime, setLastScanTime] = useState<string | null>(null);
  const [lastBreakoutScanTime, setLastBreakoutScanTime] = useState<string | null>(null);

  // Subscribe to real-time scanner events
  useEffect(() => {
    const handleSignalDetected = (data: ScanSignalEvent) => {
      setSignals((prev) => [data, ...prev]);
    };

    const handleConsolidationUpdate = (data: ConsolidationUpdateEvent) => {
      setConsolidations((prev) => {
        const idx = prev.findIndex((c) => c.symbol === data.symbol);
        if (idx >= 0) {
          const updated = [...prev];
          updated[idx] = data;
          return updated;
        }
        return [data, ...prev];
      });
    };

    on<ScanSignalEvent>('signal_detected', handleSignalDetected);
    on<ConsolidationUpdateEvent>('consolidation_update', handleConsolidationUpdate);

    return () => {
      off<ScanSignalEvent>('signal_detected', handleSignalDetected);
      off<ConsolidationUpdateEvent>('consolidation_update', handleConsolidationUpdate);
    };
  }, [on, off]);

  const triggerTrendPullbackScan = useCallback(async () => {
    try {
      setIsScanning(true);
      setScanError(null);
      const result = await post<ScanSignal[]>('/api/v1/scanner/trend-pullback');
      setSignals(Array.isArray(result) ? result : []);
      setLastScanTime(new Date().toISOString());
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Scan failed';
      setScanError(message);
    } finally {
      setIsScanning(false);
    }
  }, []);

  const triggerBreakoutScan = useCallback(async () => {
    try {
      setIsBreakoutScanning(true);
      setScanError(null);
      const result = await post<{ signals: BreakoutSignal[] }>('/api/v1/scanner/breakout');
      setBreakoutSignals(Array.isArray(result?.signals) ? result.signals : []);
      setLastBreakoutScanTime(new Date().toISOString());
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Breakout scan failed';
      setScanError(message);
    } finally {
      setIsBreakoutScanning(false);
    }
  }, []);

  const fetchConsolidations = useCallback(async () => {
    try {
      const result = await get<ConsolidationPattern[]>('/api/v1/scanner/consolidation');
      setConsolidations(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch consolidations';
      setScanError(message);
    }
  }, []);

  const fetchSignalHistory = useCallback(async () => {
    const result = await get<ScanSignal[]>('/api/v1/scanner/signals');
    return result;
  }, []);

  return {
    signals,
    breakoutSignals,
    consolidations,
    isScanning,
    isBreakoutScanning,
    scanError,
    lastScanTime,
    lastBreakoutScanTime,
    triggerTrendPullbackScan,
    triggerBreakoutScan,
    fetchConsolidations,
    fetchSignalHistory,
  };
}
