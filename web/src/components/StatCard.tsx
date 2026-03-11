import type { ReactNode } from 'react';

interface Props {
  label: string;
  value: string;
  sub?: string;
  icon?: ReactNode;
  color?: 'cyan' | 'gain' | 'loss' | 'amber' | 'default';
  className?: string;
}

const colorMap = {
  cyan: 'text-cyan',
  gain: 'text-gain',
  loss: 'text-loss',
  amber: 'text-amber',
  default: 'text-bright',
};

export function StatCard({ label, value, sub, icon, color = 'default', className = '' }: Props) {
  return (
    <div className={`glow-border rounded-xl bg-surface p-4 ${className}`}>
      <div className="mb-2 flex items-center justify-between">
        <span className="font-mono text-[10px] uppercase tracking-wider text-muted">{label}</span>
        {icon && <span className="text-muted">{icon}</span>}
      </div>
      <p className={`font-mono text-2xl font-bold leading-tight ${colorMap[color]}`}>
        {value}
      </p>
      {sub && (
        <p className="mt-0.5 font-mono text-xs text-dim">{sub}</p>
      )}
    </div>
  );
}
