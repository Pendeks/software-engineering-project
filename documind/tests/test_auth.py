from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import select

import documind.auth as auth_module
from documind.api import create_app
from documind.config import Settings
from documind.database import create_database_engine, create_session_factory, initialize_schema
from documind.models import ExternalIdentity, User, Workspace, WorkspaceMember


@pytest.fixture
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def entra_settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "auth_mode": "entra",
        "entra_tenant_id": "tenant-id",
        "entra_client_id": "spa-client-id",
        "entra_api_audience": "api://documind",
        "api_token": SecretStr("local-development-token"),
        "database_url": f"sqlite:///{tmp_path / 'auth.db'}",
        "storage_path": tmp_path / "uploads",
    }
    values.update(overrides)
    return Settings(**values)


def make_token(settings: Settings, signing_key, **claim_overrides) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "iss": f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0",
        "aud": settings.entra_api_audience,
        "tid": settings.entra_tenant_id,
        "sub": "entra-user-subject",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    claims.update(claim_overrides)
    return jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": "test-key"})


def use_test_signing_key(monkeypatch, signing_key) -> None:
    monkeypatch.setattr(
        auth_module,
        "_jwks_client",
        lambda _tenant_id: SimpleNamespace(
            get_signing_key_from_jwt=lambda _token: SimpleNamespace(
                key=signing_key.public_key()
            )
        ),
    )


def test_entra_mode_requires_tenant_client_and_audience():
    with pytest.raises(ValidationError):
        Settings(auth_mode="entra")


@pytest.mark.parametrize(
    "missing_setting",
    ["entra_tenant_id", "entra_client_id", "entra_api_audience"],
)
def test_entra_mode_requires_each_identity_setting(tmp_path: Path, missing_setting: str):
    with pytest.raises(ValidationError):
        entra_settings(tmp_path, **{missing_setting: " "})


def test_entra_mode_rejects_local_token_without_access_token(tmp_path: Path):
    settings = entra_settings(tmp_path)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/workspaces",
            headers={"Authorization": "Bearer local-development-token"},
        )

    assert response.status_code == 401


def test_entra_mode_rejects_anonymous_private_mutations(tmp_path: Path):
    app = create_app(settings=entra_settings(tmp_path))

    with TestClient(app) as client:
        response = client.post("/api/v1/workspaces", json={"name": "Private"})

    assert response.status_code == 401


def test_entra_token_rejects_invalid_signature(
    tmp_path: Path, signing_key, monkeypatch
):
    settings = entra_settings(tmp_path)
    wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    use_test_signing_key(monkeypatch, signing_key)
    token = make_token(settings, wrong_key)

    with pytest.raises(auth_module.InvalidAccessToken):
        auth_module.verify_entra_access_token(token, settings)


@pytest.mark.parametrize(
    "claim_overrides",
    [
        {"tid": "another-tenant"},
        {"iss": "https://login.microsoftonline.com/another-tenant/v2.0"},
        {"aud": "api://another-service"},
        {"exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
    ],
)
def test_entra_token_rejects_wrong_tenant_issuer_audience_or_expiry(
    tmp_path: Path, signing_key, monkeypatch, claim_overrides: dict[str, object]
):
    settings = entra_settings(tmp_path)
    use_test_signing_key(monkeypatch, signing_key)
    token = make_token(settings, signing_key, **claim_overrides)

    with pytest.raises(auth_module.InvalidAccessToken):
        auth_module.verify_entra_access_token(token, settings)


def test_entra_access_token_rejects_unknown_signing_key(tmp_path: Path, signing_key, monkeypatch):
    from jwt.exceptions import PyJWKClientError

    settings = entra_settings(tmp_path)
    monkeypatch.setattr(
        auth_module,
        "_jwks_client",
        lambda _tenant_id: SimpleNamespace(
            get_signing_key_from_jwt=lambda _token: (_ for _ in ()).throw(
                PyJWKClientError("unknown key")
            )
        ),
    )

    with pytest.raises(auth_module.InvalidAccessToken):
        auth_module.verify_entra_access_token(make_token(settings, signing_key), settings)


def test_entra_access_token_returns_verified_issuer_and_subject(
    tmp_path: Path, signing_key, monkeypatch
):
    settings = entra_settings(tmp_path)
    use_test_signing_key(monkeypatch, signing_key)

    issuer, subject = auth_module.verify_entra_access_token(
        make_token(settings, signing_key), settings
    )

    assert issuer == "https://login.microsoftonline.com/tenant-id/v2.0"
    assert subject == "entra-user-subject"


def test_entra_token_maps_same_issuer_subject_to_same_user(tmp_path: Path):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'identity.db'}")
    initialize_schema(engine)
    factory = create_session_factory(engine)

    try:
        with factory() as session:
            first = auth_module.get_or_create_external_user(
                session, "https://issuer.example/tenant", "stable-subject"
            )
            second = auth_module.get_or_create_external_user(
                session, "https://issuer.example/tenant", "stable-subject"
            )
            mapping = session.get(
                ExternalIdentity,
                ("https://issuer.example/tenant", "stable-subject"),
            )
            assert first == second
            assert mapping is not None
            assert session.get(User, first) is not None
    finally:
        engine.dispose()


def test_identity_mapping_does_not_transfer_existing_local_memberships(tmp_path: Path):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'membership.db'}")
    initialize_schema(engine)
    factory = create_session_factory(engine)

    try:
        with factory() as session:
            local_user = User(id="local-owner")
            workspace = Workspace(name="Local private workspace")
            session.add_all([local_user, workspace])
            session.flush()
            membership = WorkspaceMember(
                workspace_id=workspace.id,
                user_id=local_user.id,
                role="owner",
            )
            session.add(membership)
            session.commit()

            external_user_id = auth_module.get_or_create_external_user(
                session,
                "https://login.microsoftonline.com/tenant-id/v2.0",
                "new-entra-subject",
            )

            assert external_user_id != local_user.id
            assert session.scalar(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == workspace.id,
                    WorkspaceMember.user_id == "local-owner",
                )
            ) is not None
            assert session.scalar(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == workspace.id,
                    WorkspaceMember.user_id == external_user_id,
                )
            ) is None
    finally:
        engine.dispose()


def test_entra_identity_still_requires_workspace_membership(
    tmp_path: Path, signing_key, monkeypatch
):
    settings = entra_settings(tmp_path)
    engine = create_database_engine(settings.database_url)
    initialize_schema(engine)
    factory = create_session_factory(engine)
    with factory() as session:
        local_user = User(id="local-owner")
        workspace = Workspace(name="Local private workspace")
        session.add_all([local_user, workspace])
        session.flush()
        session.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=local_user.id,
                role="owner",
            )
        )
        session.commit()

    use_test_signing_key(monkeypatch, signing_key)
    app = create_app(settings=settings)
    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/workspaces/{workspace.id}/documents",
                headers={
                    "Authorization": f"Bearer {make_token(settings, signing_key)}"
                },
            )
    finally:
        engine.dispose()

    assert response.status_code == 404


def test_local_mode_preserves_token_authentication(tmp_path: Path):
    settings = Settings(
        auth_mode="local",
        api_token=SecretStr("local-development-token"),
        database_url=f"sqlite:///{tmp_path / 'local.db'}",
        storage_path=tmp_path / "uploads",
    )
    app = create_app(settings=settings)

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/workspaces",
            headers={"Authorization": "Bearer local-development-token"},
        )

    assert response.status_code == 200
