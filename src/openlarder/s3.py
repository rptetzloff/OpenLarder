"""Putting a file in S3-compatible object storage (Cloudflare R2, MinIO,
AWS), for the data dumps. AWS Signature Version 4 by hand: one request
kind, small enough not to bring in the AWS SDK. Path-style addresses
(endpoint/bucket/key), which R2 and MinIO both take.
"""

import hashlib
import hmac
from datetime import UTC, datetime
from urllib.parse import quote, urlsplit

import httpx2


class UploadFailed(RuntimeError):
    pass


def _hmac(key: bytes, text: str) -> bytes:
    return hmac.new(key, text.encode(), hashlib.sha256).digest()


def signed_headers(
    method: str,
    url: str,
    body: bytes,
    access_key: str,
    secret_key: str,
    region: str,
    now: datetime | None = None,
) -> dict[str, str]:
    """The headers that make the request a signed one (SigV4, service s3)."""
    now = now or datetime.now(UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    day = amz_date[:8]
    parts = urlsplit(url)
    payload = hashlib.sha256(body).hexdigest()
    canonical_headers = (
        f"host:{parts.netloc}\nx-amz-content-sha256:{payload}\nx-amz-date:{amz_date}\n"
    )
    signed = "host;x-amz-content-sha256;x-amz-date"
    canonical = "\n".join(
        [
            method,
            quote(parts.path or "/", safe="/-_.~"),
            parts.query,
            canonical_headers,
            signed,
            payload,
        ]
    )
    scope = f"{day}/{region}/s3/aws4_request"
    to_sign = "\n".join(
        ["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()]
    )
    key = _hmac(("AWS4" + secret_key).encode(), day)
    for part in (region, "s3", "aws4_request"):
        key = _hmac(key, part)
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    return {
        "x-amz-date": amz_date,
        "x-amz-content-sha256": payload,
        "Authorization": (
            f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
            f"SignedHeaders={signed}, Signature={signature}"
        ),
    }


async def put(
    endpoint: str,
    bucket: str,
    key: str,
    body: bytes,
    content_type: str,
    access_key: str,
    secret_key: str,
    region: str = "auto",
    transport: httpx2.AsyncBaseTransport | None = None,
) -> None:
    url = f"{endpoint.rstrip('/')}/{bucket}/{key}"
    headers = signed_headers("PUT", url, body, access_key, secret_key, region)
    headers["Content-Type"] = content_type
    async with httpx2.AsyncClient(transport=transport, timeout=120) as client:
        response = await client.put(url, content=body, headers=headers)
    if response.status_code >= 300:
        raise UploadFailed(f"{response.status_code} from the store: {response.text[:300]}")
