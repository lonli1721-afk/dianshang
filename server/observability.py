from __future__ import annotations

LOCAL_OBSERVABILITY_HOSTS = {"127.0.0.1", "::1", "localhost"}


def is_local_observability_request(request) -> bool:
    client = getattr(request, "client", None)
    client_host = getattr(client, "host", "")
    if client_host not in LOCAL_OBSERVABILITY_HOSTS:
        return False
    headers = getattr(request, "headers", {}) or {}
    # This endpoint is intended for direct localhost health-report calls only.
    # Reject forwarded requests so a broad reverse-proxy rule cannot expose it.
    if headers.get("x-forwarded-for") or headers.get("x-real-ip"):
        return False
    return True
