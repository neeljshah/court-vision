# API Module Guide

The `api` package is the serving boundary for CourtVision predictions and analytics.

## Entry Point

- `main.py`: creates FastAPI app, middleware, and router mounting

## Routers

- `models_router.py`: model-specific prediction endpoints
- `predictions_router.py`: extended prediction endpoints and orchestrated game outputs
- `analytics_router.py`: analytics endpoints
- `dashboard_router.py`: dashboard/chat helper endpoints
- `stitch_router.py`: stitch integration endpoints and websocket surface

## Conventions

- Keep request/response contracts stable and explicit.
- Add tests when endpoint parameters or response keys change.
- Avoid duplicating endpoint logic between routers; prefer shared service functions in `src/` where possible.
