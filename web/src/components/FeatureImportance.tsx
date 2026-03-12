import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { useApi } from '../hooks/useApi';
import { api } from '../lib/api';

export function FeatureImportance() {
  const { data, loading } = useApi(() => api.strategies.mlFeatureImportance());
  const features: { name: string; importance: number }[] = data?.features ?? [];

  return (
    <div className="space-y-3">
      <h3 className="font-mono text-[10px] uppercase tracking-wider text-muted">Feature Importance</h3>
      {loading ? (
        <div className="py-6 text-center font-mono text-xs text-muted">Loading...</div>
      ) : features.length === 0 ? (
        <div className="py-6 text-center font-mono text-xs text-muted">No data</div>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={features} layout="vertical" margin={{ left: 4, right: 16, top: 0, bottom: 0 }}>
            <XAxis type="number" hide />
            <YAxis
              type="category"
              dataKey="name"
              width={120}
              tick={{ fill: '#6b7280', fontSize: 10, fontFamily: 'JetBrains Mono' }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              contentStyle={{
                background: '#181c25',
                border: '1px solid #232833',
                borderRadius: 8,
                fontFamily: 'JetBrains Mono',
                fontSize: 11,
              }}
              formatter={(v: number) => [v.toFixed(4), 'Importance']}
            />
            <Bar dataKey="importance" radius={[0, 4, 4, 0]} maxBarSize={16}>
              {features.map((_, i) => (
                <Cell key={i} fill={i === 0 ? '#22d3ee' : 'rgba(34,211,238,0.5)'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
