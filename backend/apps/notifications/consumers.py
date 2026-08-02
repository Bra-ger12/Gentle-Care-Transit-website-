from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .services import DISPATCH_GROUP, trip_group, unread_count, user_group


def _is_admin(user) -> bool:
    from apps.accounts.models import Role

    return user.role == Role.ADMIN or user.is_staff


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """Per-user in-app notification stream that backs the notification bell."""

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close()
            return
        self.group = user_group(user.id)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        await self.send_json({"event": "unread_count", "unread_count": await self._unread(user)})

    async def disconnect(self, code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def notification_message(self, event):
        await self.send_json(
            {
                "event": "notification",
                "notification": event["notification"],
                "unread_count": event["unread_count"],
            }
        )

    @database_sync_to_async
    def _unread(self, user):
        return unread_count(user)


class DispatchConsumer(AsyncJsonWebsocketConsumer):
    """Admin-only live nudge for the dispatch board."""

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated or not _is_admin(user):
            await self.close()
            return
        await self.channel_layer.group_add(DISPATCH_GROUP, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(DISPATCH_GROUP, self.channel_name)

    async def dispatch_update(self, event):
        await self.send_json({"event": "dispatch_update", "payload": event["payload"]})


class TripTrackingConsumer(AsyncJsonWebsocketConsumer):
    """Live tracking for one trip. Rider (owner), assigned driver, and admins may
    watch; only the assigned driver may publish location updates."""

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close()
            return
        self.trip_id = str(self.scope["url_route"]["kwargs"]["trip_id"])
        role = await self._authorize(user, self.trip_id)
        if role is None:
            await self.close()
            return
        self.role = role  # "driver" (may publish) or "viewer"
        self.group = trip_group(self.trip_id)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        # Authorization on publish: only the assigned driver's location is relayed.
        if content.get("type") == "location" and getattr(self, "role", None) == "driver":
            lat, lng = content.get("lat"), content.get("lng")
            if lat is None or lng is None:
                return
            await self.channel_layer.group_send(
                self.group,
                {
                    "type": "trip.event",
                    "payload": {"event": "driver_location", "lat": lat, "lng": lng},
                },
            )

    async def trip_event(self, event):
        await self.send_json(event["payload"])

    @database_sync_to_async
    def _authorize(self, user, trip_id):
        from apps.trips.models import Trip

        try:
            trip = Trip.objects.select_related("rider__user", "assigned_driver__user").get(
                pk=trip_id
            )
        except Trip.DoesNotExist:
            return None
        if _is_admin(user):
            return "viewer"
        if trip.assigned_driver and trip.assigned_driver.user_id == user.id:
            return "driver"
        if trip.rider.user_id == user.id:
            return "viewer"
        return None
