from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path("ws/notifications/", consumers.NotificationConsumer.as_asgi()),
    path("ws/dispatch/", consumers.DispatchConsumer.as_asgi()),
    path("ws/trips/<uuid:trip_id>/track/", consumers.TripTrackingConsumer.as_asgi()),
]
