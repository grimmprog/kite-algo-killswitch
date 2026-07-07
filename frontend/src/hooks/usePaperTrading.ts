import { useState, useEffect, useCallback } from 'react';
import { get, post } from '../api/client';

// --- Types ---

export interface PaperAccount {
  userId: number;
  balance: number;
  totalPnl: number;
  winRate: number;
  profitFactor: number;
  roiPct: number;
  totalTrades: number;
}

export interface PaperTrade {
  id: number;
  symbol: string;
  strike: number;
  optionType: 'CE' | 'PE';
  entryPrice: number;
  quantity: number;
  stopLoss: number;
  target: number;
  currentPrice?: number;
  unrealizedPnl?: number;
  status: 'open' | 'closed';
  exitPrice?: number;
  exitReason?: string;
  pnl?: number;
}

export interface PaperTradeEntry {
  symbol: string;
  strike: number;
  optionType: 'CE' | 'PE';
  entryPrice: number;
  quantity: number;
  stopLoss: number;
  target: number;
}

interface UsePaperTradingReturn {
  account: PaperAccount | null;
  openPositions: PaperTrade[];
  tradeHistory: PaperTrade[];
  isLoading: boolean;
  error: string | null;
  fetchAccount: () => Promise<void>;
  enterTrade: (trade: PaperTradeEntry) => Promise<void>;
  exitTrade: (tradeId: number) => Promise<void>;
  fetchOpenPositions: () => Promise<void>;
  fetchTradeHistory: () => Promise<void>;
  resetAccount: () => Promise<void>;
}

/**
 * Hook for paper trading functionality.
 * - Manages virtual trading account state
 * - Provides enter/exit trade, fetch positions/history, and reset actions
 * - No WebSocket events needed — paper trading uses REST API polling
 */
export function usePaperTrading(): UsePaperTradingReturn {
  const [account, setAccount] = useState<PaperAccount | null>(null);
  const [openPositions, setOpenPositions] = useState<PaperTrade[]>([]);
  const [tradeHistory, setTradeHistory] = useState<PaperTrade[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAccount = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const result = await get<PaperAccount>('/api/v1/paper/account');
      setAccount(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch paper account';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const enterTrade = useCallback(async (trade: PaperTradeEntry) => {
    try {
      setError(null);
      const result = await post<PaperTrade>('/api/v1/paper/trades', trade);
      setOpenPositions((prev) => [...prev, result]);
      // Refresh account to get updated balance
      await fetchAccount();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to enter paper trade';
      setError(message);
      throw err;
    }
  }, [fetchAccount]);

  const exitTrade = useCallback(async (tradeId: number) => {
    try {
      setError(null);
      const result = await post<PaperTrade>(`/api/v1/paper/trades/${tradeId}/exit`);
      setOpenPositions((prev) => prev.filter((t) => t.id !== tradeId));
      setTradeHistory((prev) => [result, ...prev]);
      // Refresh account to get updated balance
      await fetchAccount();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to exit paper trade';
      setError(message);
    }
  }, [fetchAccount]);

  const fetchOpenPositions = useCallback(async () => {
    try {
      setError(null);
      const result = await get<PaperTrade[]>('/api/v1/paper/positions');
      setOpenPositions(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch paper positions';
      setError(message);
    }
  }, []);

  const fetchTradeHistory = useCallback(async () => {
    try {
      setError(null);
      const result = await get<PaperTrade[]>('/api/v1/paper/history');
      setTradeHistory(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch paper trade history';
      setError(message);
    }
  }, []);

  const resetAccount = useCallback(async () => {
    try {
      setError(null);
      const result = await post<PaperAccount>('/api/v1/paper/reset');
      setAccount(result);
      setOpenPositions([]);
      setTradeHistory([]);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to reset paper account';
      setError(message);
    }
  }, []);

  // Fetch initial data on mount
  useEffect(() => {
    fetchAccount();
    fetchOpenPositions();
  }, [fetchAccount, fetchOpenPositions]);

  return {
    account,
    openPositions,
    tradeHistory,
    isLoading,
    error,
    fetchAccount,
    enterTrade,
    exitTrade,
    fetchOpenPositions,
    fetchTradeHistory,
    resetAccount,
  };
}
