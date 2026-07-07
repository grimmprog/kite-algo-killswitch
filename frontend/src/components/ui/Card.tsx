import type { HTMLAttributes, ReactNode } from 'react';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  title?: string;
  subtitle?: string;
  padding?: 'none' | 'sm' | 'md' | 'lg';
}

const paddingStyles = {
  none: '',
  sm: 'p-3',
  md: 'p-4',
  lg: 'p-6',
};

export function Card({
  children,
  title,
  subtitle,
  padding = 'md',
  className = '',
  ...props
}: CardProps) {
  return (
    <div
      className={`
        bg-dashboard-card border border-dashboard-border rounded-xl
        ${paddingStyles[padding]}
        ${className}
      `}
      {...props}
    >
      {(title || subtitle) && (
        <div className={`${padding === 'none' ? 'px-4 pt-4' : ''} mb-3`}>
          {title && (
            <h3 className="text-sm font-medium text-dashboard-text">{title}</h3>
          )}
          {subtitle && (
            <p className="text-xs text-dashboard-muted mt-0.5">{subtitle}</p>
          )}
        </div>
      )}
      {children}
    </div>
  );
}

interface CardStatProps {
  label: string;
  value: string | number;
  variant?: 'default' | 'profit' | 'loss' | 'neutral';
}

const valueStyles = {
  default: 'text-dashboard-text',
  profit: 'text-profit',
  loss: 'text-loss',
  neutral: 'text-dashboard-muted',
};

export function CardStat({ label, value, variant = 'default' }: CardStatProps) {
  return (
    <div>
      <p className="text-xs text-dashboard-muted">{label}</p>
      <p className={`text-lg font-mono font-semibold ${valueStyles[variant]}`}>
        {value}
      </p>
    </div>
  );
}
