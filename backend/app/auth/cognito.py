from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.config import Settings, get_settings

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Identity:
    subject: str
    email: str
    display_name: str


class CognitoTokenVerifier:
    def __init__(self, settings: Settings) -> None:
        if not settings.cognito_user_pool_id or not settings.cognito_app_client_id:
            raise RuntimeError("Cognito is not configured")
        self.client_id = settings.cognito_app_client_id
        self.issuer = (
            f"https://cognito-idp.{settings.aws_region}.amazonaws.com/"
            f"{settings.cognito_user_pool_id}"
        )
        self.jwks = PyJWKClient(f"{self.issuer}/.well-known/jwks.json", cache_keys=True)

    def verify(self, token: str) -> Identity:
        try:
            signing_key = self.jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self.issuer,
                options={"require": ["exp", "iss", "sub", "token_use"]},
            )
        except (jwt.PyJWTError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired access token",
            ) from exc

        if claims.get("token_use") != "access" or claims.get("client_id") != self.client_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token was not issued for this application",
            )

        return Identity(
            subject=claims["sub"],
            email=claims.get("email", ""),
            display_name=claims.get("name") or claims.get("username") or "Coordinateur",
        )


@lru_cache
def get_token_verifier() -> CognitoTokenVerifier:
    return CognitoTokenVerifier(get_settings())


BearerCredentials = Annotated[
    HTTPAuthorizationCredentials | None,
    Depends(bearer_scheme),
]


def get_current_identity(credentials: BearerCredentials) -> Identity:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return get_token_verifier().verify(credentials.credentials)
