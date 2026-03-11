import { useState } from 'react';
import { Zap, ZapOff, Wifi, WifiOff } from 'lucide-react';
import { useWebSocket } from '../hooks/useWebSocket';
import { formatCurrency, formatPct, pnlColor } from '../lib/format';
import { KillSwitchModal } from './KillSwitchModal';

// Demo data — replaced by live API in production
const DEMO = {
  equity: 21485.32,
  dailyPnl: 147.88,
  dailyPnlPct: 0.69,
  mode: 'PAPER_ONLY',
};

export function Header() {
  const { connected } = useWebSocket();
  const [showKillSwitch, setShowKillSwitch] = useState(false);
  const [killActive, setKillActive] = useState(false);

  return (
    <>
      <header className="flex h-14 items-center justify-between border-b border-border bg-abyss px-6">
        {/* Left: equity + P&L */}
        <div className="flex items-center gap-8">
          <div>
            <span className="font-mono text-[10px] uppercase tracking-wider text-muted">Equity</span>
            <p className="font-mono text-lg font-semibold text-bright leading-tight">
              {formatCurrency(DEMO.equity)}
            </p>
          </div>
          <div>
            <span className="font-mono text-[10px] uppercase tracking-wider text-muted">Daily P&L</span>
            <p className={`font-mono text-lg font-semibold leading-tight ${pnlColor(DEMO.dailyPnl)}`}>
              {formatCurrency(DEMO.dailyPnl)}{' '}
              <span className="text-sm">{formatPct(DEMO.dailyPnlPct)}</span>
            </p>
          </div>
        </div>

        {/* Right: status + kill switch */}
        <div className="flex items-center gap-4">
          {/* Connection status */}
          <div className="flex items-center gap-1.5">
            {connected ? (
              <Wifi className="h-3.5 w-3.5 text-gain live-pulse" />
            ) : (
              <WifiOff className="h-3.5 w-3.5 text-loss" />
            )}
            <span className="font-mono text-[10px] uppercase tracking-wider text-muted">
              {connected ? 'live' : 'disconnected'}
            </span>
          </div>

          {/* Autonomy mode badge */}
          <div className="rounded border border-amber-dim bg-amber-dim px-2 py-0.5 font-mono text-[10px] font-medium uppercase tracking-wider text-amber">
            {DEMO.mode.replace('_', ' ')}
          </div>

          {/* Kill switch */}
          <button
            onClick={() => setShowKillSwitch(true)}
            className={`flex items-center gap-1.5 rounded-md border px-3 py-1.5 font-mono text-xs font-medium uppercase tracking-wider transition-all ${
              killActive
                ? 'kill-armed border-loss bg-loss-dim text-loss'
                : 'border-border-bright bg-surface text-dim hover:border-loss hover:text-loss'
            }`}
          >
            {killActive ? <ZapOff className="h-3.5 w-3.5" /> : <Zap className="h-3.5 w-3.5" />}
            {killActive ? 'Kill Active' : 'Kill Switch'}
          </button>
        </div>
      </header>

      {showKillSwitch && (
        <KillSwitchModal
          active={killActive}
          onConfirm={() => {
            setKillActive(!killActive);
            setShowKillSwitch(false);
          }}
          onCancel={() => setShowKillSwitch(false)}
        />
      )}
    </>
  );
}
