"""Shared helpers for M5.14 identity tests.

Generates EPHEMERAL RS256 key pairs inside the test process - the private
key never touches git, code, event_log or trace.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

KID = "test-key-1"
ISSUER = "https://staging.clerk.accounts.dev"
AUDIENCE = "nuotao-staging"


def make_key_pair(kid: str = KID) -> tuple[str, dict]:
    """Return (private_pem, public_jwk) for one ephemeral RS256 key."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("utf-8")
    public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    public_jwk["kid"] = kid
    public_jwk["alg"] = "RS256"
    public_jwk["use"] = "sig"
    return private_pem, public_jwk


def public_key_pem(private_pem: str) -> str:
    """Derive the PEM public key from a private PEM (for from_keys clients)."""
    from cryptography.hazmat.primitives import serialization as ser

    key = serialization.load_pem_private_key(private_pem.encode(), password=None)
    return (
        key.public_key()
        .public_bytes(ser.Encoding.PEM, ser.PublicFormat.SubjectPublicKeyInfo)
        .decode("utf-8")
    )


def mint_token(
    *,
    private_pem: str,
    kid: str = KID,
    sub: str = "user_2abc123",
    org: str = "org_2abc123",
    email: str | None = "ops@nuotao.example",
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    exp_delta: timedelta | None = timedelta(minutes=5),
    nbf_delta: timedelta | None = None,
    extra: dict | None = None,
    clerk_v2: bool = False,
    org_role: str = "admin",
) -> str:
    """Mint an RS256 JWT signed with the ephemeral private key.

    ``clerk_v2=True`` mimics a real Clerk v2 session token: the compact
    ``o`` claim carries ``{id, rol}`` and no ``aud`` claim is emitted (Clerk
    v2 leaves the audience implicit in the issuer).
    """
    now = datetime.now(UTC)
    if clerk_v2:
        claims: dict = {
            "sub": sub,
            "o": {"id": org, "rol": org_role},
            "iss": issuer,
            "iat": now,
            "exp": now + exp_delta if exp_delta is not None else now - timedelta(hours=1),
        }
    else:
        claims = {
            "sub": sub,
            "org": org,
            "iss": issuer,
            "aud": audience,
            "iat": now,
            "exp": now + exp_delta if exp_delta is not None else now - timedelta(hours=1),
        }
    if nbf_delta is not None:
        claims["nbf"] = now + nbf_delta
    if email is not None:
        claims["email"] = email
    if extra:
        claims.update(extra)
    return jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": kid})


def jwks_payload(*jwks: dict) -> dict:
    """Wrap JWK dicts in the standard JWKS response shape."""
    return {"keys": list(jwks)}
