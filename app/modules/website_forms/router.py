import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import enforce_rate_limit
from app.modules.website_forms.schemas import (
    ContactCreate,
    DemoRequestCreate,
    NewsletterCreate,
    SubmissionResponse,
)
from app.modules.website_forms.service import WebsiteFormsService
from app.modules.notifications.email.service import EmailService

router = APIRouter()


async def verify_website_api_key(authorization: str | None = Header(default=None)) -> None:
    expected = settings.WEBSITE_API_KEY
    supplied = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if not expected or not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid website API key")


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", maxsplit=1)[0].strip()
    return request.client.host if request.client else "unknown"


def _send_submission_notification(subject: str, body: str) -> None:
    if settings.WEBSITE_NOTIFICATION_EMAIL:
        EmailService().send_message(settings.WEBSITE_NOTIFICATION_EMAIL, subject, body)


@router.post(
    "/contact",
    response_model=SubmissionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_website_api_key)],
)
async def create_contact(
    data: ContactCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    await enforce_rate_limit(f"website-contact:{_client_ip(request)}", limit=10, window_seconds=3600)
    item = await WebsiteFormsService(db).create_contact(data)
    background_tasks.add_task(
        _send_submission_notification,
        "New website contact request",
        "\n".join([
            f"Name: {item.name}", f"Email: {item.email}",
            f"Company: {item.company_name}", f"Subject: {item.subject or '-'}",
            f"Message: {item.message or '-'}",
        ]),
    )
    return SubmissionResponse(id=item.id, message="Contact request received", created_at=item.created_at)


@router.post(
    "/demo-request",
    response_model=SubmissionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_website_api_key)],
)
async def create_demo_request(
    data: DemoRequestCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    await enforce_rate_limit(f"website-demo:{_client_ip(request)}", limit=10, window_seconds=3600)
    item = await WebsiteFormsService(db).create_demo_request(data)
    details = item.details or {}
    background_tasks.add_task(
        _send_submission_notification,
        "New website demo request",
        "\n".join([
            f"Name: {item.name}", f"Email: {item.email}",
            f"Company: {item.company_name}", f"Phone: {item.phone or '-'}",
            f"Monthly call volume: {details.get('monthly_call_volume') or '-'}",
            f"Industry: {details.get('industry') or '-'}",
            f"Current systems: {details.get('current_systems') or '-'}",
            f"Message: {item.message or '-'}",
        ]),
    )
    return SubmissionResponse(id=item.id, message="Demo request received", created_at=item.created_at)


@router.post(
    "/newsletter",
    response_model=SubmissionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_website_api_key)],
)
async def subscribe_newsletter(
    data: NewsletterCreate, request: Request, db: AsyncSession = Depends(get_db)
):
    if not data.marketing_consent:
        raise HTTPException(status_code=422, detail="Marketing consent is required")
    await enforce_rate_limit(f"website-newsletter:{_client_ip(request)}", limit=10, window_seconds=3600)
    item = await WebsiteFormsService(db).subscribe(data)
    return SubmissionResponse(id=item.id, message="Newsletter subscription saved", created_at=item.consented_at)
