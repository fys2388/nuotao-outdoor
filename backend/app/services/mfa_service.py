"""Multi-Factor Authentication (MFA) service.

Implements TOTP (Time-based One-Time Password) for two-factor authentication.
"""

import base64
import qrcode
from io import BytesIO
from typing import Optional

import pyotp

from app.core.config import get_settings


class MFAService:
    """Service for managing MFA/TOTP."""

    def __init__(self):
        self.settings = get_settings()
        # Secret key for MFA (should be stored securely)
        self.mfa_secret_key = "NUOTA0_MFA_SECRET_2024"  # Replace with env var in production

    def generate_totp_secret(self, username: str, email: str) -> dict:
        """Generate a new TOTP secret and QR code."""
        # Generate secret
        totp = pyotp.TOTP(
            secret=pyotp.random_base32(),
            digits=6,
            interval=30,
        )

        # Get provisioning URI
        provisioning_uri = totp.provisioning_uri(
            name=f"nuotao-{username}",
            issuer_name="Nuotao AI OS",
        )

        # Generate QR code
        qr_code = self._generate_qr_code(provisioning_uri)

        return {
            "secret": totp.secret,
            "provisioning_uri": provisioning_uri,
            "qr_code_base64": qr_code,
        }

    def verify_totp_code(self, secret: str, token: str) -> bool:
        """Verify a TOTP code against the secret."""
        try:
            totp = pyotp.TOTP(secret)
            return totp.verify(token, valid_window=1)  # Allow 1 time step window
        except Exception:
            return False

    def generate_totp_code(self, secret: str) -> str:
        """Generate current TOTP code for testing/backup."""
        totp = pyotp.TOTP(secret)
        return totp.now()

    def _generate_qr_code(self, uri: str) -> str:
        """Generate QR code as base64 string."""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(uri)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        # Save to bytes buffer
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        qr_string = base64.b64encode(buffered.getvalue()).decode("utf-8")

        return f"data:image/png;base64,{qr_string}"


# Singleton instance
mfa_service = MFAService()