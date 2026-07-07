import { useState } from 'react';
import { Card } from '../ui/Card';
import { useAI } from '../../hooks/useAI';
import type { AITradeReview as AITradeReviewType } from '../../hooks/useAI';

interface AITradeReviewProps {
  /** Trade context for requesting a review */
  tradeContext?: Record<string, unknown>;
  /** Pre-loaded review data (e.g., from journal) */
  review?: AITradeReviewType | null;
  /** Whether to show weekly/monthly summary section */
  showSummary?: boolean;
  className?: string;
}

const gradeConfig: Record<string, { bg: string; text: string; ring: string; description: string }> = {
  A: {
    bg: 'bg-green-500/15',
    text: 'text-green-400',
    ring: 'ring-green-500/30',
    description: 'Excellent execution',
  },
  B: {
    bg: 'bg-blue-500/15',
    text: 'text-blue-400',
    ring: 'ring-blue-500/30',
    description: 'Good trade',
  },
  C: {
    bg: 'bg-amber-500/15',
    text: 'text-amber-400',
    ring: 'ring-amber-500/30',
    description: 'Average — room for improvement',
  },
  D: {
    bg: 'bg-orange-500/15',
    text: 'text-orange-400',
    ring: 'ring-orange-500/30',
    description: 'Below average',
  },
  F: {
    bg: 'bg-red-500/15',
    text: 'text-red-400',
    ring: 'ring-red-500/30',
    description: 'Poor execution — review needed',
  },
};

interface FeedbackSectionProps {
  label: string;
  feedback: string;
  icon: string;
}

function FeedbackSection({ label, feedback, icon }: FeedbackSectionProps) {
  return (
    <div className="flex items-start gap-2.5 px-3 py-2 rounded-lg bg-dashboard-card/50 border border-dashboard-border">
      <span className="text-sm shrink-0 mt-0.5" aria-hidden="true">{icon}</span>
      <div className="flex-1 min-w-0">
        <p className="text-[10px] font-medium text-dashboard-muted uppercase tracking-wide mb-0.5">
          {label}
        </p>
        <p className="text-sm text-dashboard-text leading-relaxed">{feedback}</p>
      </div>
    </div>
  );
}

/**
 * AI Trade Review component showing grade, feedback sections, and patterns.
 *
 * Features:
 * - Overall grade display (A/B/C/D/F) with color coding
 * - Entry, exit, sizing, and risk management feedback sections
 * - Optimal comparison (what could have been achieved)
 * - Patterns identified list
 * - On-demand review request for trades
 * - Weekly/monthly summary integration
 * - Graceful "AI analysis unavailable" state
 *
 * Validates: Requirements 23.1-23.5
 */
export function AITradeReview({
  tradeContext,
  review: preloadedReview,
  showSummary = false,
  className = '',
}: AITradeReviewProps) {
  const { tradeReview: hookReview, reviewTrade, isAnalyzing, error } = useAI();
  const [hasRequestedReview, setHasRequestedReview] = useState(false);

  // Use preloaded review or hook-managed review
  const review = preloadedReview ?? hookReview;

  const handleRequestReview = async () => {
    if (!tradeContext) return;
    setHasRequestedReview(true);
    await reviewTrade(tradeContext);
  };

  // No review yet — show request button or loading
  if (!review) {
    // If currently analyzing
    if (isAnalyzing && hasRequestedReview) {
      return (
        <Card className={className}>
          <div className="space-y-3">
            <h4 className="text-xs font-medium text-dashboard-muted uppercase tracking-wide">
              AI Trade Review
            </h4>
            <div className="flex items-center gap-2 py-4">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-dashboard-muted border-t-transparent" />
              <span className="text-sm text-dashboard-muted">Analyzing trade…</span>
            </div>
          </div>
        </Card>
      );
    }

    // Error state
    if (error && hasRequestedReview) {
      return (
        <Card className={className}>
          <div className="space-y-3">
            <h4 className="text-xs font-medium text-dashboard-muted uppercase tracking-wide">
              AI Trade Review
            </h4>
            <div className="flex items-center gap-2 px-3 py-3 rounded-lg bg-dashboard-card/50 border border-dashboard-border">
              <span className="text-dashboard-muted" aria-hidden="true">⚡</span>
              <p className="text-sm text-dashboard-muted">AI trade review unavailable</p>
            </div>
          </div>
        </Card>
      );
    }

    // Show request button if we have trade context but no review
    if (tradeContext && !hasRequestedReview) {
      return (
        <Card className={className}>
          <div className="space-y-3">
            <h4 className="text-xs font-medium text-dashboard-muted uppercase tracking-wide">
              AI Trade Review
            </h4>
            <button
              type="button"
              onClick={handleRequestReview}
              disabled={isAnalyzing}
              className="w-full px-4 py-2.5 text-sm font-medium text-blue-400 border border-blue-500/30 rounded-lg
                hover:bg-blue-500/10 transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
              aria-label="Request AI review for this trade"
            >
              Request AI Review
            </button>
          </div>
        </Card>
      );
    }

    // Nothing to show
    return null;
  }

  // We have a review — display it
  const gradeStyle = gradeConfig[review.grade] ?? gradeConfig.C;

  return (
    <Card className={className} aria-live="polite" aria-atomic="true">
      <div className="space-y-3">
        {/* Header */}
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-medium text-dashboard-muted uppercase tracking-wide">
            AI Trade Review
          </h4>
        </div>

        {/* Grade display */}
        <div className="flex items-center gap-3">
          <span
            className={`
              inline-flex items-center justify-center w-12 h-12 rounded-xl text-xl font-bold
              ring-1 ring-inset
              ${gradeStyle.bg} ${gradeStyle.text} ${gradeStyle.ring}
            `}
            role="status"
            aria-label={`Trade grade: ${review.grade}`}
          >
            {review.grade}
          </span>
          <div>
            <p className={`text-sm font-semibold ${gradeStyle.text}`}>
              Grade {review.grade}
            </p>
            <p className="text-xs text-dashboard-muted">{gradeStyle.description}</p>
          </div>
        </div>

        {/* Feedback sections */}
        <div className="space-y-2">
          <FeedbackSection
            label="Entry Timing"
            feedback={review.entryFeedback}
            icon="📥"
          />
          <FeedbackSection
            label="Exit Timing"
            feedback={review.exitFeedback}
            icon="📤"
          />
          <FeedbackSection
            label="Position Sizing"
            feedback={review.sizingFeedback}
            icon="📊"
          />
          <FeedbackSection
            label="Risk Management"
            feedback={review.riskFeedback}
            icon="🛡"
          />
        </div>

        {/* Optimal comparison */}
        {review.optimalComparison && (
          <div className="px-3 py-2.5 rounded-lg bg-blue-500/5 border border-blue-500/15">
            <p className="text-[10px] font-medium text-blue-400 uppercase tracking-wide mb-1">
              Optimal vs Actual
            </p>
            <p className="text-sm text-dashboard-text leading-relaxed">
              {review.optimalComparison}
            </p>
          </div>
        )}

        {/* Patterns identified */}
        {review.patternsIdentified.length > 0 && (
          <div className="space-y-1.5">
            <p className="text-xs font-medium text-dashboard-muted uppercase tracking-wide">
              Patterns Identified
            </p>
            <ul className="space-y-1" role="list" aria-label="Trading patterns identified">
              {review.patternsIdentified.map((pattern, index) => (
                <li
                  key={index}
                  className="flex items-start gap-2 px-3 py-1.5 rounded-md bg-amber-500/5 border border-amber-500/15"
                >
                  <span className="text-amber-400 text-xs mt-0.5 shrink-0" aria-hidden="true">💡</span>
                  <span className="text-xs text-dashboard-text">{pattern}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Weekly/Monthly Summary section */}
        {showSummary && (
          <div className="pt-2 border-t border-dashboard-border space-y-2">
            <h5 className="text-xs font-medium text-dashboard-muted uppercase tracking-wide">
              Performance Summary
            </h5>
            <div className="px-3 py-2.5 rounded-lg bg-dashboard-card/50 border border-dashboard-border">
              <p className="text-xs text-dashboard-muted mb-1">
                Patterns from recent trades:
              </p>
              {review.patternsIdentified.length > 0 ? (
                <ul className="space-y-0.5">
                  {review.patternsIdentified.map((pattern, index) => (
                    <li key={index} className="text-sm text-dashboard-text flex items-start gap-1.5">
                      <span className="text-dashboard-muted shrink-0" aria-hidden="true">•</span>
                      <span>{pattern}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-dashboard-muted">
                  Not enough trades to identify patterns yet.
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}
