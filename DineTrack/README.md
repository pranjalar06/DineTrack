# DineTrack dashboard (frontend)

The React + Vite dashboard for DineTrack. For setup, sign-in details, data uploads and how the forecast works, see the [project README](../README.md).

```bash
npm install
npm run dev      # http://localhost:5173 — the backend must be running on :8000
npm run build    # production build into dist/
```

To use a backend somewhere other than `http://localhost:8000`:

```powershell
$env:VITE_API_URL="http://localhost:8000"
npm run dev
```

Everything is in [`src/App.jsx`](src/App.jsx): the sign-in page, then one component per dashboard page. Styles and the dark/light theme are in [`src/styles.css`](src/styles.css).
