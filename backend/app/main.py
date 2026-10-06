import os
from fastapi import FastAPI, HTTPException
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
        # Prevent intercepting /api, /docs, /openapi.json
        clean_path = full_path.strip("/")
        if clean_path.startswith("api") or clean_path.startswith("docs") or clean_path.startswith("openapi.json"):
            # Check if this endpoint exists on api_router under a different HTTP method
            normalized = clean_path[3:].lstrip("/") if clean_path.startswith("api") else ""
            for route in api_router.routes:
                route_path = getattr(route, "path", "").strip("/")
                if route_path == normalized:
                    raise HTTPException(status_code=405, detail="Method Not Allowed")
            raise HTTPException(status_code=404, detail="Resource not found")
        file_path = os.path.join(FRONTEND_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        index_file = os.path.join(FRONTEND_DIR, "index.html")
        if os.path.isfile(index_file):
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="Resource not found")
else:
    @app.get("/")
    def root():
        return {
            "message": "Hospital Shared-Account Elimination & Attribution Service is running.",
            "docs": "/docs",
            "health": "/api/health",
            "metrics": "/api/attribution/metrics"
        }
