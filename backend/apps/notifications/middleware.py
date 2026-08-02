"""WebSocket JWT auth.

Browsers can't set an `Authorization` header on a `WebSocket`, so the frontend
passes the short-lived access token in the query string (`?token=...`). This
middleware validates it and puts the resolved user on the connection scope; any
failure yields AnonymousUser and the consumer decides whether to reject.
"""

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken


@database_sync_to_async
def _get_user(user_id):
    User = get_user_model()
    try:
        return User.objects.get(pk=user_id, is_active=True)
    except User.DoesNotExist:
        return AnonymousUser()


async def _resolve_user(token):
    if not token:
        return AnonymousUser()
    try:
        access = AccessToken(token)  # verifies signature + expiry (no DB hit)
        user_id = access["user_id"]
    except Exception:  # noqa: BLE001 -- any token error => anonymous
        return AnonymousUser()
    return await _get_user(user_id)


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        token = (query.get("token") or [None])[0]
        scope["user"] = await _resolve_user(token)
        return await super().__call__(scope, receive, send)
