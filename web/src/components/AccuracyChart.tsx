import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { useApi } from '../hooks/useApi';
import { api } from '../lib/api';

const MOCK_DATA = [
  { date: '03-01', accuracy: 0.62 },
  { date: '03-02', accuracy: 0.58 },
  { date: '03-03', accuracy: 0.65 },
  { date: '03-04', accuracy: 0.71 },
  { date: '03-05', accuracy: 0.68 },
  { date: '03-06', accuracy: 0.73 },
  { date: '03-07', accuracy: 0.69 },
  { date: '03-08', accuracy: 0.72 },
  { date: '03-09', accuracy: 0.67 },
  { date: '03-10', accuracy: 0.71 },
  { date: '03-11', accuracy: 0.74 },
];

export function AccuracyChart() {
  const { data } = useApi(() => api.strategies.mlMonitoring());
  const raw = data?.accuracy_history ?? [];
  const accuracy = raw.length > 0
    ? raw.map((d: any) => ({ date: d.date.slice(5), accuracy: d.accuracy }))
    : MOCK_DATA;

  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-wider text-muted mb-2">
        Rolling Accuracy
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <LineChart data={accuracy}>
          <XAxis dataKey="date" tick={{ fontSize: 9, fill: '#5a6273' }} />
          <YAxis domain={[0, 1]} tick={{ fontSize: 9, fill: '#5a6273' }} />
          <ReferenceLine
            y={0.4}
            stroke="#ff1744"
            strokeDasharray="3 3"
            label={{ value: 'Threshold', fill: '#ff1744', fontSize: 9 }}
          />
          <Line
            type="monotone"
            dataKey="accuracy"
            stroke="#00bcd4"
            strokeWidth={1.5}
            dot={false}
          />
          <Tooltip
            contentStyle={{
              background: '#181c25',
              border: '1px solid #232833',
              borderRadius: 8,
              fontFamily: 'JetBrains Mono',
              fontSize: 11,
            }}
            formatter={(v) => [`${(Number(v) * 100).toFixed(1)}%`, 'Accuracy']}
            labelFormatter={(l) => l}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
