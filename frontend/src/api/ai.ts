/**
 * AI Trading Intelligence API client functions.
 * Handles signal analysis, entry suggestions, consolidation analysis,
 * exit recommendations, market narrative, trade review, and risk warnings.
 */
import { get, post } from './client';
import type {
  AISignalAnalysis,
  AISignalAnalysisRequest,
  AIEntrySuggestion,
  AIEntrySuggestionRequest,
  AIConsolidationAnalysis,
  AIConsolidationAnalysisRequest,
  AIExitRecommendation,
  AIMarketNarrative,
  AITradeReview,
  AITradeReviewRequest,
  AIRiskWarning,
  AIRiskScore,
} from './types';

const BASE = '/api/v1/ai';

/** Request AI signal quality analysis. */
export function analyzeSignal(request: AISignalAnalysisRequest): Promise<AISignalAnalysis> {
  return post<AISignalAnalysis>(`${BASE}/analyze-signal`, request);
}

/** Request AI entry point suggestion. */
export function getEntrySuggestion(request: AIEntrySuggestionRequest): Promise<AIEntrySuggestion> {
  return post<AIEntrySuggestion>(`${BASE}/entry-suggestion`, request);
}

/** Request AI consolidation breakout analysis. */
export function analyzeConsolidation(request: AIConsolidationAnalysisRequest): Promise<AIConsolidationAnalysis> {
  return post<AIConsolidationAnalysis>(`${BASE}/consolidation-analysis`, request);
}

/** Get AI exit recommendation for an open position. */
export function getExitRecommendation(positionId: number): Promise<AIExitRecommendation> {
  return get<AIExitRecommendation>(`${BASE}/exit-recommendation/${positionId}`);
}

/** Get current AI market narrative. */
export function getMarketNarrative(): Promise<AIMarketNarrative> {
  return get<AIMarketNarrative>(`${BASE}/market-narrative`);
}

/** Request AI review of a completed trade. */
export function reviewTrade(request: AITradeReviewRequest): Promise<AITradeReview> {
  return post<AITradeReview>(`${BASE}/review-trade`, request);
}

/** Get active AI risk warnings. */
export function getRiskWarnings(): Promise<AIRiskWarning[]> {
  return get<AIRiskWarning[]>(`${BASE}/risk-warnings`);
}

/** Get daily risk assessment score. */
export function getRiskScore(): Promise<AIRiskScore> {
  return get<AIRiskScore>(`${BASE}/risk-score`);
}
