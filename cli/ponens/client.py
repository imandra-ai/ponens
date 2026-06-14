"""HTTP client for the hub API."""

import json
import os
import urllib.request
import urllib.error

DEFAULT_HUB = "http://localhost:3001"


def hub_url() -> str:
    return os.environ.get("PONENS_HUB_URL", DEFAULT_HUB)


def api(method: str, path: str, body: dict | None = None) -> dict | list | str:
    """Make an API request to the hub backend.

    Returns parsed JSON (dict or list) on success.
    Raises RuntimeError on HTTP errors.
    """
    url = f"{hub_url()}/api{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            text = resp.read().decode()
    except urllib.error.HTTPError as e:
        text = e.read().decode() if e.fp else ""
        try:
            detail = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            detail = text
        raise RuntimeError(
            f"{method} {path} -> {e.code}: "
            f"{json.dumps(detail) if isinstance(detail, (dict, list)) else detail}"
        ) from None
    except urllib.error.URLError as e:
        # connection refused / DNS / no hub running — surface as a clean error
        raise RuntimeError(f"cannot reach hub at {hub_url()}: {e.reason}") from None

    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return text
