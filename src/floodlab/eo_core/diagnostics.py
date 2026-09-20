"""Read-only remote-job diagnostics, excluding credentials and signed URLs."""

import re
from itertools import islice


def redact_message(message: str) -> str:
    """Remove common credential forms and all URLs before storing/displaying log text."""
    text = str(message)
    text = re.sub(r'(?i)\b(?:https?|s3)://[^\s<>"\']+', "[URL REDACTED]", text)
    text = re.sub(r'(?i)\bBearer\s+[^\s,"\']+', "Bearer [REDACTED]", text)
    text = re.sub(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[JWT REDACTED]", text)
    text = re.sub(
        r"""(?ix)(["']?(?:access_token|refresh_token|id_token|client_secret|password|authorization|token|api_key)["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;}]+)""",
        r"\1[REDACTED]",
        text,
    )
    return text[:4000]


def inspect_job(job) -> dict:
    """Read status and at most 20 error records; never start/restart/delete a job."""
    result = {"job_id": job.job_id, "status": job.status(), "errors": []}
    try:
        for entry in islice(job.logs(level="error"), 20):
            result["errors"].append({"message": redact_message(entry.get("message", "No message"))})
    except Exception as exc:  # noqa: BLE001 -- preserve original status if diagnostic service fails
        result["logs_unavailable"] = type(exc).__name__
    if not result["errors"]:
        result["note"] = "No error messages returned; inspect this job in the CDSE openEO editor."
    return result
