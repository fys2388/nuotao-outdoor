"""Scraping job schemas (M5.16, compliance-gated)."""

from pydantic import BaseModel, Field, field_validator


class ScrapeJobRequest(BaseModel):
    """Submit a scraping job (RBAC-guarded, disabled by default).

    The submitted URLs are strictly allowlisted server-side; only public
    pages on configured domains are scraped. ``actor`` is the human operator
    submitting the job (agents can never trigger scraping).
    """

    urls: list[str] = Field(min_length=1, max_length=100)
    actor: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("urls")
    @classmethod
    def _validate_urls(cls, value: list[str]) -> list[str]:
        for url in value:
            if not isinstance(url, str) or not url.startswith(("http://", "https://")):
                raise ValueError("each url must be an http(s) URL")
        # De-duplicate while preserving order.
        seen: set[str] = set()
        out: list[str] = []
        for url in value:
            if url not in seen:
                seen.add(url)
                out.append(url)
        return out


class ScrapeJobResultOut(BaseModel):
    """Result of a scraping job."""

    requested: int
    succeeded: int
    failed: int
    product_ids: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
