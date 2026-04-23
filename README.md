
# Smart Catering Agent

Backend: FastAPI multi-agent catering planner.

## Frontend (React UI)

The React UI lives in `frontend/` and calls the existing FastAPI backend.

### Prerequisites

- Node.js + npm
- Backend running locally at `http://127.0.0.1:8000`

### Configure API key

Create or edit `frontend/.env`:

```bash
REACT_APP_API_KEY=YOUR_KEY_HERE
```

This value is read at build/runtime via `process.env.REACT_APP_API_KEY` and is never hardcoded.

### Run the frontend

```bash
npm --prefix frontend install
npm --prefix frontend start
```

Open:

- `http://localhost:3000`

### How it connects to the backend

The frontend calls:

- `POST /api/v1/catering/order`

During local development, `frontend/package.json` sets a CRA `proxy` to `http://127.0.0.1:8000`, so the frontend can call the backend using a relative URL without extra CORS setup.
