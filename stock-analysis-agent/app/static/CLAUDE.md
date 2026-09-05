# Dashboard

**Dashboard.** `GET /` serves `app/static/index.html` verbatim (via `FileResponse`) — a
single, dependency-free page (inline CSS/JS; Chart.js **and** TradingView
lightweight-charts from a CDN). It POSTs to `/analyze`
and renders, per ticker: a Buy/Sell/Hold badge, the executive thesis (paragraphs), a
dated catalyst timeline, a bull/base/bear scenario table, and downside risks — followed
by the cross-cutting risks, a 6-month returns bar chart, the metrics table, and per-ticker
charts built from `price_history`: a candlestick price pane with MA-50 / MA-200 line
overlays plus a time-synced RSI-14 sub-chart (70 / 30 dashed reference lines), with recent
headlines from `news_context`, and collapsible critic notes / fundamental report / raw
JSON. `buildCandleCharts()` owns the lightweight-charts panes; `lwCharts[]` tracks them
for teardown in `destroyCharts()` and for the window-resize handler.
No build step; edit the HTML and reload.
