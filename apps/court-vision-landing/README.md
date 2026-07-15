# Project Court Vision -- Intelligence Terminal

React + Vite frontend for CourtVision. A three-panel dashboard (AI Chat
Console, Betting Models, Analytics) that talks to the FastAPI backend for
NBA predictions and betting intelligence. See `index.html` for the app
title/shell and `src/App.jsx` for the three tabs.

- **AI Chat Console** (`AIChat` in `src/App.jsx`) -- chat query box wired to
  `POST /chat` (`chatQuery` in `src/api.js`), plus a telemetry sidebar backed
  by `getDashboardOverview()` (`GET /stitch/dashboard/overview`).
- **Betting Models** (`BettingModels`) -- today's game cards from
  `getTodayGames()` (`GET /predictions/today`).
- **Analytics** (`AnalyticsDash`) -- CLV summary from `getCLVSummary()`
  (`GET /analytics/clv-summary`).

All three panels fall back to mocked/sample data in `src/App.jsx` when the
backend is unreachable, so the UI stays usable in dev without the API
running (see `SystemStatus` in `src/App.jsx` and the `safeFetch` fallback in
`src/api.js`). Displayed edge/ROI/PnL figures on those fallback and demo
views are illustrative UI sample data, not live results -- see
`docs/JOB_EVIDENCE_PACKET.md` for what's actually verified.

## Dev

Standard Vite + React setup:

```
npm install
npm run dev
```

Set `VITE_API_URL` to point at a non-default FastAPI backend (defaults to
`http://localhost:8000`, see `API_BASE` in `src/api.js`).

## Expanding the ESLint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and [`typescript-eslint`](https://typescript-eslint.io) in your project.
