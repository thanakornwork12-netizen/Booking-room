# room_booking/asgi.py
# แทนที่ไฟล์เดิมทั้งหมด

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'room_booking.settings')

django_asgi_app = get_asgi_application()

from booking.routing import websocket_urlpatterns


class JWTAuthMiddleware(BaseMiddleware):
    """
    Middleware ตรวจสอบ JWT Token สำหรับ WebSocket
    Client ส่ง Token มาใน query string: ws://.../?token=eyJhbGci...
    """
    async def __call__(self, scope, receive, send):
        from urllib.parse import parse_qs
        from django.contrib.auth.models import AnonymousUser

        query_string = scope.get('query_string', b'').decode()
        params       = parse_qs(query_string)
        token_list   = params.get('token', [])

        if token_list:
            token = token_list[0]
            user  = await self.get_user_from_token(token)
            scope['user'] = user
        else:
            scope['user'] = AnonymousUser()

        return await super().__call__(scope, receive, send)

    @database_sync_to_async
    def get_user_from_token(self, token):
        try:
            from rest_framework_simplejwt.tokens import AccessToken
            from booking.models import User
            access_token = AccessToken(token)
            user_id      = access_token['user_id']
            return User.objects.get(id=user_id)
        except Exception:
            from django.contrib.auth.models import AnonymousUser
            return AnonymousUser()


application = ProtocolTypeRouter({
    'http':      django_asgi_app,
    'websocket': JWTAuthMiddleware(
        URLRouter(websocket_urlpatterns)
    ),
})
