import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Portfolio } from './pages/Portfolio';
import { Strategies } from './pages/Strategies';
import { Risk } from './pages/Risk';
import { Trades } from './pages/Trades';
import { Backtest } from './pages/Backtest';
import { ModelHealth } from './pages/ModelHealth';
import { Agent } from './pages/Agent';
import { Analysis } from './pages/Analysis';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Portfolio />} />
          <Route path="/strategies" element={<Strategies />} />
          <Route path="/risk" element={<Risk />} />
          <Route path="/trades" element={<Trades />} />
          <Route path="/backtest" element={<Backtest />} />
          <Route path="/model-health" element={<ModelHealth />} />
          <Route path="/agent" element={<Agent />} />
          <Route path="/analysis" element={<Analysis />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
