import { useApi } from '../hooks/useApi';
import { api } from '../lib/api';

interface ModelVersion {
  version_id: string;
  created_at: string;
  sharpe: number | null;
  accuracy: number | null;
  is_active: boolean;
}

const MOCK_DATA: ModelVersion[] = [
  { version_id: 'v1.2.0', created_at: '2026-03-10', sharpe: 1.45, accuracy: 0.71, is_active: true },
  { version_id: 'v1.1.0', created_at: '2026-03-03', sharpe: 1.32, accuracy: 0.68, is_active: false },
  { version_id: 'v1.0.0', created_at: '2026-02-24', sharpe: 1.18, accuracy: 0.65, is_active: false },
];

export function ModelVersionHistory() {
  const { data } = useApi(() => api.strategies.mlMonitoring());
  const versions: ModelVersion[] = data?.model_versions ?? MOCK_DATA;

  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-wider text-muted mb-2">
        Model Version History
      </div>
      <div className="rounded-lg border border-border overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-panel border-b border-border">
              <th className="px-3 py-2 text-left font-mono text-[9px] text-muted uppercase">Version</th>
              <th className="px-3 py-2 text-left font-mono text-[9px] text-muted uppercase">Created</th>
              <th className="px-3 py-2 text-right font-mono text-[9px] text-muted uppercase">Sharpe</th>
              <th className="px-3 py-2 text-right font-mono text-[9px] text-muted uppercase">Accuracy</th>
              <th className="px-3 py-2 text-center font-mono text-[9px] text-muted uppercase">Status</th>
            </tr>
          </thead>
          <tbody>
            {versions.map((v) => (
              <tr key={v.version_id} className="border-b border-border/50 hover:bg-panel/50">
                <td className="px-3 py-2 font-mono text-bright">{v.version_id}</td>
                <td className="px-3 py-2 text-dim">{v.created_at}</td>
                <td className="px-3 py-2 text-right font-mono text-text">
                  {v.sharpe != null ? v.sharpe.toFixed(2) : '\u2014'}
                </td>
                <td className="px-3 py-2 text-right font-mono text-text">
                  {v.accuracy != null ? `${(v.accuracy * 100).toFixed(1)}%` : '\u2014'}
                </td>
                <td className="px-3 py-2 text-center">
                  {v.is_active ? (
                    <span className="rounded border border-gain/30 bg-gain-dim px-1.5 py-0.5 font-mono text-[9px] text-gain">
                      ACTIVE
                    </span>
                  ) : (
                    <span className="font-mono text-[9px] text-muted">archived</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
