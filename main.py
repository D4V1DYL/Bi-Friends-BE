from fastapi import FastAPI, HTTPException,Request
from pydantic import BaseModel
from middleware import log_requests
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from config import supabase_client
from datetime import datetime
from auth import router as auth_router
# from dashboard import router as dashboard_router
# from product import router as product_router
# from superadmin import router as superadmin_router

app = FastAPI(title="Bi-Friends API")

limiter = Limiter(key_func=get_remote_address)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


app.include_router(auth_router, prefix="/auth")
# app.include_router(dashboard_router, prefix="/dashboard")


app.middleware("https")(log_requests)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health Check
@app.get("/")
@limiter.limit("50/minute")
async def root(request: Request):
    return {"message": "AI REST API is running"}



@app.get("/test-connection")
@limiter.limit("50/minute")
async def test_supabase_connection(request: Request):
    try:
        # Test Supabase connection with a simple query
        response = supabase_client.table('msuser').select("*").limit(1).execute()
        
        return {
            "status": "success",
            "message": "Connected to Supabase",
            "timestamp": datetime.now().isoformat(),
            "supabase_url": supabase_client.supabase_url,
            "is_connected": True,
            "response": response
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
                "is_connected": False
            }
        )