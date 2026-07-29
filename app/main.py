import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.logging import setup_logging

setup_logging(debug=settings.DEBUG)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} in {settings.APP_ENV} mode")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    description="Multi-tenant AI Telephone Agent Management Backend",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    detail = exc.detail
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": detail},
    )


@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.APP_NAME}


# Routers will be registered here as modules are built
from app.modules.auth.router import router as auth_router
from app.modules.companies.router import router as companies_router
from app.modules.users.router import router as users_router
from app.modules.agents.router import router as agents_router
from app.modules.phone_numbers.router import router as phone_numbers_router
from app.modules.calls.router import router as calls_router
from app.modules.requests.router import router as requests_router
from app.modules.knowledge_base.router import router as kb_router
from app.modules.integrations.router import router as integrations_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.dashboard.internal_router import router as internal_router
from app.modules.onboarding.router import router as onboarding_router

prefix = settings.API_V1_PREFIX
app.include_router(auth_router, prefix=f"{prefix}/auth", tags=["Authentication"])
app.include_router(companies_router, prefix=f"{prefix}/companies", tags=["Companies"])
app.include_router(users_router, prefix=f"{prefix}/users", tags=["Users"])
app.include_router(agents_router, prefix=f"{prefix}/agents", tags=["Agents"])
app.include_router(phone_numbers_router, prefix=f"{prefix}/phone-numbers", tags=["Phone Numbers"])
app.include_router(calls_router, prefix=f"{prefix}/calls", tags=["Calls"])
app.include_router(requests_router, prefix=f"{prefix}/requests", tags=["Requests"])
app.include_router(kb_router, prefix=f"{prefix}/knowledge-base", tags=["Knowledge Base"])
app.include_router(integrations_router, prefix=f"{prefix}/integrations", tags=["Integrations"])
app.include_router(dashboard_router, prefix=f"{prefix}/dashboard", tags=["Dashboard"])
app.include_router(internal_router, prefix=f"{prefix}/internal", tags=["Internal Voice Agent API"])
app.include_router(onboarding_router, prefix=f"{prefix}/onboarding", tags=["Onboarding"])
