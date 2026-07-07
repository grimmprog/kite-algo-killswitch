/**
 * Advanced Orders API client — GTT (Kite), Dhan orders, margin estimation.
 */
import { get, post, del } from './client';

const ORDERS_BASE = '/api/v1/orders';

// --- Types ---

export interface GTTCondition {
  trigger_price: number;
  order_price: number;
  quantity: number;
}

export interface GTTOrderRequest {
  symbol: string;
  exchange: string;
  side: 'BUY' | 'SELL';
  gtt_type: 'single' | 'two-leg';
  last_price: number;
  condition: GTTCondition;
  second_condition?: GTTCondition;
}

export interface GTTOrderResponse {
  success: boolean;
  gtt_id?: number;
  message: string;
}

export interface GTTListItem {
  gtt_id: number;
  symbol: string;
  exchange: string;
  gtt_type: string;
  status: string;
  condition: Record<string, number>;
  second_condition?: Record<string, number>;
  created_at?: string;
}

export interface DhanOrderRequest {
  symbol: string;
  exchange: string;
  security_id: string;
  side: 'BUY' | 'SELL';
  quantity: number;
  order_type: 'MARKET' | 'LIMIT' | 'SL' | 'SL-M';
  price?: number;
  trigger_price?: number;
  product: 'INTRADAY' | 'CNC' | 'MARGIN';
  trailing_sl?: number;
  stop_loss_price?: number;
  target_price?: number;
  target_2_price?: number;
}

export interface DhanOrderResponse {
  success: boolean;
  order_id?: string;
  sl_order_id?: string;
  target_order_id?: string;
  message: string;
}

export interface MarginEstimateRequest {
  broker: 'kite' | 'dhan';
  symbol: string;
  exchange: string;
  quantity: number;
  side: 'BUY' | 'SELL';
  order_type?: string;
  price?: number;
  security_id?: string;
  product?: string;
}

export interface MarginEstimateResponse {
  required_margin: number;
  available_margin: number;
  sufficient_funds: boolean;
  shortfall: number;
  broker: string;
  breakdown?: Record<string, unknown>;
}

// --- API Functions ---

/** Place a Zerodha GTT order. */
export function placeGTTOrder(data: GTTOrderRequest): Promise<GTTOrderResponse> {
  return post<GTTOrderResponse>(`${ORDERS_BASE}/gtt`, data);
}

/** List active GTT orders. */
export function listGTTOrders(): Promise<GTTListItem[]> {
  return get<GTTListItem[]>(`${ORDERS_BASE}/gtt`);
}

/** Cancel a GTT order. */
export function cancelGTTOrder(gttId: number): Promise<{ success: boolean; message: string }> {
  return del<{ success: boolean; message: string }>(`${ORDERS_BASE}/gtt/${gttId}`);
}

/** Place a Dhan order with trailing SL and targets. */
export function placeDhanOrder(data: DhanOrderRequest): Promise<DhanOrderResponse> {
  return post<DhanOrderResponse>(`${ORDERS_BASE}/dhan`, data);
}

/** Estimate margin required for an order. */
export function estimateMargin(data: MarginEstimateRequest): Promise<MarginEstimateResponse> {
  return post<MarginEstimateResponse>(`${ORDERS_BASE}/margin-estimate`, data);
}
