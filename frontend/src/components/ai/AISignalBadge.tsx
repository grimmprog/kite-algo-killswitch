import type { AIQualityRating } from '../../hooks/useAI';

interface AISignalBadgeProps {
  rating: AIQualityRating;
  warningCount?: number;
  className?: string;
}

const ratingStyles: Record<AIQualityRating, { bg: string; text: string; ring: string }> = {
  'Strong Setup': {
    bg: 'bg-green-500/15',
    text: 'text-green-400',
    ring: 'ring-green-500/30',
  },
  'Acceptable Setup': {
    bg: 'bg-blue-500/15',
    text: 'text-blue-400',
    ring: 'ring-blue-500/30',
  },
  'Weak Setup': {
    bg: 'bg-amber-500/15',
    text: 'text-amber-400',
    ring: 'ring-amber-500/30',
  },
  'Avoid — High Risk': {
    bg: 'bg-red-500/15',
    text: 'text-red-400',
    ring: 'ring-red-500/30',
  },
};

/**
 * Compact badge/chip displaying the AI quality rating with color coding.
 * Shows warning count if warnings exist.
 *
 * Validates: Requirements 18.2-18.4
 */
export function AISignalBadge({ rating, warningCount = 0, className = '' }: AISignalBadgeProps) {
  const styles = ratingStyles[rating];

  return (
    <span
      className={`
        inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium
        ring-1 ring-inset
        ${styles.bg} ${styles.text} ${styles.ring}
        ${className}
      `}
      role="status"
      aria-label={`AI quality rating: ${rating}${warningCount > 0 ? `, ${warningCount} warning${warningCount > 1 ? 's' : ''}` : ''}`}
    >
      <span className="truncate">{rating}</span>
      {warningCount > 0 && (
        <span
          className={`
            inline-flex items-center justify-center w-4 h-4 rounded-full text-[10px] font-bold
            ${rating === 'Avoid — High Risk' ? 'bg-red-500/30' : 'bg-amber-500/30'}
          `}
          aria-hidden="true"
        >
          {warningCount}
        </span>
      )}
    </span>
  );
}
