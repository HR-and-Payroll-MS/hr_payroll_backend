from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema_view
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.mixins import UpdateModelMixin
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from hr_payroll.audit.utils import log_action
from hr_payroll.users.models import User

from .serializers import UserSerializer


@extend_schema_view(
    list=extend_schema(tags=["Users"]),
    retrieve=extend_schema(tags=["Users"]),
    partial_update=extend_schema(tags=["Users"]),
    update=extend_schema(tags=["Users"]),
)
class UserViewSet(RetrieveModelMixin, ListModelMixin, UpdateModelMixin, GenericViewSet):
    serializer_class = UserSerializer
    queryset = User.objects.all()
    lookup_field = "username"
    # Keep legacy API contract: return a plain list (no pagination) for /api/v1/users/
    pagination_class = None

    def get_queryset(self, *args, **kwargs):  # type: ignore[override]
        user = self.request.user
        if not getattr(user, "is_authenticated", False):  # pragma: no cover - safety
            return User.objects.none()
        # Managers/Admins may list all users; others only themselves
        is_elevated = getattr(user, "is_staff", False) or (
            getattr(user, "groups", None)
            and user.groups.filter(name__in=["Admin", "Manager"]).exists()
        )
        return User.objects.all() if is_elevated else User.objects.filter(pk=user.pk)

    @action(detail=False)
    def me(self, request):
        serializer = UserSerializer(request.user, context={"request": request})
        return Response(status=status.HTTP_200_OK, data=serializer.data)

    def perform_update(self, serializer):  # type: ignore[override]
        instance = serializer.save()
        # Log update action
        log_action(
            "user_updated",
            actor=self.request.user,
            message=f"username={instance.username}",
        )
