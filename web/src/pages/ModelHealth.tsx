import { BrainCircuit } from 'lucide-react';
import { AccuracyChart } from '../components/AccuracyChart';
import { DriftHeatmap } from '../components/DriftHeatmap';
import { ModelVersionHistory } from '../components/ModelVersionHistory';
import { ModelPerformance } from '../components/ModelPerformance';
import { useApi } from '../hooks/useApi';
import { api } from '../lib/api';

export function ModelHealth() {
  const { data: monitoring } = useApi(() => api.strategies.mlMonitoring());

  const rollingAccuracy: number = monitoring?.rolling_accuracy ?? 0.71;
  const maxPsi: number = monitoring?.max_psi ?? 0.28;
  const fallbackActive: boolean = monitoring?.fallback_active ?? false;
  const currentStatus: string = monitoring?.current_status ?? 'ok';

  const statusColor =
    currentStatus === 'ok' ? 'text-gain' :
    currentStatus === 'warning' ? 'text-amber' : 'text-loss';

  const statusBg =
    currentStatus === 'ok' ? 'bg-gain-dim border-gain/30' :
    currentStatus === 'warning' ? 'bg-amber-dim border-amber/30' : 'bg-loss-dim border-loss/30';

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <BrainCircuit className="h-4 w-4 text-cyan" />
        <h1 className="font-mono text-sm font-semibold uppercase tracking-wider text-bright">
          Model Health
        </h1>
      </div>

      {/* Status bar */}
      <div className="glow-border rounded-xl bg-surface p-5">
        <div className="grid grid-cols-4 gap-4">
          <div className="rounded-lg bg-panel px-4 py-3">
            <div className="font-mono text-[9px] uppercase tracking-wider text-muted mb-1">
              System Status
            </div>
            <div className={`font-mono text-sm font-bold uppercase rounded border px-2 py-0.5 inline-block ${statusBg} ${statusColor}`}>
              {currentStatus}
            </div>
          </div>
          <div className="rounded-lg bg-panel px-4 py-3">
            <div className="font-mono text-[9px] uppercase tracking-wider text-muted mb-1">
              Rolling Accuracy
            </div>
            <div className={`font-mono text-sm font-semibold ${rollingAccuracy >= 0.6 ? 'text-gain' : 'text-loss'}`}>
              {(rollingAccuracy * 100).toFixed(1)}%
            </div>
          </div>
          <div className="rounded-lg bg-panel px-4 py-3">
            <div className="font-mono text-[9px] uppercase tracking-wider text-muted mb-1">
              Max PSI Drift
            </div>
            <div className={`font-mono text-sm font-semibold ${maxPsi < 0.1 ? 'text-gain' : maxPsi < 0.2 ? 'text-amber' : 'text-loss'}`}>
              {maxPsi.toFixed(3)}
            </div>
          </div>
          <div className="rounded-lg bg-panel px-4 py-3">
            <div className="font-mono text-[9px] uppercase tracking-wider text-muted mb-1">
              Fallback Mode
            </div>
            <div className={`font-mono text-sm font-semibold ${fallbackActive ? 'text-amber' : 'text-gain'}`}>
              {fallbackActive ? 'Active' : 'Inactive'}
            </div>
          </div>
        </div>
      </div>

      {/* Model performance + accuracy chart */}
      <div className="grid grid-cols-3 gap-6">
        <div className="glow-border rounded-xl bg-surface p-5">
          <ModelPerformance />
        </div>
        <div className="col-span-2 glow-border rounded-xl bg-surface p-5">
          <AccuracyChart />
        </div>
      </div>

      {/* Drift heatmap + version history */}
      <div className="grid grid-cols-2 gap-6">
        <div className="glow-border rounded-xl bg-surface p-5">
          <DriftHeatmap />
        </div>
        <div className="glow-border rounded-xl bg-surface p-5">
          <ModelVersionHistory />
        </div>
      </div>
    </div>
  );
}
