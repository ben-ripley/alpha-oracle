import { useApi } from '../hooks/useApi';
import { api } from '../lib/api';

interface FeatureDrift {
  name: string;
  psi: number;
}

const MOCK_DATA: FeatureDrift[] = [
  { name: 'rsi_14', psi: 0.04 },
  { name: 'sma_20_200_ratio', psi: 0.07 },
  { name: 'volume_ratio_20d', psi: 0.12 },
  { name: 'macd_histogram', psi: 0.03 },
  { name: 'bb_width_20', psi: 0.28 },
  { name: 'atr_pct_14', psi: 0.06 },
  { name: 'obv_slope_10', psi: 0.15 },
  { name: 'sector_momentum', psi: 0.09 },
  { name: 'insider_net_30d', psi: 0.02 },
  { name: 'pe_sector_rank', psi: 0.11 },
];

function psiColor(psi: number) {
  if (psi < 0.1) return 'bg-gain/20 text-gain';
  if (psi < 0.25) return 'bg-amber/20 text-amber';
  return 'bg-loss/20 text-loss';
}

function psiLabel(psi: number) {
  if (psi < 0.1) return 'OK';
  if (psi < 0.25) return 'WARN';
  return 'DRIFT';
}

export function DriftHeatmap() {
  const { data } = useApi(() => api.strategies.mlMonitoring());
  const features: FeatureDrift[] = data?.feature_drift ?? MOCK_DATA;

  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-wider text-muted mb-2">
        Feature Drift (PSI)
      </div>
      <div className="space-y-1">
        {features.map((f) => (
          <div key={f.name} className="flex items-center gap-2">
            <span className="font-mono text-[10px] text-dim w-32 truncate">{f.name}</span>
            <div className="flex-1 h-4 bg-panel rounded overflow-hidden">
              <div
                className={`h-full ${psiColor(f.psi)}`}
                style={{ width: `${Math.min(f.psi * 400, 100)}%` }}
              />
            </div>
            <span className={`font-mono text-[9px] ${psiColor(f.psi)} px-1.5 py-0.5 rounded`}>
              {f.psi.toFixed(3)} {psiLabel(f.psi)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
