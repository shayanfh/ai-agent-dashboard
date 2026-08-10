from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import normalize_email
from app.modules.website_forms.models import NewsletterSubscriber, WebsiteSubmission
from app.modules.website_forms.schemas import ContactCreate, DemoRequestCreate, NewsletterCreate


class WebsiteFormsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_contact(self, data: ContactCreate) -> WebsiteSubmission:
        submission = WebsiteSubmission(
            kind="contact",
            name=data.name.strip(),
            email=normalize_email(str(data.email)),
            company_name=data.company_name.strip(),
            subject=data.subject,
            message=data.message,
            source=data.source,
            page_url=str(data.page_url) if data.page_url else None,
        )
        self.db.add(submission)
        await self.db.commit()
        await self.db.refresh(submission)
        return submission

    async def create_demo_request(self, data: DemoRequestCreate) -> WebsiteSubmission:
        submission = WebsiteSubmission(
            kind="demo_request",
            name=data.name.strip(),
            email=normalize_email(str(data.email)),
            company_name=data.company_name.strip(),
            phone=data.phone,
            message=data.message,
            marketing_consent=data.marketing_consent,
            details={
                "monthly_call_volume": data.monthly_call_volume,
                "industry": data.industry,
                "current_systems": data.current_systems,
            },
            source=data.source,
            page_url=str(data.page_url) if data.page_url else None,
        )
        self.db.add(submission)
        await self.db.commit()
        await self.db.refresh(submission)
        return submission

    async def subscribe(self, data: NewsletterCreate) -> NewsletterSubscriber:
        email = normalize_email(str(data.email))
        result = await self.db.execute(
            select(NewsletterSubscriber).where(NewsletterSubscriber.email == email)
        )
        subscriber = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if subscriber:
            subscriber.marketing_consent = data.marketing_consent
            subscriber.is_active = True
            subscriber.source = data.source
            subscriber.page_url = str(data.page_url) if data.page_url else None
            subscriber.consented_at = now
        else:
            subscriber = NewsletterSubscriber(
                email=email,
                marketing_consent=data.marketing_consent,
                source=data.source,
                page_url=str(data.page_url) if data.page_url else None,
                consented_at=now,
            )
            self.db.add(subscriber)
        await self.db.commit()
        await self.db.refresh(subscriber)
        return subscriber
