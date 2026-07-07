import { useEffect, useState } from 'react';
import { Card } from '../ui/Card';
import { useAI } from '../../hooks/useAI';
import type { AIExitRecommendation } from '../../hooks/useAI';

interface AIExitAdvisorProps {
  positionId: number;
  className?: string;
}

type ExitAction = AIExitRecommendation['action'];

const actionConfig: Record<ExitAction, { label: string; bg: string; text: string; ring: string; icon: string }> = {
  hold: {
    label: 'Hold',
    bg: 'bg-green-500/15',
    text: 'text-green-400',
    ring: 'ring-green-500/30',
    icon: '✓',
  },
  tighten_stop: {
    label: 'Tighten Stop',
    bg: 'bg-amber-500/15',
    text: 'text-amber-400',
    ring: 'ring-amber-500/30',
    icon: '⚠',
  },
  book_partial: {
    label: 'Book Partial',
    bg: 'bg-blue-500/15',
    text: 'text-blue-400',
    ring: 'ring-blue-500/30',
    icon: '📊',
  },
  exit_now: {
    label: 'Exit Now',
    bg: 'bg-red-500/15',
    text: 'text-red-400',
    ring: 'ring-red-500/30',
    icon: '🚨',
  },
};

/**
 * AI Exit Advisor panel that displays hold/tighten/book_partial/exit_now
 * recommendations with reasoning and confidence.
 *
 * Features:
 * - Color-coded action badge
 * - Confidence percentage indicator
 * - Reasoning text
 * - Warnings list
 * - Pulsing red glow for high-confidence "exit_now" (confidence > 80%)
 * - Advisory-only disclaimer (never auto-executes)
 * - Graceful "AI analysis unavailable" state
 *
 * Validates: Requirements 21.1-21.4
 */
export function AIExitAdvisor({ positionId, className = '' }: AIExitAdvisorProps) {
  const { exitRecommendation, getExitRecommendation, error } = useAI();
  const [isLoading, setIsLoading] = useState(false);
  const [hasFetched, setHasFetched] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function fetchRecommendation() {
      setIsLoading(true);
      await getExitRecommendation(positionId);
      if (!cancelled) {
        setIsLoading(false);
        setHasFetched(true);
      }
    }

    fetchRecommendation();

    return () => {
      cancelled = true;
    };
  }, [positionId, getExitRecommendation]);

  // Loading state
  if (isLoading && !hasFetched) {
    return (
      <Card className={className}>
        <div className="space-y-3">
          <h4 className="text-xs font-medium text-dashboard-muted uppercase tracking-wide">
            AI Exit Advisor
          </h4>
          <div className="flex items-center gap-2 py-4">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-dashboard-muted border-t-transparent" />
            <span className="text-sm text-dashboard-muted">Analyzing position…</span>
          </div>
        </div>
      </Card>
    );
  }

  // Error / unavailable state
  if ((error && !exitRecommendation) || (!exitRecommendation && hasFetched)) {
    return (
      <Card className={className}>
        <div className="space-y-3">
          <h4 className="text-xs font-medium text-dashboard-muted uppercase tracking-wide">
            AI Exit Advisor
          </h4>
          <div className="flex items-center gap-2 px-3 py-3 rounded-lg bg-dashboard-card/50 border border-dashboard-border">
            <span className="text-dashboard-muted" aria-hidden="true">⚡</span>
            <p className="text-sm text-dashboard-muted">AI analysis unavailable</p>
          </div>
        </div>
      </Card>
    );
  }

  // We have a valid recommendation — non-null asserted by early return above
  const recommendation = exitRecommendation!;
  const config = actionConfig[recommendation.action];
  const isUrgentExit = recommendation.action === 'exit_now' && recommendation.confidence > 80;

  return (
    <Card
      className={`
        ${className}
        ${isUrgentExit ? 'ring-2 ring-red-500/60 animate-pulse-border' : ''}
      `}
      aria-live="polite"
      aria-atomic="true"
    >
      <div className="space-y-3">
        {/* Header */}
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-medium text-dashboard-muted uppercase tracking-wide">
            AI Exit Advisor
          </h4>
          {isUrgentExit && (
            <span className="text-[10px] font-bold text-red-400 uppercase tracking-wider animate-pulse">
              Urgent
            </span>
          )}
        </div>

        {/* Action badge */}
        <div className="flex items-center gap-3">
          <span
            className={`
              inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-semibold
              ring-1 ring-inset
              ${config.bg} ${config.text} ${config.ring}
            `}
            role="status"
            aria-label={`AI recommendation: ${config.label}`}
          >
            <span aria-hidden="true">{config.icon}</span>
            <span>{config.label}</span>
          </span>

          {/* Confidence indicator */}
          <div className="flex items-center gap-2">
            <div className="flex-1 h-1.5 w-16 rounded-full bg-dashboard-border overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  recommendation.confidence >= 80
                    ? 'bg-red-400'
                    : recommendation.confidence >= 60
                      ? 'bg-amber-400'
                      : 'bg-green-400'
                }`}
                style={{ width: `${Math.min(100, Math.max(0, recommendation.confidence))}%` }}
              />
            </div>
            <span className="text-xs font-mono text-dashboard-muted">
              {recommendation.confidence}%
            </span>
          </div>
        </div>

        {/* Reasoning */}
        <div className="px-3 py-2 rounded-lg bg-dashboard-card/50 border border-dashboard-border">
          <p className="text-sm text-dashboard-text leading-relaxed">
            {recommendation.reasoning}
          </p>
        </div>

        {/* Warnings */}
        {recommendation.warnings.length > 0 && (
          <div className="space-y-1.5">
            <p className="text-xs font-medium text-dashboard-muted uppercase tracking-wide">
              Warnings
            </p>
            <ul className="space-y-1" role="list" aria-label="AI warnings">
              {recommendation.warnings.map((warning, index) => (
                <li
                  key={index}
                  className="flex items-start gap-2 px-3 py-1.5 rounded-md bg-amber-500/5 border border-amber-500/15"
                >
                  <span className="text-amber-400 text-xs mt-0.5 shrink-0" aria-hidden="true">⚠</span>
                  <span className="text-xs text-dashboard-text">{warning}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Advisory disclaimer */}
        <div className="flex items-center gap-1.5 pt-1 border-t border-dashboard-border">
          <span className="text-dashboard-muted text-xs" aria-hidden="true">ℹ</span>
          <p className="text-[11px] text-dashboard-muted italic">
            This is advisory only — no exits are executed automatically.
          </p>
        </div>
      </div>
    </Card>
  );
}
