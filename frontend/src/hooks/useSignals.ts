import { useState, useEffect, useCallback, useRef } from 'react';
import { useWebSocket } from '../contexts/WebSocketContext';
import type { SignalExpiredEvent, SignalPriceUpdateEvent } from '../contexts/WebSocketContext';
import { get, post } from '../api/client';

// --- Types ---

export type SignalStatus = 'pending' | 'approved' | 'rejected' | 'expired';

export interface TradingSignal {
  id: string;
  symbol: string;
  confidenceScore: number;
  entryPrice: number;
  stopLoss: number;
  targetPrice: number;
  maxLoss: number;
  status: SignalStatus;
  createdAt: string;
  expiresAt: string;
  countdownSeconds: number;
  remainingSeconds: number;
  aiQualityRating?: string;
  aiWarnings?: string[];
}

export interface SignalPriceInfo {
  signalId: string;
  symbol: string;
  currentPrice: number;
  changeFromEntry: number;
  changePct: number;
}

interface UseSignalsReturn {
  pendingSignals: TradingSignal[];
  signalPrices: Map<string, SignalPriceInfo>;
  isLoading: boolean;
  error: string | null;
  approveSignal: (signalId: string) => Promise<void>;
  rejectSignal: (signalId: string) => Promise<void>;
  fetchPendingSignals: () => Promise<void>;
  fetchSignalHistory: () => Promise<TradingSignal[]>;
}

/**
 * Hook for signal approval workflow.
 * - Fetches pending signals from API
 * - Subscribes to signal_expired and signal_price_update WebSocket events
 * - Manages countdown state with client-side timer
 * - Provides approve/reject actions
 */
export function useSignals(): UseSignalsReturn {
  const { on, off } = useWebSocket();

  const [pendingSignals, setPendingSignals] = useState<TradingSignal[]>([]);
  const [signalPrices, setSignalPrices] = useState<Map<string, SignalPriceInfo>>(new Map());
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Client-side countdown timer for pending signals
  useEffect(() => {
    countdownRef.current = setInterval(() => {
      setPendingSignals((prev) =>
        prev
          .map((signal) => {
            if (signal.status !== 'pending') return signal;
            const remaining = Math.max(0, signal.remainingSeconds - 1);
            if (remaining === 0) {
              return { ...signal, remainingSeconds: 0, status: 'expired' as SignalStatus };
            }
            return { ...signal, remainingSeconds: remaining };
          })
          .filter((signal) => signal.status === 'pending')
      );
    }, 1000);

    return () => {
      if (countdownRef.current) clearInterval(countdownRef.current);
    };
  }, []);

  // Subscribe to WebSocket events
  useEffect(() => {
    const handleSignalExpired = (data: SignalExpiredEvent) => {
      setPendingSignals((prev) => prev.filter((s) => s.id !== data.id));
    };

    const handlePriceUpdate = (data: SignalPriceUpdateEvent) => {
      setSignalPrices((prev) => {
        const updated = new Map(prev);
        updated.set(data.signalId, {
          signalId: data.signalId,
          symbol: data.symbol,
          currentPrice: data.currentPrice,
          changeFromEntry: data.changeFromEntry,
          changePct: data.changePct,
        });
        return updated;
      });
    };

    on<SignalExpiredEvent>('signal_expired', handleSignalExpired);
    on<SignalPriceUpdateEvent>('signal_price_update', handlePriceUpdate);

    return () => {
      off<SignalExpiredEvent>('signal_expired', handleSignalExpired);
      off<SignalPriceUpdateEvent>('signal_price_update', handlePriceUpdate);
    };
  }, [on, off]);

  const fetchPendingSignals = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const result = await get<TradingSignal[]>('/api/v1/signals/pending');
      setPendingSignals(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch pending signals';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const approveSignal = useCallback(async (signalId: string) => {
    try {
      await post(`/api/v1/signals/${signalId}/approve`);
      setPendingSignals((prev) => prev.filter((s) => s.id !== signalId));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to approve signal';
      setError(message);
    }
  }, []);

  const rejectSignal = useCallback(async (signalId: string) => {
    try {
      await post(`/api/v1/signals/${signalId}/reject`);
      setPendingSignals((prev) => prev.filter((s) => s.id !== signalId));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to reject signal';
      setError(message);
    }
  }, []);

  const fetchSignalHistory = useCallback(async () => {
    const result = await get<TradingSignal[]>('/api/v1/signals/history');
    return result;
  }, []);

  // Fetch pending signals on mount
  useEffect(() => {
    fetchPendingSignals();
  }, [fetchPendingSignals]);

  return {
    pendingSignals,
    signalPrices,
    isLoading,
    error,
    approveSignal,
    rejectSignal,
    fetchPendingSignals,
    fetchSignalHistory,
  };
}
