import { useState, useEffect, useCallback } from 'react';
import { useWebSocket } from '../contexts/WebSocketContext';
import type {
  AIAnalysisResultEvent,
  AIRiskWarningEvent,
  AIMarketUpdateEvent,
} from '../contexts/WebSocketContext';
import { get, post } from '../api/client';

// --- Types ---

export type AIQualityRating = 'Strong Setup' | 'Acceptable Setup' | 'Weak Setup' | 'Avoid — High Risk';

export interface AISignalAnalysis {
  qualityRating: AIQualityRating;
  warnings: string[];
  explanation: string;
  suggestedEntry?: number;
  suggestedSl?: string;
  riskRewardDefault?: number;
  riskRewardAi?: number;
  timingRecommendation?: string;
}

export interface AIConsolidationAnalysis {
  breakoutProbability: number;
  predictedDirection: string;
  expectedMovePct: number;
  falseBreakoutRisk: boolean;
  falseBreakoutReasons: string[];
  assessment?: string;
}

export interface AIExitRecommendation {
  action: 'hold' | 'tighten_stop' | 'book_partial' | 'exit_now';
  reasoning: string;
  confidence: number;
  warnings: string[];
}

export interface AIMarketNarrative {
  sessionType: string;
  keyPoints: string[];
  bias: string;
  expectedRange: { low: number; high: number };
  keyLevels: { support: number[]; resistance: number[] };
  detailedAnalysis?: string;
}

export interface AITradeReview {
  grade: string;
  entryFeedback: string;
  exitFeedback: string;
  sizingFeedback: string;
  riskFeedback: string;
  optimalComparison: string;
  patternsIdentified: string[];
}

export interface AIRiskWarning {
  severity: 'info' | 'warning' | 'critical';
  message: string;
  category: string;
  requiresAcknowledgment: boolean;
}

interface UseAIReturn {
  // State
  signalAnalysis: AISignalAnalysis | null;
  consolidationAnalysis: AIConsolidationAnalysis | null;
  exitRecommendation: AIExitRecommendation | null;
  marketNarrative: AIMarketNarrative | null;
  tradeReview: AITradeReview | null;
  riskWarnings: AIRiskWarning[];
  riskScore: number | null;
  isAnalyzing: boolean;
  error: string | null;
  // Actions
  analyzeSignal: (signalContext: Record<string, unknown>) => Promise<AISignalAnalysis | null>;
  requestEntrySuggestion: (signalContext: Record<string, unknown>) => Promise<void>;
  analyzeConsolidation: (patternContext: Record<string, unknown>) => Promise<AIConsolidationAnalysis | null>;
  getExitRecommendation: (positionId: number) => Promise<AIExitRecommendation | null>;
  fetchMarketNarrative: () => Promise<void>;
  reviewTrade: (tradeContext: Record<string, unknown>) => Promise<AITradeReview | null>;
  fetchRiskWarnings: () => Promise<void>;
  fetchRiskScore: () => Promise<void>;
  clearAnalysis: () => void;
}

/**
 * Hook for AI trading intelligence.
 * - Subscribes to ai_analysis_result, ai_risk_warning, ai_market_update WebSocket events
 * - Provides request methods for various AI analyses
 * - Manages AI analysis state
 */
export function useAI(): UseAIReturn {
  const { on, off } = useWebSocket();

  const [signalAnalysis, setSignalAnalysis] = useState<AISignalAnalysis | null>(null);
  const [consolidationAnalysis, setConsolidationAnalysis] = useState<AIConsolidationAnalysis | null>(null);
  const [exitRecommendation, setExitRecommendation] = useState<AIExitRecommendation | null>(null);
  const [marketNarrative, setMarketNarrative] = useState<AIMarketNarrative | null>(null);
  const [tradeReview, setTradeReview] = useState<AITradeReview | null>(null);
  const [riskWarnings, setRiskWarnings] = useState<AIRiskWarning[]>([]);
  const [riskScore, setRiskScore] = useState<number | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Subscribe to WebSocket events for async AI results
  useEffect(() => {
    const handleAnalysisResult = (data: AIAnalysisResultEvent) => {
      setIsAnalyzing(false);
      const { analysisType, result } = data;

      switch (analysisType) {
        case 'signal_analysis':
          setSignalAnalysis(result as unknown as AISignalAnalysis);
          break;
        case 'consolidation_analysis':
          setConsolidationAnalysis(result as unknown as AIConsolidationAnalysis);
          break;
        case 'exit_recommendation':
          setExitRecommendation(result as unknown as AIExitRecommendation);
          break;
        case 'trade_review':
          setTradeReview(result as unknown as AITradeReview);
          break;
        default:
          break;
      }
    };

    const handleRiskWarning = (data: AIRiskWarningEvent) => {
      setRiskWarnings((prev) => [data, ...prev]);
    };

    const handleMarketUpdate = (data: AIMarketUpdateEvent) => {
      setMarketNarrative(data);
    };

    on<AIAnalysisResultEvent>('ai_analysis_result', handleAnalysisResult);
    on<AIRiskWarningEvent>('ai_risk_warning', handleRiskWarning);
    on<AIMarketUpdateEvent>('ai_market_update', handleMarketUpdate);

    return () => {
      off<AIAnalysisResultEvent>('ai_analysis_result', handleAnalysisResult);
      off<AIRiskWarningEvent>('ai_risk_warning', handleRiskWarning);
      off<AIMarketUpdateEvent>('ai_market_update', handleMarketUpdate);
    };
  }, [on, off]);

  const analyzeSignal = useCallback(async (signalContext: Record<string, unknown>) => {
    try {
      setIsAnalyzing(true);
      setError(null);
      const result = await post<AISignalAnalysis>('/api/v1/ai/analyze-signal', signalContext);
      setSignalAnalysis(result);
      return result;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'AI signal analysis unavailable';
      setError(message);
      return null;
    } finally {
      setIsAnalyzing(false);
    }
  }, []);

  const requestEntrySuggestion = useCallback(async (signalContext: Record<string, unknown>) => {
    try {
      setIsAnalyzing(true);
      setError(null);
      const result = await post<AISignalAnalysis>('/api/v1/ai/entry-suggestion', signalContext);
      setSignalAnalysis(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'AI entry suggestion unavailable';
      setError(message);
    } finally {
      setIsAnalyzing(false);
    }
  }, []);

  const analyzeConsolidation = useCallback(async (patternContext: Record<string, unknown>) => {
    try {
      setIsAnalyzing(true);
      setError(null);
      const result = await post<AIConsolidationAnalysis>('/api/v1/ai/consolidation-analysis', patternContext);
      setConsolidationAnalysis(result);
      return result;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'AI consolidation analysis unavailable';
      setError(message);
      return null;
    } finally {
      setIsAnalyzing(false);
    }
  }, []);

  const getExitRecommendation = useCallback(async (positionId: number) => {
    try {
      setError(null);
      const result = await get<AIExitRecommendation>(`/api/v1/ai/exit-recommendation/${positionId}`);
      setExitRecommendation(result);
      return result;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'AI exit recommendation unavailable';
      setError(message);
      return null;
    }
  }, []);

  const fetchMarketNarrative = useCallback(async () => {
    try {
      setError(null);
      const result = await get<AIMarketNarrative>('/api/v1/ai/market-narrative');
      setMarketNarrative(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'AI market narrative unavailable';
      setError(message);
    }
  }, []);

  const reviewTrade = useCallback(async (tradeContext: Record<string, unknown>) => {
    try {
      setIsAnalyzing(true);
      setError(null);
      const result = await post<AITradeReview>('/api/v1/ai/review-trade', tradeContext);
      setTradeReview(result);
      return result;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'AI trade review unavailable';
      setError(message);
      return null;
    } finally {
      setIsAnalyzing(false);
    }
  }, []);

  const fetchRiskWarnings = useCallback(async () => {
    try {
      setError(null);
      const result = await get<AIRiskWarning[]>('/api/v1/ai/risk-warnings');
      setRiskWarnings(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'AI risk warnings unavailable';
      setError(message);
    }
  }, []);

  const fetchRiskScore = useCallback(async () => {
    try {
      setError(null);
      const result = await get<{ score: number }>('/api/v1/ai/risk-score');
      setRiskScore(result.score);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'AI risk score unavailable';
      setError(message);
    }
  }, []);

  const clearAnalysis = useCallback(() => {
    setSignalAnalysis(null);
    setConsolidationAnalysis(null);
    setExitRecommendation(null);
    setTradeReview(null);
    setError(null);
  }, []);

  return {
    signalAnalysis,
    consolidationAnalysis,
    exitRecommendation,
    marketNarrative,
    tradeReview,
    riskWarnings,
    riskScore,
    isAnalyzing,
    error,
    analyzeSignal,
    requestEntrySuggestion,
    analyzeConsolidation,
    getExitRecommendation,
    fetchMarketNarrative,
    reviewTrade,
    fetchRiskWarnings,
    fetchRiskScore,
    clearAnalysis,
  };
}
