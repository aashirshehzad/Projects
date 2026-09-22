# Dashboard

`GET /` serves `app/static/index.html` verbatim (via `FileResponse`) — one
build-step-free page: inline CSS/JS, TradingView **lightweight-charts** (v4) from a
CDN, Inter + JetBrains Mono from Google Fonts, company logos by ticker from
Financial Modeling Prep's public image CDN. No bundler; edit the HTML and reload.

## Layout

A three-panel "terminal" grid under a fixed header, above a fixed footer:

- **Left — watchlist.** Market-snapshot rows (`^GSPC` / `^IXIC` / `^DJI` via
  `/api/quote`), then the watchlist: per row a logo chip, up/down dot, symbol and
  live % change. Search box adds/jumps to a ticker. "Run full analysis" POSTs the
  whole watchlist to `/analyze`; while it runs the button shows a time-based
  percentage.
- **Center — chart workspace.** A ticker header (logo, company name,
  sector/industry tags, price, market cap, volume, 52W range, ATR-14, Add-to-
  Watchlist + Generate-Report buttons), a toolbar (timeframe segmented control,
  an "Indicators" dropdown, fullscreen + PNG-export icons), the candlestick +
  volume pane, a "Technical Indicators" card grid, and a Recent-Headlines /
  Catalyst-Timeline row.
- **Right — Agent 3.** Recommendation + confidence badges, Executive-Thesis /
  Key-Insights tabs, the probabilistic scenario matrix (with an investment-impact
  column), key risks, cross-cutting risks, and collapsible critic notes /
  fundamental report. While a run is in flight this panel shows a big percentage.

## Charts (`buildCandleCharts`)

One lightweight-charts pane: candlesticks + a volume histogram overlay, with
MA-50 / MA-200 / EMA-9 / EMA-20 / Bollinger line overlays toggled from the
Indicators dropdown, and an absolutely-positioned Fair-Value-Gap rectangle
overlay (`SMC / FVG` toggle) repositioned on pan/zoom/resize. Mouse wheel and
trackpad pinch both zoom. `lwCharts[]` tracks every chart (main pane, the
compact mini-charts, and any open modal chart) for teardown in `destroyCharts()`.

RSI, MACD, Stochastic and ATR are **not** overlays — each is a compact card in
the "Technical Indicators" grid with its own mini-chart (`buildMiniLineChart` /
`buildMiniMacdChart` / `buildMiniStochChart`), an expand-to-modal button
(`openIndicatorModal`), and a "Show AI Insight" toggle. Every indicator's AI
insight (dropdown pills and the RSI/MACD/Stoch/ATR cards) routes through the same
`createInsightController` grid and `/api/analyze-indicator`.

## Persistence

`localStorage` key `stock-terminal:v1` holds the watchlist, the active
ticker/timeframe, and the last Agent 3 run (`decision` + `fundamental` + `news` +
`ranAt`) so a reload restores the report and the footer timestamp. Per-ticker
price history is **not** persisted — it re-fetches per ticker on selection. All
storage access is wrapped in try/catch so a private window just gets defaults.
