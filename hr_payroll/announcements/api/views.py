from django.db.models import Q
from rest_framework import mixins
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from hr_payroll.announcements.api.serializers import AnnouncementCreateSerializer
from hr_payroll.announcements.api.serializers import AnnouncementSerializer
from hr_payroll.announcements.models import Announcement
from hr_payroll.announcements.models import AnnouncementRead
from hr_payroll.employees.api.permissions import IsAdminOrManagerCanWrite
from hr_payroll.realtime.socketio import emit_event_to_all
from hr_payroll.realtime.socketio import emit_event_to_group


class AnnouncementViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    """Announcements CRUD with audience filtering and mark-read."""

    permission_classes = [IsAuthenticated]
    serializer_class = AnnouncementSerializer
    queryset = Announcement.objects.all().prefetch_related("audience_groups")

    def get_permissions(self):
        if self.action in {"create", "destroy"}:
            return [IsAuthenticated(), IsAdminOrManagerCanWrite()]
        return [perm() for perm in self.permission_classes]

    def get_queryset(self):
        qs = self.queryset
        user = getattr(self.request, "user", None)
        if not (user and getattr(user, "is_authenticated", False)):
            return qs.none()
        group_ids = list(user.groups.values_list("id", flat=True))
        if not group_ids:
            return qs.filter(audience_groups__isnull=True)
        return qs.filter(
            Q(audience_groups__isnull=True) | Q(audience_groups__in=group_ids)
        ).distinct()

    def create(self, request, *args, **kwargs):
        serializer = AnnouncementCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        announcement = serializer.save()
        out = AnnouncementSerializer(announcement, context={"request": request}).data
        # Broadcast announcement in realtime to audience rooms
        try:
            group_qs = announcement.audience_groups.all()
            group_names = [g.name for g in group_qs]
            event = "announcement.created"
            payload = out
            if group_names:
                for name in group_names:
                    emit_event_to_group(name, event, payload)
            else:
                # No audience groups: visible to all users
                emit_event_to_all(event, payload)
        except Exception:
            import logging

            logger = logging.getLogger(__name__)
            logger.exception("Failed to emit realtime announcement")

        return Response(out, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, pk=None):
        announcement = self.get_object()
        user = request.user
        AnnouncementRead.objects.get_or_create(announcement=announcement, user=user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        user = request.user
        # Fetch only visible announcements to avoid creating reads for hidden ones
        visible_ids = list(self.get_queryset().values_list("id", flat=True))
        if not visible_ids:
            return Response(status=status.HTTP_204_NO_CONTENT)
        existing = set(
            AnnouncementRead.objects.filter(
                user=user, announcement_id__in=visible_ids
            ).values_list("announcement_id", flat=True)
        )
        to_create = [
            AnnouncementRead(announcement_id=aid, user=user)
            for aid in visible_ids
            if aid not in existing
        ]
        if to_create:
            AnnouncementRead.objects.bulk_create(to_create)
        return Response(status=status.HTTP_204_NO_CONTENT)
