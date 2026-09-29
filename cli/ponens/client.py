"""HTTP client for the hub API.

    PONENS_HUB_URL     the hub (default http://localhost:3001); WARRANT_URL is read too
    PONENS_HUB_TOKEN   your access token on it, sent as `Authorization: Bearer`; WARRANT_TOKEN is read too

A hub that requires sign-in (Imandra Warrant does, outside development) refuses a request without the
token; the token itself is never printed.
"""

import json
import os
import urllib.request
import urllib.error

DEFAULT_HUB = "http://localhost:3001"


def hub_url() -> str:
    return (os.environ.get("PONENS_HUB_URL") or os.environ.get("WARRANT_URL") or DEFAULT_HUB).rstrip("/")


def hub_token() -> str:
    return os.environ.get("PONENS_HUB_TOKEN") or os.environ.get("WARRANT_TOKEN") or ""


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
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {hub_token()}"} if hub_token() else {})},
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
        hint = ""
        if e.code == 401:
            hint = (" - the hub needs your access token: set PONENS_HUB_TOKEN" if not hub_token()
                    else " - the hub refused the token in PONENS_HUB_TOKEN (or WARRANT_TOKEN)")
        raise RuntimeError(
            f"{method} {path} -> {e.code}: "
            f"{json.dumps(detail) if isinstance(detail, (dict, list)) else detail}{hint}"
        ) from None
    except urllib.error.URLError as e:
        # connection refused / DNS / no hub running — surface as a clean error
        raise RuntimeError(f"cannot reach hub at {hub_url()}: {e.reason}") from None

    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return text
