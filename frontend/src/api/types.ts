/**
 * Type-safe request/response interfaces for all API endpoints.
 * These interfaces match the backend Pydantic models defined in the design document.
 */

// ============================================================
// Scanner Types
// ============================================================

export type ScanType = 'trend_pullback' | 'consolidation_breakout';

export interface ScanSignal {
  symbol: string;
  scan_type: ScanType;
  confidence_score: number;
  entry_price: number;
  stop_loss: number;
  target_price: number;
  max_potential_loss: number;
  timestamp: string;
  metadata: Record<string, unknown>;
}

export interface ConsolidationPattern {
  symbol: string;
  range_high: number;
  range_low: number;
  avg_price: number;
  candle_count: number;
  duration_minutes: number;
  is_breakout: boolean;
  breakout_price?: number;
}

export interface TrendPullbackRequest {
  watchlist?: string[];
}

// ============================================================
// Index Analyzer Types
// ============================================================

export type TrendDirection = 'bullish' | 'bearish' | 'neutral';

export interface IndexMetrics {
  symbol: string;
  current_price: number;
  change_1h_pct: number;
  change_daily_pct: number;
  momentum_score: number;
  volume_score: number;
  trend_direction: TrendDirection;
  composite_score: number;
  data_available: boolean;
}

export interface IndexRecommendation {
  best_index: string;
  option_type: 'CE' | 'PE';
  recommended_strike: number;
  strike_step: number;
  reasoning: string;
}

// ============================================================
// Signal Types
// ============================================================

export type SignalStatus = 'pending' | 'approved' | 'rejected' | 'expired';

export interface TradingSignal {
  id: string;
  symbol: string;
  confidence_score: number;
  entry_price: number;
  stop_loss: number;
  target_price: number;
  max_loss: number;
  status: SignalStatus;
  created_at: string;
  expires_at: string;
  countdown_seconds: number;
  ai_quality_rating?: string;
  ai_warnings?: string[];
}

export interface SignalActionResponse {
  success: boolean;
  message: string;
  signal_id: string;
}

// ============================================================
// Settings Types
// ============================================================

export interface StrategySettings {
  watchlist: string[];
  trading_start_time: string;
  trading_end_time: string;
  confidence_threshold: number;
  max_trades_per_day: number;
  max_active_trades: number;
  capital: number;
  lot_sizes: Record<string, number>;
}

export type ThresholdType = 'amount' | 'percentage';

export interface KillSwitchThresholds {
  daily_loss_type: ThresholdType;
  daily_loss_value: number;
  profit_target_type: ThresholdType;
  profit_target_value: number;
  drawdown_type: ThresholdType;
  drawdown_value: number;
  profit_warning_pct: number;
}

export interface SegmentStatus {
  segment: string;
  is_active: boolean;
  deactivated_by_killswitch: boolean;
}

export interface AISettings {
  provider: 'gemini' | 'claude';
  api_key_configured: boolean;
  signal_analysis_enabled: boolean;
  entry_suggestions_enabled: boolean;
  exit_recommendations_enabled: boolean;
  market_narrative_enabled: boolean;
  trade_review_enabled: boolean;
  risk_warnings_enabled: boolean;
}

export interface DataSourceConfig {
  source_id: string;
  display_name: string;
  enabled: boolean;
  priority: number;
}

export interface DataSourcesRequest {
  sources: DataSourceConfig[];
}

export interface DataSourcesResponse {
  sources: DataSourceConfig[];
  warnings: string[];
}

// ============================================================
// Broker Settings Types
// ============================================================

export type KiteConnectionStatus = 'Connected' | 'Disconnected' | 'Token Expired';
export type DhanConnectionStatus = 'Connected' | 'Disconnected' | 'Error';

export interface KiteStatusResponse {
  status: KiteConnectionStatus;
  token_expiry: string | null;
  time_remaining: string | null;
  auto_login_enabled: boolean;
  key_configured: boolean;
  last_auto_login_at: string | null;
  last_auto_login_success: boolean | null;
}

export interface AutoLoginRequest {
  totp_key?: string | null;
  enabled: boolean;
}

export interface AutoLoginResponse {
  success: boolean;
}

export interface DhanStatusResponse {
  status: DhanConnectionStatus;
  account_name: string | null;
  error_message: string | null;
}

export interface DhanConnectRequest {
  client_id: string;
  access_token: string;
}

// ============================================================
// Live Market Data Types
// ============================================================

export interface IndexData {
  symbol: string;
  value: number;
  change_points: number;
  change_percent: number;
  last_updated: string;
}

export interface LiveMarketResponse {
  indices: IndexData[];
  market_open: boolean;
  data_source: string;
  last_successful_fetch: string | null;
}

// ============================================================
// Position Monitor Types
// ============================================================

export type PositionMonitorStatus = 'active' | 'sl_hit' | 'target_hit' | 'trailing_stop_hit';

export interface MonitoredPosition {
  position_id: number;
  symbol: string;
  entry_price: number;
  current_price: number;
  stop_loss: number;
  target: number;
  trailing_stop_enabled: boolean;
  trailing_stop_level?: number;
  unrealized_pnl: number;
  distance_to_sl_pct: number;
  distance_to_target_pct: number;
  status: PositionMonitorStatus;
}

export type ExitConditionName = 'ema_cross' | 'vwap_touch' | 'consecutive_green' | 'time_based';

export interface ExitCondition {
  name: ExitConditionName;
  description: string;
  is_met: boolean;
  details?: string;
}

export interface ManualExitRequest {
  reason?: string;
}

export interface MonitorToggleRequest {
  active: boolean;
}

export interface MonitorToggleResponse {
  active: boolean;
  message: string;
}

// ============================================================
// Paper Trading Types
// ============================================================

export interface PaperAccount {
  user_id: number;
  balance: number;
  total_pnl: number;
  win_rate: number;
  profit_factor: number;
  roi_pct: number;
  total_trades: number;
}

export interface PaperTrade {
  id: number;
  symbol: string;
  strike: number;
  option_type: 'CE' | 'PE';
  entry_price: number;
  quantity: number;
  stop_loss: number;
  target: number;
  current_price?: number;
  unrealized_pnl?: number;
  status: 'open' | 'closed';
  exit_price?: number;
  exit_reason?: string;
  pnl?: number;
}

export interface PaperTradeEntryRequest {
  symbol: string;
  strike: number;
  option_type: 'CE' | 'PE';
  entry_price: number;
  quantity: number;
  stop_loss: number;
  target: number;
}

export interface PaperTradeExitRequest {
  exit_price: number;
}

// ============================================================
// Journal Types
// ============================================================

export interface TradeJournalEntry {
  id: number;
  trade_id: number;
  date: string;
  symbol: string;
  entry_price: number;
  exit_price: number;
  pnl: number;
  setup_type?: string;
  confidence_score?: number;
  trend_direction?: TrendDirection;
  exit_reason?: string;
  ai_grade?: string;
  ai_review?: string;
}

export interface JournalFilters {
  date_from?: string;
  date_to?: string;
  setup_type?: string;
  profit_loss?: 'profit' | 'loss';
  symbol?: string;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
}

export interface JournalStats {
  total_trades: number;
  win_rate: number;
  avg_profit: number;
  avg_loss: number;
  profit_factor: number;
  best_trade: number;
  worst_trade: number;
}

// ============================================================
// Charts Types
// ============================================================

export type ChartInterval = '3min' | '5min' | '15min';

export interface CandleData {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface ChartIndicators {
  ema20: number[];
  vwap: number[];
  macd: { macd: number; signal: number; histogram: number }[];
}

export interface ChartData {
  symbol: string;
  interval: ChartInterval;
  candles: CandleData[];
  indicators: ChartIndicators;
}

export interface ChartWithSignal extends ChartData {
  signal_entry: number;
  signal_sl: number;
  signal_target: number;
}

// ============================================================
// Status Types
// ============================================================

export type MarketState = 'pre_market' | 'open' | 'closed';
export type WorkerStatus = 'running' | 'stopped' | 'unknown';

export interface SystemStatus {
  market_state: MarketState;
  countdown_seconds: number;
  countdown_label: string;
  session_status: 'connected' | 'disconnected' | 'expired';
  workers: {
    scanner: WorkerStatus;
    position_monitor: WorkerStatus;
    killswitch_monitor: WorkerStatus;
  };
}

export interface CapitalStatus {
  available_balance: number;
  configured_capital: number;
  used_margin: number;
  available_margin: number;
  margin_breakdown: {
    equity: number;
    commodity: number;
    fo: number;
  };
}

// ============================================================
// AI Types
// ============================================================

// ============================================================
// Account Dashboard Types
// ============================================================

export interface AccountProfile {
  user_name: string;
  user_id: string;
  email: string;
  broker: string;
}

export interface AccountMargins {
  available_capital: number;
  net: number;
  used: number;
}

export interface AccountPosition {
  symbol: string;
  qty: number;
  avg_price: number;
  ltp: number;
  pnl: number;
  product: string;
}

export interface AccountTrade {
  symbol: string;
  transaction_type: string;
  qty: number;
  price: number;
  time: string;
}

export interface AccountTradesToday {
  count: number;  // Executed orders
  fills: number;  // Individual trade fills
  trades: AccountTrade[];
}

export interface AccountPnLSummary {
  total_pnl: number;
  realized_pnl: number;
  unrealized_pnl: number;
  brokerage: number;
  stt: number;
  exchange_charges: number;
  gst: number;
  total_charges: number;
  net_pnl: number;
}

export interface AccountOrder {
  symbol: string;
  status: string;
  transaction_type: string;
  qty: number;
  price: number;
}

export interface AccountOrdersToday {
  count: number;
  orders: AccountOrder[];
}

export interface AccountDashboardResponse {
  profile: AccountProfile;
  margins: AccountMargins;
  positions: AccountPosition[];
  trades_today: AccountTradesToday;
  pnl_summary: AccountPnLSummary;
  orders_today: AccountOrdersToday;
}

// ============================================================
// AI Types
// ============================================================

export type AIQualityRating = 'Strong Setup' | 'Acceptable Setup' | 'Weak Setup' | 'Avoid — High Risk';

export interface AISignalAnalysis {
  quality_rating: AIQualityRating;
  warnings: string[];
  explanation: string;
  suggested_entry?: number;
  suggested_sl?: string;
  risk_reward_default?: number;
  risk_reward_ai?: number;
  timing_recommendation?: string;
}

export interface AISignalAnalysisRequest {
  signal_id: string;
  symbol: string;
  timeframe: string;
  indicators: Record<string, unknown>;
  price_action: Record<string, unknown>;
}

export interface AIEntrySuggestionRequest {
  signal_id: string;
  symbol: string;
  current_price: number;
  scanner_entry: number;
  stop_loss: number;
  target: number;
}

export interface AIEntrySuggestion {
  suggested_entry: number;
  entry_type: 'market' | 'limit' | 'wait';
  suggested_sl: number;
  sl_reasoning: string;
  risk_reward_default: number;
  risk_reward_ai: number;
  timing: string;
  reasoning: string;
}

export interface AIConsolidationAnalysisRequest {
  symbol: string;
  range_high: number;
  range_low: number;
  avg_price: number;
  candle_count: number;
  duration_minutes: number;
}

export interface AIConsolidationAnalysis {
  breakout_probability: number;
  predicted_direction: 'up' | 'down';
  expected_move_pct: number;
  false_breakout_risk: boolean;
  false_breakout_reasons: string[];
  assessment?: string;
}

export interface AIExitRecommendation {
  action: 'hold' | 'tighten_stop' | 'book_partial' | 'exit_now';
  reasoning: string;
  confidence: number;
  warnings: string[];
}

export interface AIMarketNarrative {
  session_type: string;
  key_points: string[];
  bias: 'bullish' | 'bearish' | 'neutral';
  expected_range: { low: number; high: number };
  key_levels: { support: number[]; resistance: number[] };
  detailed_analysis?: string;
}

export interface AITradeReviewRequest {
  trade_id: number;
  symbol: string;
  entry_price: number;
  exit_price: number;
  pnl: number;
  entry_time: string;
  exit_time: string;
  setup_type?: string;
}

export interface AITradeReview {
  grade: string;
  entry_feedback: string;
  exit_feedback: string;
  sizing_feedback: string;
  risk_feedback: string;
  optimal_comparison: string;
  patterns_identified: string[];
}

export type RiskWarningSeverity = 'info' | 'warning' | 'critical';
export type RiskWarningCategory = 'market_condition' | 'behavioral' | 'rule_violation';

export interface AIRiskWarning {
  severity: RiskWarningSeverity;
  message: string;
  category: RiskWarningCategory;
  requires_acknowledgment: boolean;
}

export interface AIRiskScore {
  score: number;
  factors: string[];
  recommendation: string;
}


// ============================================================
// Instruments / Option Chain Types
// ============================================================

export interface OptionChainEntry {
  strike: number;
  ce_ltp: number;
  ce_change: number;
  ce_oi: number;
  ce_volume: number;
  ce_symbol: string;
  ce_bid: number;
  ce_ask: number;
  pe_ltp: number;
  pe_change: number;
  pe_oi: number;
  pe_volume: number;
  pe_symbol: string;
  pe_bid: number;
  pe_ask: number;
}

export interface OptionChainResponse {
  index: string;
  spot_price: number;
  expiry: string;
  lot_size: number;
  strikes: OptionChainEntry[];
}

export interface InstrumentSearchResult {
  tradingsymbol: string;
  name: string;
  exchange: string;
  instrument_type: string;
  lot_size: number;
  last_price: number;
  change_percent: number;
}

export interface QuoteItem {
  symbol: string;
  ltp: number;
  change: number;
  change_percent: number;
  volume: number;
  oi: number;
}
