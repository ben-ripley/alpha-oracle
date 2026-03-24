---
title: Frontend
nav_order: 3
parent: Developer Guide
has_children: true
---

# Frontend Dashboard Architecture

The dashboard is a React 18 single-page application styled with TailwindCSS and built with Vite. It provides real-time visibility into portfolio performance, active strategies, risk metrics, and ML model health.

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Framework | React 18 | Component-based UI with hooks |
| Language | TypeScript | Type safety and IDE support |
| Build tool | Vite | Fast dev server with HMR |
| Styling | TailwindCSS | Utility-first CSS framework |
| Charts | Recharts | Declarative React charts |
| Icons | Lucide React | Consistent icon set |
| HTTP client | Fetch API | REST API calls via `useApi` hook |
| WebSocket | Native WebSocket | Real-time updates via `useWebSocket` hook |

**Project structure:**
```
web/
├── src/
│   ├── pages/           # Main page components (4 pages)
│   │   ├── Portfolio.tsx
│   │   ├── Strategies.tsx
│   │   ├── Risk.tsx
│   │   └── Trades.tsx
│   ├── components/      # Reusable UI components
│   │   ├── layout/      # AppLayout, Sidebar, Header
│   │   ├── portfolio/   # PositionCard, PerformanceChart, etc.
│   │   ├── strategies/  # StrategyCard, SignalFeed, etc.
│   │   ├── risk/        # RiskMetrics, CircuitBreakerStatus, etc.
│   │   ├── trades/      # TradeHistory, OrderBook, etc.
│   │   └── ml/          # FeatureImportance, ModelPerformance, DriftHeatmap, etc.
│   ├── hooks/           # Custom React hooks
│   │   ├── useApi.ts    # REST API client
│   │   └── useWebSocket.ts  # WebSocket connection manager
│   ├── lib/             # Utilities and types
│   │   ├── types.ts     # TypeScript interfaces
│   │   └── utils.ts     # Helper functions
│   ├── App.tsx          # Root component with routing
│   └── main.tsx         # Entry point
├── vite.config.ts       # Vite configuration
├── tailwind.config.js   # TailwindCSS configuration
└── package.json         # Dependencies
```

---

## Design System

### Dark Terminal Aesthetic

**Inspiration:** "Bloomberg meets Blade Runner" — professional trading terminal with cyberpunk accents.

**Color palette:**

| Name | Hex | Usage |
|------|-----|-------|
| `void` | `#0a0a0f` | Page background |
| `abyss` | `#12121a` | Card/panel background |
| `surface` | `#1a1a2e` | Elevated surfaces, hover states |
| `cyan` | `#00d9ff` | Accent color, links, buttons |
| `gain-green` | `#00ff88` | Positive values (PnL, returns) |
| `loss-red` | `#ff3366` | Negative values (losses, drawdowns) |
| `amber` | `#ffaa00` | Warnings, alerts |
| `muted` | `#6b7280` | Secondary text, disabled states |

**Configuration in `tailwind.config.js`:**
```javascript
module.exports = {
  theme: {
    extend: {
      colors: {
        void: '#0a0a0f',
        abyss: '#12121a',
        surface: '#1a1a2e',
        cyan: '#00d9ff',
        'gain-green': '#00ff88',
        'loss-red': '#ff3366',
        amber: '#ffaa00',
      },
    },
  },
}
```

### Typography

**Fonts:**
- **JetBrains Mono** — monospace font for code, data, and numeric values
- **Outfit** — sans-serif font for headings and labels

**Loading:** Fonts are loaded via `@fontsource` packages in `main.tsx`:
```typescript
import '@fontsource/jetbrains-mono/400.css';
import '@fontsource/jetbrains-mono/600.css';
import '@fontsource/outfit/400.css';
import '@fontsource/outfit/600.css';
```

**Usage:**
```tsx
<h1 className="font-outfit font-semibold">Portfolio Overview</h1>
<pre className="font-mono text-sm">AAPL: $178.42</pre>
```

### Icons

**Lucide React** provides a consistent, MIT-licensed icon set:
```typescript
import { TrendingUp, AlertCircle, Shield } from 'lucide-react';

<TrendingUp className="w-5 h-5 text-gain-green" />
```

**Common icons:**
- `TrendingUp` / `TrendingDown` — performance indicators
- `AlertCircle` — warnings and alerts
- `Shield` — risk management
- `Activity` — real-time updates
- `BarChart3` — charts and analytics

---

## Component Organization

### Pages (Top-level routes)

**1. Portfolio (`/`)**
- Current equity, cash, positions value
- Daily P&L, total P&L, max drawdown
- Position cards with real-time price updates
- Sector exposure pie chart
- Performance line chart (equity curve)

**2. Strategies (`/strategies`)**
- Active strategy cards (name, description, status)
- Signal feed (live signals from strategy engine)
- Strategy parameters and performance metrics
- ML model health (Phase 2): FeatureImportance, ModelPerformance, AccuracyChart, DriftHeatmap

**3. Risk (`/risk`)**
- Position limits (per-position, sector)
- Portfolio limits (drawdown, daily loss, cash reserve)
- PDT guard status (day trades remaining)
- Circuit breaker status (VIX, stale data, reconciliation)
- Kill switch control (with typed confirmation modal)

**4. Trades (`/trades`)**
- Trade history table (entry/exit, P&L, hold duration)
- Order book (pending, filled, cancelled orders)
- Execution quality metrics (fill price vs signal price)
- Day trade tracker (PDT compliance)

### Reusable Components

**Layout:**
- `AppLayout` — sidebar + header + page content wrapper
- `Sidebar` — navigation menu with icons
- `Header` — page title, breadcrumbs, connection status

**Data display:**
- `StatCard` — key metric with label, value, change indicator
- `PositionCard` — individual position details
- `TradeRow` — single trade in history table
- `OrderRow` — single order in order book

**Charts (Recharts):**
- `PerformanceChart` — equity curve line chart
- `SectorChart` — sector exposure pie chart
- `SignalStrengthBar` — horizontal bar for signal strength (0-100%)

**ML Components (Phase 2):**
- `FeatureImportance` — horizontal bar chart of XGBoost feature importance
- `ModelPerformance` — accuracy, precision, recall, F1 score cards
- `AccuracyChart` — rolling accuracy over time
- `DriftHeatmap` — PSI drift scores by feature
- `ModelVersionHistory` — model registry with promote/rollback controls

---

## Routing

React Router handles client-side navigation:

```typescript
import { BrowserRouter, Routes, Route } from 'react-router-dom';

<BrowserRouter>
  <Routes>
    <Route path="/" element={<Portfolio />} />
    <Route path="/strategies" element={<Strategies />} />
    <Route path="/risk" element={<Risk />} />
    <Route path="/trades" element={<Trades />} />
  </Routes>
</BrowserRouter>
```

---

## API Integration

### REST API

The `useApi` hook wraps the Fetch API for typed requests:

```typescript
import { useApi } from '../hooks/useApi';

function Portfolio() {
  const { data, loading, error } = useApi<PortfolioSnapshot>('/api/portfolio');

  if (loading) return <Spinner />;
  if (error) return <ErrorMessage error={error} />;

  return <div>Total Equity: ${data.total_equity}</div>;
}
```

**Vite proxy configuration** (`vite.config.ts`):
```typescript
export default defineConfig({
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://localhost:8000',  // Proxy /api/* to FastAPI
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
})
```

All `/api/*` requests are proxied to the FastAPI backend on port 8000. This avoids CORS issues and simplifies deployment.

### WebSocket

The `useWebSocket` hook manages a persistent connection to `/ws` for real-time updates:

```typescript
import { useWebSocket } from '../hooks/useWebSocket';

function Portfolio() {
  const { lastMessage, connected } = useWebSocket();

  useEffect(() => {
    if (lastMessage?.channel === 'portfolio:update') {
      // Update portfolio state
      setPortfolio(lastMessage.data);
    }
  }, [lastMessage]);

  return <div className={connected ? 'text-gain-green' : 'text-loss-red'}>
    {connected ? 'Connected' : 'Disconnected'}
  </div>;
}
```

**Connection behavior:**
- Auto-connects on mount
- Sends ping every 30 seconds for keepalive
- Auto-reconnects on disconnect (3-second backoff)
- Filters out `pong` messages from render triggers

**Channels:** See [WebSocket Events](websocket-events.md) for full event list.

---

## Data Visualization

**Recharts** provides declarative React charts:

```typescript
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

<ResponsiveContainer width="100%" height={300}>
  <LineChart data={equityCurve}>
    <XAxis dataKey="timestamp" stroke="#6b7280" />
    <YAxis stroke="#6b7280" />
    <Tooltip
      contentStyle={{
        backgroundColor: '#1a1a2e',
        border: '1px solid #00d9ff'
      }}
    />
    <Line
      type="monotone"
      dataKey="equity"
      stroke="#00ff88"
      strokeWidth={2}
      dot={false}
    />
  </LineChart>
</ResponsiveContainer>
```

**Chart color conventions:**
- Green (`gain-green`) for positive metrics (equity, profit)
- Red (`loss-red`) for negative metrics (losses, drawdown)
- Cyan (`cyan`) for neutral data (volume, generic lines)
- Amber (`amber`) for warnings (thresholds, limits)

---

## State Management

**Local state:** React hooks (`useState`, `useEffect`) for component-level state.

**No global state library:** The app is small enough that props and hooks suffice. If complexity grows, consider Zustand or Jotai.

**Data fetching:** `useApi` hook with built-in loading/error states.

**Real-time updates:** WebSocket events trigger re-renders via `useState`.

---

## Development

### Start dev server
```bash
cd web
npm install
npm run dev  # or use ./scripts/start-frontend.sh
```

Dev server runs on `http://localhost:3000` with hot module replacement (HMR).

### Build for production
```bash
cd web
npm run build  # outputs to web/dist/
```

### Linting
```bash
npm run lint
```

---

## Browser Support

**Target:** Modern evergreen browsers (Chrome, Firefox, Safari, Edge)

**Minimum versions:**
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

No IE11 support. The build uses ES2020 features (optional chaining, nullish coalescing).

---

<!-- DIAGRAM: Component hierarchy showing page structure and data flow from API/WebSocket to components -->
