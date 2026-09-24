# AI Weeks Support Agent

React (Vite + TS) support app for the SwissLife 2026 triage challenge.

```bash
python3 ../analysis/build_insights.py   # regenerate src/data/insights.json from the datasets
npm install && npm run dev
```

The **Get help** tab streams analysis progress from `POST /api/assist/stream`. Enable **Debug** before submitting to see backend tool names, timings, retrieved knowledge matches, duplicate checks, cited evidence, and final routing. The standard `POST /api/assist` endpoint remains available for clients that want one JSON response.

The analysis animation uses the LottieFiles React player and the recolored animation in [`public/animations`](public/animations/README.md).
