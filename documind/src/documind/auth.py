from functools import lru_cache
from uuid import uuid4

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError, PyJWTError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from documind.config import Settings
from documind.models import ExternalIdentity, User


class InvalidAccessToken(ValueError):
    pass


@lru_cache(maxsize=32)
def _jwks_client(tenant_id: str) -> PyJWKClient:
    return PyJWKClient(
        f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
    )


def verify_entra_access_token(token: str, settings: Settings) -> tuple[str, str]:
    tenant_id = settings.entra_tenant_id
    audience = settings.entra_api_audience
    if tenant_id is None or audience is None:
        raise RuntimeError("Entra authentication settings are incomplete.")

    issuer = f"https://login.microsoftonline.com/{tenant_id}/v2.0"
    try:
        signing_key = _jwks_client(tenant_id).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
            options={"require": ["exp", "iss", "aud", "sub", "tid"]},
        )
    except (PyJWKClientError, PyJWTError, ValueError) as error:
        raise InvalidAccessToken("Invalid access token.") from error

    subject = claims.get("sub")
    if claims.get("tid") != tenant_id or not isinstance(subject, str) or not subject:
        raise InvalidAccessToken("Invalid access token.")
    return issuer, subject


def get_or_create_external_user(session: Session, issuer: str, subject: str) -> str:
    identity = session.get(ExternalIdentity, (issuer, subject))
    if identity is not None:
        return identity.user_id

    user_id = uuid4().hex
    try:
        with session.begin_nested():
            session.add(User(id=user_id))
            session.flush()
            session.add(
                ExternalIdentity(issuer=issuer, subject=subject, user_id=user_id)
            )
            session.flush()
        session.commit()
        return user_id
    except IntegrityError:
        identity = session.scalar(
            select(ExternalIdentity).where(
                ExternalIdentity.issuer == issuer,
                ExternalIdentity.subject == subject,
            )
        )
        if identity is None:
            raise
        return identity.user_id
