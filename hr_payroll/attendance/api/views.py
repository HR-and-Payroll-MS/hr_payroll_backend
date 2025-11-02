from django.utils.dateparse import parse_datetime
from django.utils.dateparse import parse_duration
from rest_framework import mixins
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from hr_payroll.attendance.api.serializers import AttendanceAdjustmentSerializer
from hr_payroll.attendance.api.serializers import AttendanceSerializer
from hr_payroll.attendance.models import Attendance
from hr_payroll.attendance.models import AttendanceAdjustment
from hr_payroll.users.api.permissions import IsManagerOrAdmin


class AttendanceViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    """ViewSet for attendance records.

    Endpoints:
    - list/create/update/destroy attendance
    - POST /{pk}/clock-out/ to set clock_out
    - POST /{pk}/adjust-paid-time/ to adjust paid_time (creates an adjustment record)
    """

    queryset = Attendance.objects.select_related("employee").all()
    serializer_class = AttendanceSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        # Allow Manager/Admin to approve/adjust; others limited by default perms
        if self.request and self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return [IsAuthenticated()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        employee = self.kwargs.get("employee_id") or self.request.query_params.get(
            "employee"
        )
        date = self.request.query_params.get("date")
        if employee:
            qs = qs.filter(employee_id=employee)
        if date:
            qs = qs.filter(date=date)
        return qs

    @action(detail=True, methods=["post"], url_path="clock-out")
    def clock_out(self, request, pk=None):
        """Set clock_out time and optional location."""
        inst = self.get_object()
        clock_out = request.data.get("clock_out")
        clock_out_location = request.data.get("clock_out_location")
        if not clock_out:
            return Response(
                {"clock_out": "required"}, status=status.HTTP_400_BAD_REQUEST
            )
        dt = parse_datetime(clock_out) if isinstance(clock_out, str) else clock_out
        if dt is None:
            return Response(
                {"clock_out": "invalid datetime"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        inst.clock_out = dt
        if clock_out_location:
            inst.clock_out_location = clock_out_location
        inst.save(update_fields=["clock_out", "clock_out_location", "updated_at"])
        serializer = self.get_serializer(inst)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["post"],
        url_path="adjust-paid-time",
        permission_classes=[IsAuthenticated, IsManagerOrAdmin],
    )
    def adjust_paid_time(self, request, pk=None):
        """Adjust paid_time and create an adjustment audit record."""
        inst = self.get_object()
        new_paid = request.data.get("paid_time")
        notes = request.data.get("notes", "")
        if new_paid is None:
            return Response(
                {"paid_time": "required"}, status=status.HTTP_400_BAD_REQUEST
            )
        if isinstance(new_paid, str):
            dur = parse_duration(new_paid)
            if dur is None:
                return Response(
                    {"paid_time": "invalid duration"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            new_paid = dur
        # keep previous
        prev = inst.paid_time
        inst.paid_time = new_paid
        inst.save(update_fields=["paid_time", "updated_at"])
        adj = AttendanceAdjustment.objects.create(
            attendance=inst,
            performed_by=request.user if request.user.is_authenticated else None,
            previous_paid_time=prev,
            new_paid_time=new_paid,
            notes=notes,
        )
        ser = AttendanceAdjustmentSerializer(adj)
        return Response(ser.data, status=status.HTTP_201_CREATED)
