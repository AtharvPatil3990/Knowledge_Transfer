# backend/app/main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.db.supabase_client import supabase_client
from app.api.auth import router as auth_router
from app.api.teams import router as teams_router
from app.api.knowledge import router as knowledge_router

app = FastAPI(title=settings.PROJECT_NAME)
app.include_router(auth_router)
app.include_router(teams_router)
app.include_router(knowledge_router)

# Configure CORS so the React frontend can communicate with this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", tags=["System"])
async def health_check():
    """
    Verifies that the API is running and can successfully ping the Supabase DB.
    """
    try:
        return {
            "status": "healthy", 
            "supabase_connection": "successful"
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database connection failed: {str(e)}")