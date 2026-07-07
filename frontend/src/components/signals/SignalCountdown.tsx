import { useMemo } from 'react';

interface SignalCountdownProps {
  /** Remaining seconds on the countdown */
  remainingSeconds: number;
  /** Total countdown duration in seconds */
  totalSeconds: number;
  /** Size of the countdown display */
  size?: 'sm' | 'md' | 'lg';
}

const sizeConfig = {
  sm: { dimension: 48, strokeWidth: 3, fontSize: 'text-xs' },
  md: { dimension: 64, strokeWidth: 4, fontSize: 'text-sm' },
  lg: { dimension: 80, strokeWidth: 5, fontSize: 'text-base' },
};

/**
 * Circular countdown timer component for signal approval.
 * Displays remaining seconds with a diminishing ring.
 */
export function SignalCountdown({
  remainingSeconds,
  totalSeconds,
  size = 'md',
}: SignalCountdownProps) {
  const config = sizeConfig[size];
  const radius = (config.dimension - config.strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;

  const progress = useMemo(() => {
    if (totalSeconds <= 0) return 0;
    return Math.max(0, Math.min(1, remainingSeconds / totalSeconds));
  }, [remainingSeconds, totalSeconds]);

  const strokeDashoffset = circumference * (1 - progress);

  // Color transitions: green → yellow → red as time runs out
  const progressColor = useMemo(() => {
    if (progress > 0.5) return 'text-profit';
    if (progress > 0.25) return 'text-yellow-400';
    return 'text-loss';
  }, [progress]);

  const isUrgent = remainingSeconds <= 10;

  return (
    <div
      className="relative inline-flex items-center justify-center"
      role="timer"
      aria-label={`${remainingSeconds} seconds remaining`}
      aria-live="polite"
    >
      <svg
        width={config.dimension}
        height={config.dimension}
        className={`transform -rotate-90 ${isUrgent ? 'animate-pulse' : ''}`}
        aria-hidden="true"
      >
        {/* Background circle */}
        <circle
          cx={config.dimension / 2}
          cy={config.dimension / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={config.strokeWidth}
          className="text-dashboard-border"
        />
        {/* Progress circle */}
        <circle
          cx={config.dimension / 2}
          cy={config.dimension / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={config.strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          className={`${progressColor} transition-all duration-1000 ease-linear`}
        />
      </svg>
      {/* Center text */}
      <span
        className={`absolute font-mono font-bold ${config.fontSize} ${progressColor}`}
      >
        {remainingSeconds}s
      </span>
    </div>
  );
}
