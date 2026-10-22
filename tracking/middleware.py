from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import CustomUser


@database_sync_to_async
def get_user_for_token(raw_token):
    try:
        token = AccessToken(raw_token)
        return CustomUser.objects.get(id=token['user_id'])
    except (TokenError, KeyError, CustomUser.DoesNotExist):
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    """Authenticate WebSocket connections with ?token=<JWT access token>.

    Browsers can't set an Authorization header on a WebSocket, so the token
    rides in the query string instead.
    """

    async def __call__(self, scope, receive, send):
        token = parse_qs(scope.get('query_string', b'').decode()).get('token')
        if token:
            scope['user'] = await get_user_for_token(token[0])
        return await super().__call__(scope, receive, send)
