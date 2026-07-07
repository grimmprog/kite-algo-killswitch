/**
 * API client barrel export.
 * Re-exports all domain-specific API functions and types.
 */

// Core client
export { apiClient, get, post, put, del } from './client';

// Domain clients
export * as scannerApi from './scanner';
export * as indexAnalyzerApi from './indexAnalyzer';
export * as signalsApi from './signals';
export * as settingsApi from './settings';
export * as positionMonitorApi from './positionMonitor';
export * as paperTradingApi from './paperTrading';
export * as journalApi from './journal';
export * as chartsApi from './charts';
export * as statusApi from './status';
export * as aiApi from './ai';

// Types
export type * from './types';
