"""Unit tests for application package HTTP error semantics."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1 import applications as applications_api
from app.core.exceptions import ValidationError


@pytest.mark.asyncio
async def test_prepare_package_returns_422_for_unsupported_claims(monkeypatch):
    class RejectingPackageService:
        def __init__(self, *_args, **_kwargs):
            pass

        async def build_package(self, _application_id):
            raise ValidationError(
                "Generated application package contains unsupported claims"
            )

    monkeypatch.setattr(
        applications_api,
        "get_application_service",
        lambda _session: SimpleNamespace(),
    )
    monkeypatch.setattr(
        applications_api,
        "ApplicationPackageService",
        RejectingPackageService,
    )

    with pytest.raises(HTTPException) as error:
        await applications_api.prepare_package(uuid4(), SimpleNamespace())

    assert error.value.status_code == 422
    assert "unsupported claims" in str(error.value.detail).lower()
