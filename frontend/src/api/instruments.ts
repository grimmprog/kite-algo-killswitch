/**
 * Instruments API client functions.
 * Option chain, instrument search, and live quotes.
 */
import { get } from './client';
import type { OptionChainResponse, InstrumentSearchResult, QuoteItem } from './types';

const INSTRUMENTS_BASE = '/api/v1/instruments';

/** Get option chain data for NIFTY or BANKNIFTY. */
export function getOptionChain(index: string, expiry: string = 'nearest'): Promise<OptionChainResponse> {
  return get<OptionChainResponse>(`${INSTRUMENTS_BASE}/option-chain`, { index, expiry });
}

/** Get available expiry dates for an index. */
export function getExpiries(index: string): Promise<{ index: string; expiries: string[] }> {
  return get<{ index: string; expiries: string[] }>(`${INSTRUMENTS_BASE}/expiries`, { index });
}

/** Search instruments by name/symbol. */
export function searchInstruments(query: string, exchange: string = 'NSE'): Promise<InstrumentSearchResult[]> {
  return get<InstrumentSearchResult[]>(`${INSTRUMENTS_BASE}/search`, { q: query, exchange });
}

/** Get live quotes for specific symbols. */
export function getQuotes(symbols: string[]): Promise<QuoteItem[]> {
  return get<QuoteItem[]>(`${INSTRUMENTS_BASE}/quote`, { symbols: symbols.join(',') });
}
