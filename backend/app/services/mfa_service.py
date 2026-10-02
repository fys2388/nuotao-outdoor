"""Multi-Factor Authentication (MFA) service.

Implements TOTP (Time-based One-Time Password) for two-factor authentication.
"""

import base64
import qrcode
import secrets
import string
from io import BytesIO
from datetime import datetime, timezone
from typing import Optional

import pyotp

from app.core.config import get_settings


class MFAService:
    """Service for managing MFA/TOTP."""

    def __init__(self):
        self.settings = get_settings()

    def generate_totp_secret(self, username: str, email: str) -> dict:
        """Generate a new TOTP secret and QR code."""
        # Generate secret
        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)
        totp.digits = 6
        totp.interval = 30

        # Get provisioning URI
        provisioning_uri = totp.provisioning_uri(
            name=f"nuotao-{username}",
            issuer_name="Nuotao AI OS",
        )

        # Generate QR code
        qr_code = self._generate_qr_code(provisioning_uri)

        # Generate backup codes
        backup_codes = self._generate_backup_codes(count=10)

        return {
            "secret": secret,
            "provisioning_uri": provisioning_uri,
            "qr_code_base64": qr_code,
            "backup_codes": backup_codes,
        }

    def verify_totp_code(self, secret: str, token: str) -> bool:
        """Verify a TOTP code against the secret."""
        try:
            totp = pyotp.TOTP(secret)
            totp.digits = 6
            totp.interval = 30
            return totp.verify(token, valid_window=1)  # Allow 1 time step window
        except Exception:
            return False

    def verify_backup_code(self, backup_codes: list, code: str) -> bool:
        """Verify a backup code."""
        if not backup_codes:
            return False
        
        # Normalize code for comparison
        normalized_code = code.upper().strip()
        
        # Check if code is in backup codes
        if normalized_code in backup_codes:
            return True
        return False

    def remove_backup_code(self, backup_codes: list, code: str) -> list:
        """Remove a used backup code and return updated list."""
        normalized_code = code.upper().strip()
        return [c for c in backup_codes if c.upper() != normalized_code]

    def generate_totp_code(self, secret: str) -> str:
        """Generate current TOTP code for testing/backup."""
        totp = pyotp.TOTP(secret)
        totp.digits = 6
        totp.interval = 30
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

    def _generate_backup_codes(self, count: int = 10) -> list:
        """Generate backup codes for emergency access."""
        codes = []
        for _ in range(count):
            # Generate code in format XXXX-XXXX
            code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
            code += '-'
            code += ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
            codes.append(code)
        return codes


# Singleton instance
mfa_service = MFAService()