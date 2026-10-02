"""Authentication audit logging.

Records authentication events (login success/failure, token refresh, etc.)
for security monitoring and compliance.
"""

import logging
from datetime import datetime
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("security.auth")


class AuthAuditMiddleware(BaseHTTPMiddleware):
    """Middleware to log authentication events."""

    async def dispatch(self, request: Request, call_next):
        # Only log auth-related endpoints
        if "/auth/" in request.url.path:
            start_time = datetime.utcnow()
            
            # Log request details
            client_ip = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown")
            
            try:
                response = await call_next(request)
                
                # Log authentication events
                if request.url.path.endswith("/login"):
                    status = response.status_code
                    if status == 200:
                        logger.info(
                            "LOGIN_SUCCESS ip=%s user_agent=%s",
                            client_ip,
                            user_agent,
                        )
                    else:
                        logger.warning(
                            "LOGIN_FAILED ip=%s status=%s user_agent=%s",
                            client_ip,
                            status,
                            user_agent,
                        )
                elif request.url.path.endswith("/refresh"):
                    status = response.status_code
                    if status == 200:
                        logger.info("TOKEN_REFRESH ip=%s", client_ip)
                    else:
                        logger.warning(
                            "TOKEN_REFRESH_FAILED ip=%s status=%s",
                            client_ip,
                            status,
                        )
                elif request.url.path.endswith("/me"):
                    status = response.status_code
                    if status == 401:
                        logger.warning("AUTH_FAILED ip=%s", client_ip)
                
                return response
                
            except Exception as e:
                logger.error(
                    "AUTH_ERROR ip=%s path=%s error=%s",
                    client_ip,
                    request.url.path,
                    str(e),
                )
                raise