import { useState } from 'react';
import { AlertTriangle, ShieldOff, Shield } from 'lucide-react';

interface Props {
  active: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function KillSwitchModal({ active, onConfirm, onCancel }: Props) {
  const [confirmText, setConfirmText] = useState('');
  const required = active ? 'RESUME' : 'KILL';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-void/80 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-xl border border-border-bright bg-surface p-6 shadow-2xl">
        <div className="mb-4 flex items-center gap-3">
          {active ? (
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gain-dim">
              <Shield className="h-5 w-5 text-gain" />
            </div>
          ) : (
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-loss-dim kill-armed">
              <ShieldOff className="h-5 w-5 text-loss" />
            </div>
          )}
          <div>
            <h2 className="font-mono text-sm font-semibold uppercase tracking-wider text-bright">
              {active ? 'Resume Trading' : 'Activate Kill Switch'}
            </h2>
            <p className="text-xs text-muted">
              {active ? 'This will resume automated trading.' : 'This will cancel all open orders and halt all trading.'}
            </p>
          </div>
        </div>

        {!active && (
          <div className="mb-4 flex items-start gap-2 rounded-lg border border-amber-dim bg-amber-dim p-3">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber" />
            <p className="text-xs text-amber">
              All open orders will be cancelled immediately. No new trades will be submitted until the kill switch is deactivated and the cooldown period has elapsed.
            </p>
          </div>
        )}

        <div className="mb-4">
          <label className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-muted">
            Type "{required}" to confirm
          </label>
          <input
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            className="w-full rounded-lg border border-border bg-abyss px-3 py-2 font-mono text-sm text-bright outline-none focus:border-border-bright"
            placeholder={required}
            autoFocus
          />
        </div>

        <div className="flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 rounded-lg border border-border bg-panel py-2 font-mono text-xs font-medium uppercase tracking-wider text-dim transition-colors hover:text-text"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={confirmText !== required}
            className={`flex-1 rounded-lg border py-2 font-mono text-xs font-medium uppercase tracking-wider transition-all ${
              confirmText === required
                ? active
                  ? 'border-gain bg-gain-dim text-gain hover:bg-gain/20'
                  : 'border-loss bg-loss-dim text-loss hover:bg-loss/20'
                : 'cursor-not-allowed border-border bg-panel text-muted'
            }`}
          >
            {active ? 'Resume Trading' : 'Activate Kill Switch'}
          </button>
        </div>
      </div>
    </div>
  );
}
