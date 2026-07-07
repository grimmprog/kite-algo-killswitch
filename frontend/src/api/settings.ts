/**
 * Settings API client functions.
 * Handles strategy settings, kill switch thresholds, segment management, and AI config.
 */
import { get, put, post, del } from './client';
import type {
  StrategySettings,
  KillSwitchThresholds,
  SegmentStatus,
  AISettings,
  KiteStatusResponse,
  DhanStatusResponse,
  DhanConnectRequest,
  AutoLoginRequest,
  AutoLoginResponse,
  DataSourcesRequest,
  DataSourcesResponse,
  LiveMarketResponse,
} from './types';

const BASE = '/api/v1/settings';

// --- Strategy Settings ---

/** Get current strategy settings. */
export function getStrategySettings(): Promise<StrategySettings> {
  return get<StrategySettings>(`${BASE}/strategy`);
}

/** Update strategy settings. */
export function updateStrategySettings(settings: StrategySettings): Promise<StrategySettings> {
  return put<StrategySettings>(`${BASE}/strategy`, settings);
}

// --- Kill Switch Thresholds ---

/** Get current kill switch thresholds. */
export function getKillSwitchThresholds(): Promise<KillSwitchThresholds> {
  return get<KillSwitchThresholds>(`${BASE}/killswitch`);
}

/** Update kill switch thresholds. Applied immediately to running monitor. */
export function updateKillSwitchThresholds(thresholds: KillSwitchThresholds): Promise<KillSwitchThresholds> {
  return put<KillSwitchThresholds>(`${BASE}/killswitch`, thresholds);
}

// --- Segment Management ---

/** Get all segment statuses. */
export function getSegments(): Promise<SegmentStatus[]> {
  return get<SegmentStatus[]>(`${BASE}/segments`);
}

/** Toggle a segment's active status. */
export function updateSegment(segment: string, data: { is_active: boolean }): Promise<SegmentStatus> {
  return put<SegmentStatus>(`${BASE}/segments/${segment}`, data);
}

// --- AI Settings ---

/** Get AI configuration. */
export function getAISettings(): Promise<AISettings> {
  return get<AISettings>(`${BASE}/ai`);
}

/** Update AI configuration. */
export function updateAISettings(settings: Partial<AISettings>): Promise<AISettings> {
  return put<AISettings>(`${BASE}/ai`, settings);
}


// --- Broker Settings ---

const BROKERS_BASE = '/api/v1/settings/brokers';

/** Get Kite connection status. */
export function getKiteStatus(): Promise<KiteStatusResponse> {
  return get<KiteStatusResponse>(`${BROKERS_BASE}/kite`);
}

/** Initiate Kite OAuth reconnection flow. Returns login URL. */
export function reconnectKite(): Promise<{ login_url: string }> {
  return post<{ login_url: string }>(`${BROKERS_BASE}/kite/reconnect`);
}

/** Update auto-login configuration (TOTP key and enabled state). */
export function updateAutoLogin(request: AutoLoginRequest): Promise<AutoLoginResponse> {
  return put<AutoLoginResponse>(`${BROKERS_BASE}/kite/auto-login`, request);
}

/** Get Dhan connection status. */
export function getDhanStatus(): Promise<DhanStatusResponse> {
  return get<DhanStatusResponse>(`${BROKERS_BASE}/dhan`);
}

/** Connect Dhan broker with client ID and access token. */
export function connectDhan(request: DhanConnectRequest): Promise<DhanStatusResponse> {
  return post<DhanStatusResponse>(`${BROKERS_BASE}/dhan/connect`, request);
}

/** Disconnect Dhan broker and remove stored credentials. */
export function disconnectDhan(): Promise<{ success: boolean }> {
  return del<{ success: boolean }>(`${BROKERS_BASE}/dhan/connect`);
}

// --- Market Data Sources ---

const MARKET_DATA_BASE = '/api/v1/settings/market-data';

/** Get market data source configuration. */
export function getMarketDataSources(): Promise<DataSourcesResponse> {
  return get<DataSourcesResponse>(`${MARKET_DATA_BASE}/sources`);
}

/** Update market data source configuration. */
export function updateMarketDataSources(request: DataSourcesRequest): Promise<DataSourcesResponse> {
  return put<DataSourcesResponse>(`${MARKET_DATA_BASE}/sources`, request);
}

// --- Live Market Data ---

const LIVE_MARKET_BASE = '/api/v1/market-data';

/** Get live market index data (NIFTY 50, SENSEX, BANK NIFTY, NIFTY IT). */
export function getLiveMarketData(): Promise<LiveMarketResponse> {
  return get<LiveMarketResponse>(`${LIVE_MARKET_BASE}/live`);
}
