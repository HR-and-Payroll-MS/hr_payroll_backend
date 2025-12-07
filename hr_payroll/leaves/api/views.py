from drf_spectacular.utils import extend_schema
from rest_framework import permissions
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from hr_payroll.leaves.api.serializers import BalanceHistorySerializer
from hr_payroll.leaves.api.serializers import EmployeeBalanceSerializer
from hr_payroll.leaves.api.serializers import LeavePolicySerializer
from hr_payroll.leaves.api.serializers import LeaveRequestSerializer
from hr_payroll.leaves.api.serializers import LeaveTypeSerializer
from hr_payroll.leaves.api.serializers import PublicHolidaySerializer
from hr_payroll.leaves.models import BalanceHistory
from hr_payroll.leaves.models import EmployeeBalance
from hr_payroll.leaves.models import LeavePolicy
from hr_payroll.leaves.models import LeaveRequest
from hr_payroll.leaves.models import LeaveType
from hr_payroll.leaves.models import PublicHoliday


class LeavesPlaceholderViewSet(viewsets.ViewSet):
    """
    Placeholder ViewSet to show 'leaves' in API root.
    Actual endpoints are nested under /api/v1/leaves/
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = None  # Explicitly set to avoid drf_spectacular warning

    @extend_schema(exclude=True)
    def list(self, request):
        return Response({"message": "Leaves API Root"})


class IsAdminOrManagerOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.is_superuser or request.user.is_staff
        )


class LeaveTypeViewSet(viewsets.ModelViewSet):
    queryset = LeaveType.objects.all()
    serializer_class = LeaveTypeSerializer
    permission_classes = [IsAdminOrManagerOnly]


class LeavePolicyViewSet(viewsets.ModelViewSet):
    queryset = LeavePolicy.objects.all()
    serializer_class = LeavePolicySerializer
    permission_classes = [IsAdminOrManagerOnly]


class PublicHolidayViewSet(viewsets.ModelViewSet):
    queryset = PublicHoliday.objects.all()
    serializer_class = PublicHolidaySerializer
    permission_classes = [IsAdminOrManagerOnly]


class EmployeeBalanceViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EmployeeBalanceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.is_staff:
            return EmployeeBalance.objects.all()
        if hasattr(user, "employee"):
            return EmployeeBalance.objects.filter(employee=user.employee)
        return EmployeeBalance.objects.none()


class LeaveRequestViewSet(viewsets.ModelViewSet):
    serializer_class = LeaveRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.is_staff:
            return LeaveRequest.objects.all()
        if hasattr(user, "employee"):
            return LeaveRequest.objects.filter(employee=user.employee)
        return LeaveRequest.objects.none()

    def perform_create(self, serializer):
        if hasattr(self.request.user, "employee"):
            serializer.save(employee=self.request.user.employee)
        else:
            raise ValidationError(
                {"detail": "User does not have an associated Employee profile."}
            )


class BalanceHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BalanceHistorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.is_staff:
            return BalanceHistory.objects.all()
        if hasattr(user, "employee"):
            return BalanceHistory.objects.filter(employee=user.employee)
        return BalanceHistory.objects.none()
