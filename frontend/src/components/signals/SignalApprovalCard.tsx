import { useState, useCallback } from 'react';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { SignalCountdown } from './SignalCountdown';
import type { TradingSignal, SignalPriceInfo } from '../../hooks/useSignals';

interface SignalApprovalCardProps {
  signal: TradingSignal;
  priceInfo?: SignalPriceInfo;
  onApprove: (signalId: string) => Promise<void>;
  onReject: (signalId: string) => Promise<void>;
}

/**
 * Prominent signal approval card with countdown timer.
 * Displays signal details, real-time price, AI quality rating,
 * and approve/reject action buttons.
 *
 * Validates: Requirements 4.1-4.7, 18.5
 */
export function SignalApprovalCard({
  signal,
  priceInfo,
  onApprove,
  onReject,
}: SignalApprovalCardProps) {
  const [isApproving, setIsApproving] = useState(false);
  const [isRejecting, setIsRejecting] = useState(false);
  const [riskAcknowledged, setRiskAcknowledged] = useState(false);

  const isHighRisk = signal.aiQualityRating === 'Avoid — High Risk';
  const canApprove = !isHighRisk || riskAcknowledged;

  const handleApprove = useCallback(async () => {
    setIsApproving(true);
    try {
      await onApprove(signal.id);
    } finally {
      setIsApproving(false);
    }
  }, [onApprove, signal.id]);

  const handleReject = useCallback(async () => {
    setIsRejecting(true);
    try {
      await onReject(signal.id);
    } finally {
      setIsRejecting(false);
    }
  }, [onReject, signal.id]);

  const formatPrice = (price: number) =>
    `₹${price.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  const riskReward = Math.abs(signal.targetPrice - signal.entryPrice) /
    Math.abs(signal.entryPrice - signal.stopLoss);

  return (
    <Card
      className={`relative overflow-hidden border-2 ${
        isHighRisk
          ? 'border-loss/60 shadow-lg shadow-loss/10'
          : 'border-blue-500/40 shadow-lg shadow-blue-500/10'
      }`}
      padding="lg"
      role="article"
      aria-label={`Trading signal for ${signal.symbol}`}
    >
      {/* High Risk Warning Banner */}
      {isHighRisk && (
        <div
          className="absolute top-0 left-0 right-0 bg-loss/90 text-white px-4 py-2 text-center text-sm font-semibold"
          role="alert"
          aria-live="assertive"
        >
          ⚠️ Avoid — High Risk: AI recommends skipping this trade
        </div>
      )}

      <div className={`${isHighRisk ? 'mt-8' : ''}`}>
        {/* Header: Symbol + Countdown */}
        <div className="flex items-start justify-between mb-4">
          <div>
            <h3 className="text-xl font-bold text-dashboard-text">
              {signal.symbol}
            </h3>
            <div className="flex items-center gap-2 mt-1">
              <ConfidenceBadge score={signal.confidenceScore} />
              {signal.aiQualityRating && (
                <AIRatingBadge rating={signal.aiQualityRating} />
              )}
            </div>
          </div>
          <SignalCountdown
            remainingSeconds={signal.remainingSeconds}
            totalSeconds={signal.countdownSeconds}
            size="lg"
          />
        </div>

        {/* Price Details Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-4">
          <PriceDetail label="Entry" value={formatPrice(signal.entryPrice)} />
          <PriceDetail
            label="Stop Loss"
            value={formatPrice(signal.stopLoss)}
            variant="loss"
          />
          <PriceDetail
            label="Target"
            value={formatPrice(signal.targetPrice)}
            variant="profit"
          />
          <PriceDetail
            label="Max Loss"
            value={formatPrice(signal.maxLoss)}
            variant="loss"
          />
          <PriceDetail
            label="Risk:Reward"
            value={`1:${riskReward.toFixed(1)}`}
          />
          {/* Real-time price update */}
          {priceInfo && (
            <PriceDetail
              label="Current Price"
              value={formatPrice(priceInfo.currentPrice)}
              subValue={`${priceInfo.changePct >= 0 ? '+' : ''}${priceInfo.changePct.toFixed(2)}%`}
              variant={priceInfo.changePct >= 0 ? 'profit' : 'loss'}
            />
          )}
        </div>

        {/* AI Warnings */}
        {signal.aiWarnings && signal.aiWarnings.length > 0 && (
          <div className="mb-4 bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3">
            <p className="text-xs font-semibold text-yellow-400 uppercase tracking-wide mb-1">
              AI Warnings
            </p>
            <ul className="space-y-1" aria-label="AI trading warnings">
              {signal.aiWarnings.map((warning, idx) => (
                <li
                  key={idx}
                  className="text-sm text-yellow-300/90 flex items-start gap-1.5"
                >
                  <span className="shrink-0 mt-0.5" aria-hidden="true">•</span>
                  {warning}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* High Risk Acknowledgment */}
        {isHighRisk && !riskAcknowledged && (
          <div className="mb-4 bg-loss/10 border border-loss/30 rounded-lg p-3">
            <label className="flex items-start gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={riskAcknowledged}
                onChange={(e) => setRiskAcknowledged(e.target.checked)}
                className="mt-0.5 rounded border-loss/50 text-loss focus:ring-loss"
                aria-label="Acknowledge high risk signal"
              />
              <span className="text-sm text-loss/90">
                I understand this signal is rated &quot;Avoid — High Risk&quot; by AI
                and I accept the additional risk of taking this trade.
              </span>
            </label>
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex items-center gap-3">
          <Button
            variant="success"
            size="lg"
            onClick={handleApprove}
            isLoading={isApproving}
            disabled={!canApprove || isRejecting || signal.remainingSeconds === 0}
            className="flex-1"
            aria-label={`Approve trade for ${signal.symbol}`}
          >
            ✓ Approve
          </Button>
          <Button
            variant="danger"
            size="lg"
            onClick={handleReject}
            isLoading={isRejecting}
            disabled={isApproving || signal.remainingSeconds === 0}
            className="flex-1"
            aria-label={`Reject trade for ${signal.symbol}`}
          >
            ✗ Reject
          </Button>
        </div>

        {/* Expired overlay */}
        {signal.remainingSeconds === 0 && (
          <div
            className="absolute inset-0 bg-dashboard-bg/80 flex items-center justify-center rounded-xl"
            role="status"
            aria-label="Signal expired"
          >
            <p className="text-lg font-semibold text-dashboard-muted">
              Signal Expired
            </p>
          </div>
        )}
      </div>
    </Card>
  );
}

// --- Sub-components ---

interface PriceDetailProps {
  label: string;
  value: string;
  subValue?: string;
  variant?: 'default' | 'profit' | 'loss';
}

function PriceDetail({ label, value, subValue, variant = 'default' }: PriceDetailProps) {
  const valueColor = {
    default: 'text-dashboard-text',
    profit: 'text-profit',
    loss: 'text-loss',
  }[variant];

  return (
    <div className="bg-dashboard-bg/50 rounded-lg p-2.5">
      <p className="text-xs text-dashboard-muted">{label}</p>
      <p className={`text-sm font-mono font-semibold ${valueColor}`}>{value}</p>
      {subValue && (
        <p className={`text-xs font-mono ${valueColor}`}>{subValue}</p>
      )}
    </div>
  );
}

interface ConfidenceBadgeProps {
  score: number;
}

function ConfidenceBadge({ score }: ConfidenceBadgeProps) {
  const color =
    score >= 80 ? 'bg-profit/20 text-profit' :
    score >= 65 ? 'bg-yellow-500/20 text-yellow-400' :
    'bg-orange-500/20 text-orange-400';

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${color}`}
      aria-label={`Confidence score: ${score} percent`}
    >
      {score}% confidence
    </span>
  );
}

interface AIRatingBadgeProps {
  rating: string;
}

function AIRatingBadge({ rating }: AIRatingBadgeProps) {
  const colorMap: Record<string, string> = {
    'Strong Setup': 'bg-profit/20 text-profit',
    'Acceptable Setup': 'bg-blue-500/20 text-blue-400',
    'Weak Setup': 'bg-yellow-500/20 text-yellow-400',
    'Avoid — High Risk': 'bg-loss/20 text-loss',
  };

  const color = colorMap[rating] ?? 'bg-dashboard-border text-dashboard-muted';

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${color}`}
      aria-label={`AI quality rating: ${rating}`}
    >
      {rating}
    </span>
  );
}
