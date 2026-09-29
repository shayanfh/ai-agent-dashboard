"""Interactively and permanently delete a company and its local data.

Run inside Docker with::

    docker compose exec api python -m scripts.delete_company

The database deletion is transactional. PostgreSQL cascades remove tenant-owned
rows; outbound campaigns are deleted first because they contain RESTRICT foreign
keys to users and phone numbers. Object-storage files are removed after the
database transaction commits.

This script deliberately does not delete or cancel remote Stripe, Twilio,
Asterisk, or LiveKit resources. Their identifiers are shown before confirmation
so an operator can clean them up using the relevant provider workflow.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Import every model module before inspecting Base.metadata. This keeps the
# related-record report accurate as new application processes do not import all
# routers/models automatically.
import app.modules.agents.models  # noqa: F401
import app.modules.auth.models  # noqa: F401
import app.modules.billing.models  # noqa: F401
import app.modules.calls.models  # noqa: F401
import app.modules.extensions.models  # noqa: F401
import app.modules.integrations.models  # noqa: F401
import app.modules.knowledge_base.models  # noqa: F401
import app.modules.onboarding.models  # noqa: F401
import app.modules.outbound_campaigns.models  # noqa: F401
import app.modules.phone_numbers.models  # noqa: F401
import app.modules.requests.models  # noqa: F401
import app.modules.users.models  # noqa: F401

from app.core.config import settings
from app.core.database import AsyncSessionLocal, Base
from app.core.storage import get_object_storage
from app.modules.calls.models import Call
from app.modules.companies.models import Company
from app.modules.extensions.models import Extension
from app.modules.knowledge_base.models import KnowledgeDocument
from app.modules.onboarding.models import TelephonyConnection
from app.modules.outbound_campaigns.models import OutboundCampaign
from app.modules.phone_numbers.models import PhoneNumber
from app.modules.users.models import User


@dataclass(frozen=True, slots=True)
class AccountChoice:
    email: str
    full_name: str
    role: str
    company_id: uuid.UUID
    company_name: str


@dataclass(frozen=True, slots=True)
class CompanySnapshot:
    company: dict[str, Any]
    users: list[dict[str, Any]]
    related_counts: dict[str, int]
    storage_keys: list[str]
    external_resources: dict[str, list[str]]


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, (uuid.UUID, Decimal)):
        return str(value)
    return value


def _row_dict(instance: Any, *, excluded: set[str] | None = None) -> dict[str, Any]:
    excluded = excluded or set()
    return {
        column.name: _json_value(getattr(instance, column.key))
        for column in instance.__table__.columns
        if column.name not in excluded
    }


def storage_key_from_url(value: str | None, bucket: str) -> str | None:
    """Return a key only for an s3:// URL belonging to the configured bucket."""
    if not value:
        return None
    prefix = f"s3://{bucket}/"
    if value.startswith(prefix) and len(value) > len(prefix):
        return value[len(prefix) :]
    return None


async def list_company_accounts(db: AsyncSession) -> list[AccountChoice]:
    rows = (
        await db.execute(
            select(
                User.email,
                User.full_name,
                User.role,
                Company.id,
                Company.name,
            )
            .join(Company, User.company_id == Company.id)
            .order_by(User.email.asc())
        )
    ).all()
    return [
        AccountChoice(
            email=row.email,
            full_name=row.full_name,
            role=_json_value(row.role),
            company_id=row.id,
            company_name=row.name,
        )
        for row in rows
    ]


async def _related_counts(
    db: AsyncSession, company_id: uuid.UUID
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in sorted(Base.metadata.tables.values(), key=lambda item: item.name):
        if table.name == Company.__tablename__ or "company_id" not in table.c:
            continue
        count = await db.scalar(
            select(func.count()).select_from(table).where(table.c.company_id == company_id)
        )
        counts[table.name] = int(count or 0)

    # Auth tokens are owned through users and have no direct company_id column.
    auth_tokens = Base.metadata.tables.get("auth_tokens")
    users = Base.metadata.tables.get("users")
    if auth_tokens is not None and users is not None:
        count = await db.scalar(
            select(func.count())
            .select_from(auth_tokens.join(users, auth_tokens.c.user_id == users.c.id))
            .where(users.c.company_id == company_id)
        )
        counts["auth_tokens"] = int(count or 0)
    return counts


async def _storage_keys(db: AsyncSession, company_id: uuid.UUID) -> list[str]:
    keys: set[str] = set()

    document_keys = await db.scalars(
        select(KnowledgeDocument.storage_key).where(
            KnowledgeDocument.company_id == company_id,
            KnowledgeDocument.storage_key.is_not(None),
        )
    )
    keys.update(key for key in document_keys if key)

    campaign_keys = await db.scalars(
        select(OutboundCampaign.audio_storage_key).where(
            OutboundCampaign.company_id == company_id,
            OutboundCampaign.audio_storage_key.is_not(None),
        )
    )
    keys.update(key for key in campaign_keys if key)

    calls = (
        await db.execute(
            select(Call.recording_url, Call.metadata_).where(Call.company_id == company_id)
        )
    ).all()
    for recording_url, metadata in calls:
        key = storage_key_from_url(recording_url, settings.STORAGE_BUCKET)
        if key:
            keys.add(key)
        if isinstance(metadata, dict):
            object_key = (metadata.get("recording") or {}).get("object_key")
            if isinstance(object_key, str) and object_key:
                keys.add(object_key)

    company = await db.get(Company, company_id)
    if company:
        logo_key = storage_key_from_url(company.logo_url, settings.STORAGE_BUCKET)
        if logo_key:
            keys.add(logo_key)
    return sorted(keys)


async def _external_resources(
    db: AsyncSession, company: Company
) -> dict[str, list[str]]:
    resources: dict[str, list[str]] = {}

    if company.stripe_customer_id:
        resources["stripe_customer"] = [company.stripe_customer_id]

    subscriptions = Base.metadata.tables.get("subscriptions")
    if subscriptions is not None:
        stripe_subscription_ids = await db.scalars(
            select(subscriptions.c.stripe_subscription_id).where(
                subscriptions.c.company_id == company.id,
                subscriptions.c.stripe_subscription_id.is_not(None),
            )
        )
        values = [value for value in stripe_subscription_ids if value]
        if values:
            resources["stripe_subscriptions"] = values

    connections = (
        await db.scalars(
            select(TelephonyConnection).where(
                TelephonyConnection.company_id == company.id
            )
        )
    ).all()
    connection_ids = sorted(
        {
            value
            for item in connections
            for value in (
                item.livekit_trunk_id,
                item.dispatch_rule_id,
                item.external_trunk_id,
                item.asterisk_resource_id,
            )
            if value
        }
    )
    if connection_ids:
        resources["telephony"] = connection_ids

    phone_resources = (
        await db.execute(
            select(
                PhoneNumber.sip_trunk_id,
                PhoneNumber.livekit_trunk_id,
                PhoneNumber.dispatch_rule_id,
            ).where(PhoneNumber.company_id == company.id)
        )
    ).all()
    phone_ids = sorted(
        {
            value
            for row in phone_resources
            for value in row
            if value
        }
    )
    if phone_ids:
        resources["phone_numbers"] = phone_ids

    extension_ids = await db.scalars(
        select(Extension.asterisk_resource_id).where(
            Extension.company_id == company.id,
            Extension.asterisk_resource_id.is_not(None),
        )
    )
    values = sorted(value for value in extension_ids if value)
    if values:
        resources["extensions"] = values
    return resources


async def load_company_snapshot(
    db: AsyncSession, company_id: uuid.UUID
) -> CompanySnapshot | None:
    company = await db.get(Company, company_id)
    if not company:
        return None
    users = (
        await db.scalars(select(User).where(User.company_id == company_id).order_by(User.email))
    ).all()
    return CompanySnapshot(
        company=_row_dict(company),
        users=[_row_dict(user, excluded={"hashed_password"}) for user in users],
        related_counts=await _related_counts(db, company_id),
        storage_keys=await _storage_keys(db, company_id),
        external_resources=await _external_resources(db, company),
    )


def print_snapshot(snapshot: CompanySnapshot) -> None:
    print("\n=== Complete company details ===")
    print(json.dumps(snapshot.company, ensure_ascii=False, indent=2, default=str))
    print("\n=== Company users (password hashes are not displayed) ===")
    print(json.dumps(snapshot.users, ensure_ascii=False, indent=2, default=str))
    print("\n=== Related record counts ===")
    non_empty = {key: value for key, value in snapshot.related_counts.items() if value}
    print(json.dumps(non_empty, ensure_ascii=False, indent=2))
    print(f"\nObject Storage files to delete: {len(snapshot.storage_keys)}")
    if snapshot.external_resources:
        print("\n=== External resource IDs (not deleted automatically) ===")
        print(
            json.dumps(
                snapshot.external_resources, ensure_ascii=False, indent=2, default=str
            )
        )
        print(
            "Warning: Local records for these resources will be deleted, but the "
            "remote resources must be removed or cancelled through their provider."
        )


async def delete_company_rows(db: AsyncSession, company_id: uuid.UUID) -> bool:
    """Delete a company transactionally, handling known RESTRICT dependencies."""
    company = await db.scalar(
        select(Company).where(Company.id == company_id).with_for_update()
    )
    if not company:
        return False

    # These rows RESTRICT deletion of their creator and phone number. Removing
    # them first allows the company cascade to remove both referenced parents.
    await db.execute(
        delete(OutboundCampaign).where(OutboundCampaign.company_id == company_id)
    )
    await db.flush()
    await db.execute(delete(Company).where(Company.id == company_id))
    await db.commit()
    return True


async def delete_storage_objects(keys: list[str]) -> list[tuple[str, str]]:
    if not keys:
        return []
    storage = get_object_storage()
    failures: list[tuple[str, str]] = []
    for key in keys:
        try:
            await storage.delete(key=key)
        except Exception as exc:  # noqa: BLE001 - report every orphaned object
            failures.append((key, f"{type(exc).__name__}: {exc}"))
    return failures


def choose_account(accounts: list[AccountChoice]) -> AccountChoice | None:
    print("=== Company user emails ===")
    for index, item in enumerate(accounts, start=1):
        print(
            f"[{index}] {item.email} | {item.full_name} | {item.role} | "
            f"{item.company_name}"
        )
    while True:
        raw = input("\nEnter a number or email address (q to quit): ").strip()
        if raw.lower() in {"q", "quit", "exit"}:
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(accounts):
            return accounts[int(raw) - 1]
        matches = [item for item in accounts if item.email.casefold() == raw.casefold()]
        if len(matches) == 1:
            return matches[0]
        print("Invalid selection. Enter a listed number or email address.")


async def run(*, skip_storage: bool = False) -> int:
    async with AsyncSessionLocal() as db:
        accounts = await list_company_accounts(db)
        if not accounts:
            print("No email addresses linked to a company were found.")
            return 0
        selected = choose_account(accounts)
        if not selected:
            print("Operation cancelled.")
            return 0
        snapshot = await load_company_snapshot(db, selected.company_id)
        if not snapshot:
            print("The selected company no longer exists. Operation cancelled.", file=sys.stderr)
            return 1

        print_snapshot(snapshot)
        phrase = f"DELETE {selected.company_id}"
        print("\nThis action is irreversible and deletes all local company data.")
        confirmation = input(
            f"To confirm, enter the following phrase exactly:\n{phrase}\n> "
        ).strip()
        if confirmation != phrase:
            print("The confirmation phrase did not match. Nothing was deleted.")
            return 0

        try:
            deleted = await delete_company_rows(db, selected.company_id)
        except Exception:
            await db.rollback()
            print(
                "Database deletion failed and the transaction was rolled back.",
                file=sys.stderr,
            )
            raise
        if not deleted:
            print(
                "The company could not be found before deletion. Nothing was deleted.",
                file=sys.stderr,
            )
            return 1

    print(f'Company "{selected.company_name}" and its local data were deleted.')
    if skip_storage:
        print("Object Storage cleanup was skipped with --skip-storage.")
        return 0

    failures = await delete_storage_objects(snapshot.storage_keys)
    if failures:
        print(
            "\nThe database was deleted, but these files could not be removed:",
            file=sys.stderr,
        )
        for key, error in failures:
            print(f"- {key}: {error}", file=sys.stderr)
        return 2
    print(f"Deleted {len(snapshot.storage_keys)} Object Storage file(s).")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Interactively preview and permanently delete one company."
    )
    parser.add_argument(
        "--skip-storage",
        action="store_true",
        help="Delete database data but leave object-storage files untouched.",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(skip_storage=args.skip_storage)))


if __name__ == "__main__":
    main()
