/**
 * Paper Trading API client functions.
 * Handles virtual account, trade entry/exit, positions, history, and reset.
 */
import { get, post } from './client';
import type { PaperAccount, PaperTrade, PaperTradeEntryRequest, PaperTradeExitRequest } from './types';

const BASE = '/api/v1/paper';

/** Get paper trading account stats. */
export function getPaperAccount(): Promise<PaperAccount> {
  return get<PaperAccount>(`${BASE}/account`);
}

/** Enter a new paper trade. */
export function enterPaperTrade(trade: PaperTradeEntryRequest): Promise<PaperTrade> {
  return post<PaperTrade>(`${BASE}/trades`, trade);
}

/** Exit a paper trade at the given price. */
export function exitPaperTrade(tradeId: number, request: PaperTradeExitRequest): Promise<PaperTrade> {
  return post<PaperTrade>(`${BASE}/trades/${tradeId}/exit`, request);
}

/** Get all open paper positions. */
export function getPaperPositions(): Promise<PaperTrade[]> {
  return get<PaperTrade[]>(`${BASE}/positions`);
}

/** Get paper trade history (closed trades). */
export function getPaperHistory(): Promise<PaperTrade[]> {
  return get<PaperTrade[]>(`${BASE}/history`);
}

/** Reset paper account to starting capital and clear history. */
export function resetPaperAccount(): Promise<PaperAccount> {
  return post<PaperAccount>(`${BASE}/reset`);
}
