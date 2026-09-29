import uuid

import pytest

from app.modules.companies.models import Company
from scripts.delete_company import (
    AccountChoice,
    choose_account,
    delete_company_rows,
    storage_key_from_url,
)


def test_storage_key_from_url_only_accepts_configured_bucket() -> None:
    assert storage_key_from_url("s3://tenant-data/path/file.wav", "tenant-data") == (
        "path/file.wav"
    )
    assert storage_key_from_url("s3://other/path/file.wav", "tenant-data") is None
    assert storage_key_from_url("https://example.com/file.wav", "tenant-data") is None
    assert storage_key_from_url(None, "tenant-data") is None


def test_choose_account_accepts_number(monkeypatch) -> None:
    expected = AccountChoice(
        email="owner@example.com",
        full_name="Owner",
        role="company_admin",
        company_id=uuid.uuid4(),
        company_name="Example Co",
    )
    monkeypatch.setattr("builtins.input", lambda _: "1")

    assert choose_account([expected]) == expected


def test_choose_account_accepts_case_insensitive_email(monkeypatch) -> None:
    expected = AccountChoice(
        email="Owner@Example.com",
        full_name="Owner",
        role="company_admin",
        company_id=uuid.uuid4(),
        company_name="Example Co",
    )
    monkeypatch.setattr("builtins.input", lambda _: "owner@example.COM")

    assert choose_account([expected]) == expected


@pytest.mark.asyncio
async def test_delete_company_rows_removes_selected_company(db_session) -> None:
    company = Company(name="Disposable Company")
    db_session.add(company)
    await db_session.flush()
    company_id = company.id

    assert await delete_company_rows(db_session, company_id) is True
    assert await db_session.get(Company, company_id) is None
    assert await delete_company_rows(db_session, company_id) is False
