import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.database import engine, Base
import app.models  # Ensure all models are registered with Base
from app.api.routes import router as api_router

# Initialize database schema
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Hospital Shared-Account Attribution Service",
    description="Cybersecurity proof of concept for accountable delegation and session attribution in hospital environments.",
    version="1.0.0"
)

# Enable CORS for local frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(api_router, prefix="/api")

# Static frontend mount
FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "frontend"
)

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    async def serve_index():
        index_file = os.path.join(FRONTEND_DIR, "index.html")
        if os.path.isfile(index_file):
            return FileResponse(index_file)
        return {"message": "Hospital Shared-Account Elimination Service is running.", "docs": "/docs"}

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # Prevent intercepting /api and /docs
        if full_path.startswith("api") or full_path.startswith("docs") or full_path.startswith("openapi.json"):
            return None
        file_path = os.path.join(FRONTEND_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        index_file = os.path.join(FRONTEND_DIR, "index.html")
        if os.path.isfile(index_file):
            return FileResponse(index_file)
        return {"message": "Resource not found"}
else:
    @app.get("/")
    def root():
        return {
            "message": "Hospital Shared-Account Elimination & Attribution Service is running.",
            "docs": "/docs",
            "health": "/api/health",
            "metrics": "/api/attribution/metrics"
        }
