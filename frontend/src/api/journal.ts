/**
 * Trade Journal API client functions.
 * Handles journal entries with filters and aggregate statistics.
 */
import { get } from './client';
import type { TradeJournalEntry, JournalFilters, JournalStats } from './types';

const BASE = '/api/v1/journal';

/** Get journal entries with optional filters. */
export function getJournalEntries(filters?: JournalFilters): Promise<TradeJournalEntry[]> {
  const params = filters ? (filters as unknown as Record<string, unknown>) : undefined;
  return get<TradeJournalEntry[]>(BASE, params);
}

/** Get aggregate journal statistics. */
export function getJournalStats(): Promise<JournalStats> {
  return get<JournalStats>(`${BASE}/stats`);
}
