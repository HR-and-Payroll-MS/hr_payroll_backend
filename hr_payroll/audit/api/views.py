from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from hr_payroll.audit.api.serializers import AuditLogSerializer
from hr_payroll.audit.models import AuditLog
from hr_payroll.employees.api.permissions import ROLE_ADMIN
from hr_payroll.employees.api.permissions import ROLE_LINE_MANAGER
from hr_payroll.employees.api.permissions import ROLE_MANAGER
from hr_payroll.employees.api.permissions import _user_in_groups

if TYPE_CHECKING:
    from django.db.models import QuerySet


class RecentAuditView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if not (
            getattr(user, "is_staff", False)
            or _user_in_groups(user, [ROLE_ADMIN, ROLE_MANAGER, ROLE_LINE_MANAGER])
        ):
            return Response({"detail": "Forbidden"}, status=403)

        try:
            limit = int(request.query_params.get("limit", "5"))
        except (TypeError, ValueError):
            limit = 5
        limit = max(1, min(limit, 50))

        qs: QuerySet[AuditLog] = AuditLog.objects.select_related("actor").all()
        rows = list(qs[:limit])
        data = AuditLogSerializer(rows, many=True).data
        return Response({"results": data, "limit": limit})
