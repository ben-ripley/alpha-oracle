import { useApi } from '../hooks/useApi';
import { api } from '../lib/api';

const DRIFT_STYLES: Record<string, string> = {
  OK: 'text-gain',
  Warning: 'text-amber',
  Critical: 'text-loss',
};

export function ModelPerformance() {
  const { data, loading } = useApi(() => api.strategies.mlSignals());

  const model = data?.model_meta ?? {
    accuracy: 0.73,
    precision: 0.69,
    recall: 0.71,
    model_version: 'v0.1.0-mock',
    last_trained: '2026-03-10',
    drift_status: 'OK',
    fallback_active: false,
  };

  if (loading) {
    return (
      <div className="space-y-3">
        <h3 className="font-mono text-[10px] uppercase tracking-wider text-muted">Model Performance</h3>
        <div className="py-6 text-center font-mono text-xs text-muted">Loading...</div>
      </div>
    );
  }

  const metrics = [
    { label: 'Accuracy', value: `${(model.accuracy * 100).toFixed(1)}%` },
    { label: 'Precision', value: `${(model.precision * 100).toFixed(1)}%` },
    { label: 'Recall', value: `${(model.recall * 100).toFixed(1)}%` },
  ];

  return (
    <div className="space-y-3">
      <h3 className="font-mono text-[10px] uppercase tracking-wider text-muted">Model Performance</h3>
      <div className="grid grid-cols-3 gap-2">
        {metrics.map((m) => (
          <div key={m.label} className="rounded-lg bg-panel px-3 py-2 text-center">
            <div className="font-mono text-[9px] uppercase tracking-wider text-muted">{m.label}</div>
            <div className="font-mono text-sm font-semibold text-bright">{m.value}</div>
          </div>
        ))}
      </div>
      <div className="space-y-1.5 text-xs">
        <div className="flex justify-between">
          <span className="text-dim">Version</span>
          <span className="font-mono text-text">{model.model_version}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-dim">Last Trained</span>
          <span className="font-mono text-text">{model.last_trained}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-dim">Drift Status</span>
          <span className={`font-mono font-semibold ${DRIFT_STYLES[model.drift_status] ?? 'text-muted'}`}>
            {model.drift_status}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-dim">Fallback</span>
          <span className={`font-mono font-semibold ${model.fallback_active ? 'text-amber' : 'text-gain'}`}>
            {model.fallback_active ? 'Active' : 'Inactive'}
          </span>
        </div>
      </div>
    </div>
  );
}
