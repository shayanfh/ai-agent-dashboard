import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal
from app.modules.calls.models import Call, CallDirection, CallStatus
from app.modules.outbound_campaigns.models import (
    CampaignStatus,
    OutboundAttempt,
    OutboundCampaign,
    OutboundRecipient,
    RecipientStatus,
)
from app.modules.phone_connections.providers import AsteriskProvisionerClient
from app.modules.phone_numbers.models import PhoneNumber
from app.workers.async_utils import run_async
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.outbound_tasks.dispatch_due_campaigns")
def dispatch_due_campaigns() -> None:
    run_async(_dispatch_due)


async def _dispatch_due() -> None:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        scheduled_ids = list(
            await db.scalars(
                select(OutboundCampaign.id).where(
                    OutboundCampaign.status == CampaignStatus.SCHEDULED,
                    OutboundCampaign.scheduled_at <= now,
                )
            )
        )
        if scheduled_ids:
            await db.execute(
                OutboundCampaign.__table__.update()
                .where(OutboundCampaign.id.in_(scheduled_ids))
                .values(status=CampaignStatus.RUNNING)
            )
            await db.commit()
        campaign_ids = list(
            await db.scalars(
                select(OutboundCampaign.id).where(
                    OutboundCampaign.status == CampaignStatus.RUNNING
                )
            )
        )
    for campaign_id in campaign_ids:
        dispatch_campaign.delay(str(campaign_id))


@celery_app.task(name="app.workers.outbound_tasks.dispatch_campaign")
def dispatch_campaign(campaign_id: str) -> None:
    parsed_id = uuid.UUID(campaign_id)
    run_async(lambda: _dispatch_campaign(parsed_id))


async def _dispatch_campaign(campaign_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        campaign = await db.get(OutboundCampaign, campaign_id)
        if not campaign or campaign.status != CampaignStatus.RUNNING:
            return
        from app.core.config import settings

        active_states = [
            RecipientStatus.QUEUED,
            RecipientStatus.DIALING,
            RecipientStatus.RINGING,
            RecipientStatus.ANSWERED,
        ]
        campaign_active = int(
            await db.scalar(
                select(func.count(OutboundRecipient.id)).where(
                    OutboundRecipient.campaign_id == campaign.id,
                    OutboundRecipient.status.in_(active_states),
                )
            )
            or 0
        )
        company_active = int(
            await db.scalar(
                select(func.count(OutboundRecipient.id)).where(
                    OutboundRecipient.company_id == campaign.company_id,
                    OutboundRecipient.status.in_(active_states),
                )
            )
            or 0
        )
        slots = min(
            max(campaign.max_concurrency - campaign_active, 0),
            max(settings.OUTBOUND_MAX_CONCURRENCY_PER_COMPANY - company_active, 0),
        )
        if not slots:
            return
        from app.modules.billing.models import Plan, Subscription, SubscriptionStatus

        subscription_row = (
            await db.execute(
                select(Subscription, Plan)
                .join(Plan, Plan.id == Subscription.plan_id)
                .where(Subscription.company_id == campaign.company_id)
            )
        ).one_or_none()
        if subscription_row:
            subscription, plan = subscription_row
            if subscription.status not in {
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.TRIAL,
            }:
                campaign.status = CampaignStatus.PAUSED
                await db.commit()
                return
            if plan.monthly_minutes is not None:
                used_seconds = int(
                    await db.scalar(
                        select(func.coalesce(func.sum(Call.duration_seconds), 0)).where(
                            Call.company_id == campaign.company_id,
                            Call.started_at >= subscription.current_period_start,
                            Call.started_at < subscription.current_period_end,
                        )
                    )
                    or 0
                )
                if used_seconds >= plan.monthly_minutes * 60:
                    campaign.status = CampaignStatus.PAUSED
                    campaign.settings = {
                        **(campaign.settings or {}),
                        "pause_reason": "monthly_minutes_exhausted",
                    }
                    await db.commit()
                    return
        now = datetime.now(timezone.utc)
        candidates = list(
            await db.scalars(
                select(OutboundRecipient)
                .where(
                    OutboundRecipient.campaign_id == campaign.id,
                    OutboundRecipient.status == RecipientStatus.PENDING,
                    (
                        OutboundRecipient.next_attempt_at.is_(None)
                        | (OutboundRecipient.next_attempt_at <= now)
                    ),
                )
                .order_by(OutboundRecipient.created_at)
                .with_for_update(skip_locked=True)
                .limit(max(slots * 5, slots))
            )
        )
        recipients: list[OutboundRecipient] = []
        for recipient in candidates:
            try:
                local_now = now.astimezone(
                    ZoneInfo(recipient.timezone or campaign.timezone)
                )
            except ZoneInfoNotFoundError:
                recipient.status = RecipientStatus.FAILED
                recipient.last_error = "Unknown recipient timezone"
                continue
            if (
                campaign.calling_window_start
                <= local_now.time().replace(tzinfo=None)
                < campaign.calling_window_end
            ):
                recipients.append(recipient)
                if len(recipients) == slots:
                    break
            else:
                next_local = local_now.replace(
                    hour=campaign.calling_window_start.hour,
                    minute=campaign.calling_window_start.minute,
                    second=0,
                    microsecond=0,
                )
                if local_now.time().replace(tzinfo=None) >= campaign.calling_window_end:
                    next_local += timedelta(days=1)
                recipient.next_attempt_at = next_local.astimezone(timezone.utc)
        phone = await db.get(PhoneNumber, campaign.phone_number_id)
        if not phone or not phone.connection_id:
            campaign.status = CampaignStatus.FAILED
            await db.commit()
            return
        jobs: list[tuple[OutboundRecipient, OutboundAttempt, Call]] = []
        for recipient in recipients:
            recipient.attempts_count += 1
            recipient.status = RecipientStatus.QUEUED
            attempt = OutboundAttempt(
                id=uuid.uuid4(),
                campaign_id=campaign.id,
                recipient_id=recipient.id,
                company_id=campaign.company_id,
                attempt_number=recipient.attempts_count,
                status=RecipientStatus.QUEUED,
            )
            call = Call(
                company_id=campaign.company_id,
                agent_id=campaign.agent_id,
                phone_number_id=campaign.phone_number_id,
                campaign_id=campaign.id,
                recipient_id=recipient.id,
                direction=CallDirection.OUTBOUND,
                caller_number=phone.phone_number,
                destination_number=recipient.phone_number,
                status=CallStatus.INITIATED,
                started_at=now,
                metadata_={
                    "outbound_campaign_id": str(campaign.id),
                    "outbound_recipient_id": str(recipient.id),
                    "asterisk_linked_id": str(attempt.id),
                },
            )
            db.add_all([attempt, call])
            await db.flush()
            attempt.call_id = call.id
            recipient.last_call_id = call.id
            jobs.append((recipient, attempt, call))
        await db.commit()
        client = AsteriskProvisionerClient()
        for recipient, attempt, call in jobs:
            try:
                response = await client.originate_outbound(
                    {
                        "attempt_id": str(attempt.id),
                        "connection_id": str(phone.connection_id),
                        "campaign_type": campaign.campaign_type.value,
                        "destination_number": recipient.phone_number,
                        "caller_id": phone.phone_number,
                        "ring_timeout_seconds": campaign.ring_timeout_seconds,
                        "media_id": campaign.audio_media_id,
                        "company_id": str(campaign.company_id),
                        "agent_id": str(campaign.agent_id)
                        if campaign.agent_id
                        else None,
                        "campaign_id": str(campaign.id),
                        "recipient_id": str(recipient.id),
                        "call_id": str(call.id),
                        "keypad_actions": campaign.keypad_actions,
                    }
                )
                recipient.status = RecipientStatus.DIALING
                attempt.status = RecipientStatus.DIALING
                attempt.provider_call_id = response.get("provider_call_id")
                attempt.started_at = datetime.now(timezone.utc)
                call.livekit_room_name = response.get("room_name")
            except Exception as exc:  # noqa: BLE001 - provider failures are retryable
                recipient.status = (
                    RecipientStatus.PENDING
                    if recipient.attempts_count < campaign.max_attempts
                    else RecipientStatus.FAILED
                )
                if recipient.status == RecipientStatus.PENDING:
                    recipient.next_attempt_at = datetime.now(timezone.utc) + timedelta(
                        minutes=campaign.retry_delay_minutes
                    )
                recipient.last_error = str(exc)[:500]
                attempt.status = RecipientStatus.FAILED
                attempt.failure_reason = str(exc)[:500]
                call.status = CallStatus.FAILED
                call.ended_at = datetime.now(timezone.utc)
            await db.commit()
