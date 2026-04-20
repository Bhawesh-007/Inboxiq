from fastapi import APIRouter
from .email import router as email_router
from .auth import router as auth_router
api_router = APIRouter()
api_router.include_router(email_router)
api_router.include_router(auth_router)

