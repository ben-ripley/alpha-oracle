import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  FlaskConical,
  ShieldAlert,
  ArrowLeftRight,
  Activity,
  BarChart2,
  BrainCircuit,
} from 'lucide-react';

const links = [
  { to: '/', icon: LayoutDashboard, label: 'Portfolio' },
  { to: '/strategies', icon: FlaskConical, label: 'Strategies' },
  { to: '/backtest', icon: BarChart2, label: 'Backtest' },
  { to: '/risk', icon: ShieldAlert, label: 'Risk' },
  { to: '/trades', icon: ArrowLeftRight, label: 'Trades' },
  { to: '/model-health', icon: BrainCircuit, label: 'Model Health' },
];

export function Sidebar() {
  return (
    <aside className="relative z-10 flex w-[68px] flex-col items-center border-r border-border bg-abyss py-4">
      {/* Logo mark */}
      <div className="mb-8 flex h-10 w-10 items-center justify-center rounded-lg bg-cyan-dim">
        <Activity className="h-5 w-5 text-cyan" />
      </div>

      <nav className="flex flex-1 flex-col gap-1">
        {links.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `group relative flex h-11 w-11 items-center justify-center rounded-lg transition-all ${
                isActive
                  ? 'bg-panel text-cyan shadow-[inset_0_0_0_1px_var(--color-border-bright)]'
                  : 'text-muted hover:bg-surface hover:text-dim'
              }`
            }
          >
            <Icon className="h-[18px] w-[18px]" strokeWidth={1.8} />
            <span className="pointer-events-none absolute left-full ml-3 whitespace-nowrap rounded bg-panel px-2 py-1 font-mono text-xs text-dim opacity-0 shadow-lg transition-opacity group-hover:opacity-100 border border-border">
              {label}
            </span>
          </NavLink>
        ))}
      </nav>

      {/* Environment indicator */}
      <div className="mt-auto font-mono text-[9px] uppercase tracking-widest text-muted [writing-mode:vertical-lr] rotate-180">
        paper
      </div>
    </aside>
  );
}
