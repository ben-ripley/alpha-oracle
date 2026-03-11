export interface StrategySection {
  title: string;
  body: string;
}

export interface StrategyReference {
  label: string;
  url: string;
}

export interface StrategyDescription {
  /** Matches `strategy_name` from the API */
  id: string;
  displayName: string;
  tagline: string;
  sections: StrategySection[];
  parameters: { label: string; value: string; note: string }[];
  bestFor: string;
  risks: string;
  references: StrategyReference[];
}

export const STRATEGY_DESCRIPTIONS: Record<string, StrategyDescription> = {
  swing_momentum: {
    id: 'swing_momentum',
    displayName: 'Swing Momentum',
    tagline: 'Ride trending moves using moving average crossovers filtered by RSI.',
    sections: [
      {
        title: 'Core Idea',
        body:
          'Momentum strategies bet that assets which have recently been rising will continue to rise for a while longer. This strategy identifies the start of an upward trend by watching for a faster-moving average to cross above a slower one — a classic sign that short-term price action has become stronger than the long-term trend.',
      },
      {
        title: 'Entry Signal',
        body:
          'A BUY signal fires when two conditions are met simultaneously: (1) the 10-day simple moving average (SMA) crosses above the 50-day SMA on the current bar — it was below on the previous bar, meaning this is a fresh crossover; and (2) RSI(14) is below 70, confirming the stock is not yet in overbought territory. Signal strength scales with how much RSI headroom remains below 70 — a very low RSI produces a stronger signal.',
      },
      {
        title: 'Exit Signal',
        body:
          'After the minimum 3-day hold (required for PDT compliance), the position is closed when any of three exit conditions trigger: the 10-day SMA falls back below the 50-day SMA (trend reversal), RSI(14) exceeds 80 (extreme overbought), or the price has dropped 5% or more below the entry price (stop-loss). The stop-loss exit carries the highest urgency score.',
      },
      {
        title: 'Signal Strength',
        body:
          'Strength is a 0.0–1.0 score used by the order generator to size positions via Kelly criterion. On entry, strength = (70 − RSI) / 100, capped at 1.0 — the more room before overbought, the larger the position. On exit, stop-loss exits score 0.8 vs 0.6 for technical exits, communicating urgency to the execution layer.',
      },
    ],
    parameters: [
      { label: 'Fast MA', value: '10 days', note: 'Short-term trend line' },
      { label: 'Slow MA', value: '50 days', note: 'Long-term trend baseline' },
      { label: 'RSI Period', value: '14 days', note: 'Wilder\'s standard period' },
      { label: 'RSI Entry Cap', value: '< 70', note: 'Avoids chasing overbought stocks' },
      { label: 'RSI Exit', value: '> 80', note: 'Extreme overbought exit' },
      { label: 'Stop Loss', value: '5%', note: 'Hard downside floor' },
      { label: 'Min Hold', value: '3 days', note: 'PDT rule compliance' },
    ],
    bestFor:
      'Trending markets where stocks establish clear directional momentum. Works best when sector or macro tailwinds support broad upward trends.',
    risks:
      'Whipsaws in choppy, sideways markets generate false crossovers and frequent stop-outs. The 50-day MA lag means entries often occur after a significant portion of the move has already happened.',
    references: [
      {
        label: 'Jegadeesh & Titman (1993) — Returns to Buying Winners and Selling Losers',
        url: 'https://doi.org/10.1111/j.1540-6261.1993.tb04702.x',
      },
    ],
  },

  mean_reversion: {
    id: 'mean_reversion',
    displayName: 'Mean Reversion',
    tagline: 'Buy statistically oversold pullbacks and exit when price normalises.',
    sections: [
      {
        title: 'Core Idea',
        body:
          'Mean reversion strategies exploit the tendency of prices to snap back toward their historical average after extreme moves. The premise is that when a stock drops far enough below its recent average — especially alongside signs of overselling in momentum — it is priced at a discount and likely to recover.',
      },
      {
        title: 'Bollinger Bands',
        body:
          'Bollinger Bands place an upper and lower envelope around a 20-day moving average, each band sitting 2 standard deviations away. Because standard deviations describe typical price variation, roughly 95% of closes fall inside the bands. When price touches or breaks below the lower band, it is statistically unusually cheap relative to recent behaviour — a potential reversion opportunity.',
      },
      {
        title: 'Entry Signal',
        body:
          'A BUY signal fires only when both conditions are true simultaneously: (1) closing price is at or below the lower Bollinger Band (BBL_20_2.0) — price is statistically extended to the downside; and (2) RSI(14) is below 30 — momentum confirms the oversold reading. Requiring both a price extreme AND a momentum extreme reduces false signals. Signal strength scales with how far RSI sits below 30: deeper oversold = larger position.',
      },
      {
        title: 'Exit Signal',
        body:
          'After the minimum 2-day hold, the position closes when any of three conditions occur: price reaches or exceeds the middle Bollinger Band (the 20-day SMA) — the reversion target has been achieved; RSI(14) rises above 60 — momentum has normalised; or the price falls 5% below entry — stop-loss. The middle band exit is the primary profit-taking target.',
      },
    ],
    parameters: [
      { label: 'BB Period', value: '20 days', note: 'Moving average window' },
      { label: 'BB Width', value: '2 std dev', note: '~95% of prices inside bands' },
      { label: 'RSI Period', value: '14 days', note: 'Momentum confirmation' },
      { label: 'RSI Entry', value: '< 30', note: 'Classic oversold threshold' },
      { label: 'RSI Exit', value: '> 60', note: 'Momentum normalised' },
      { label: 'Stop Loss', value: '5%', note: 'Hard downside floor' },
      { label: 'Min Hold', value: '2 days', note: 'PDT rule compliance' },
    ],
    bestFor:
      'Range-bound or mildly trending markets where individual stocks periodically overshoot in both directions. Well-suited to quality stocks with stable fundamentals that tend to recover from technical shakeouts.',
    risks:
      'Dangerous in strong downtrends — a stock can be "statistically cheap" and keep falling. The strategy has no fundamental filter, so it can buy genuinely deteriorating businesses. Stop-losses limit but do not eliminate gap-down risk.',
    references: [
      {
        label: 'DeBondt & Thaler (1985) — Does the Stock Market Overreact?',
        url: 'https://doi.org/10.1111/j.1540-6261.1985.tb05004.x',
      },
      {
        label: 'John Bollinger — Bollinger Bands (Official Site)',
        url: 'https://www.bollingerbands.com/bollinger-bands',
      },
    ],
  },

  value_factor: {
    id: 'value_factor',
    displayName: 'Value Factor',
    tagline: 'Systematically own the cheapest stocks; avoid the most expensive.',
    sections: [
      {
        title: 'Core Idea',
        body:
          'Value investing uses fundamental accounting metrics to find stocks trading at a discount to their intrinsic worth. This strategy automates the process by ranking a universe of stocks on three widely-used valuation ratios and periodically rebalancing into the cheapest names.',
      },
      {
        title: 'Valuation Metrics',
        body:
          'Three ratios are combined into a composite value score. Price-to-Earnings (P/E) compares market cap to annual profit — lower means you pay less per dollar of earnings (40% weight). Price-to-Book (P/B) compares market cap to net asset value — lower means you pay less than the accounting value of assets (30% weight). EV/EBITDA compares enterprise value to operating cash flows, making it useful across capital structures (30% weight). Lower values on all three ratios are better.',
      },
      {
        title: 'Scoring & Ranking',
        body:
          'For each metric, every stock is assigned a percentile rank within the universe. Because lower ratios are better, the rank is inverted: a P/E in the bottom 10% of the universe scores 0.90 on that metric. The three inverted percentiles are blended using their weights to produce a single composite score between 0 and 1. Stocks with missing or negative ratios are excluded from scoring for that metric.',
      },
      {
        title: 'Signals & Rebalancing',
        body:
          'The top 20% of stocks by composite score generate LONG signals; the bottom 20% generate SHORT/sell signals. Signals are emitted on a configurable rebalance schedule (default every 5 calendar days — approximately weekly). The strategy is entirely driven by fundamentals data from SEC EDGAR filings and data provider APIs; it does not use price patterns or technical indicators.',
      },
    ],
    parameters: [
      { label: 'P/E Weight', value: '40%', note: 'Earnings yield' },
      { label: 'P/B Weight', value: '30%', note: 'Asset discount' },
      { label: 'EV/EBITDA Weight', value: '30%', note: 'Operating value' },
      { label: 'Top Quintile', value: '20%', note: 'Buy universe cutoff' },
      { label: 'Rebalance', value: '5 days', note: 'Minimum weekly' },
      { label: 'Min Hold', value: '5 days', note: 'PDT rule compliance' },
    ],
    bestFor:
      'Long investment horizons where fundamental mispricing has time to correct. Works best during value-rotation regimes and when market breadth is wide enough to produce meaningful cross-sectional dispersion in valuations.',
    risks:
      'Value stocks can stay cheap for years — the "value trap" risk is real. The strategy is blind to business quality, debt levels, and growth prospects beyond what the three ratios capture. Fundamentals data can be stale (quarterly filings) and ratios can be distorted by one-time accounting items.',
    references: [
      {
        label: 'Fama & French (1992) — The Cross-Section of Expected Stock Returns',
        url: 'https://doi.org/10.1111/j.1540-6261.1992.tb04398.x',
      },
    ],
  },
};
