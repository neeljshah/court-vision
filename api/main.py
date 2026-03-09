from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.models_router import router as models_router
from api.analytics_router import router as analytics_router

app = FastAPI(title="NBA AI System", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(models_router, prefix="/predictions", tags=["predictions"])
app.include_router(analytics_router, prefix="/analytics", tags=["analytics"])


@app.get("/health", tags=["health"])
def health():
    """Liveness check."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
