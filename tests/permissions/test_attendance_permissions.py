from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from hr_payroll.attendance.models import OfficeNetwork
from tests.permissions.mixins import ROLE_EMPLOYEE
from tests.permissions.mixins import ROLE_LINE_MANAGER
from tests.permissions.mixins import ROLE_MANAGER
from tests.permissions.mixins import RoleAPITestCase


class AttendancePermissionTests(RoleAPITestCase):
    def test_employee_cannot_access_admin_attendance_list(self):
        response = self.get("api_v1:attendance-list", role=ROLE_EMPLOYEE)
        self.assert_denied(response)

    def test_manager_can_list_all_attendance_records(self):
        response = self.get("api_v1:attendance-list", role=ROLE_MANAGER)
        self.assert_http_status(response, status.HTTP_200_OK)
        employees = {row["employee"] for row in self.extract_results(response)}
        assert self.roles[ROLE_EMPLOYEE].employee.pk in employees

    def test_line_manager_only_sees_department_attendances(self):
        response = self.get("api_v1:attendance-list", role=ROLE_LINE_MANAGER)
        self.assert_http_status(response, status.HTTP_200_OK)
        employees = {row["employee"] for row in self.extract_results(response)}
        assert self.roles[ROLE_EMPLOYEE].employee.pk in employees
        assert self.others["employee"].employee.pk not in employees

    def test_line_manager_cannot_patch_team_attendance_times(self):
        team_record = self.attendance_records["team"]
        new_clock_in = (timezone.now() - timedelta(hours=9)).isoformat()
        res = self.patch(
            "api_v1:attendance-detail",
            role=ROLE_LINE_MANAGER,
            reverse_kwargs={"pk": team_record.pk},
            payload={"clock_in": new_clock_in, "clock_in_location": "HQ corrected"},
        )
        self.assert_denied(res)

    def test_line_manager_cannot_patch_other_department_attendance(self):
        other_record = self.attendance_records["other"]
        new_clock_in = (timezone.now() - timedelta(hours=9)).isoformat()
        denied = self.patch(
            "api_v1:attendance-detail",
            role=ROLE_LINE_MANAGER,
            reverse_kwargs={"pk": other_record.pk},
            payload={"clock_in": new_clock_in},
        )
        # Scoped queryset should hide it.
        assert denied.status_code in (
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        )

    def test_line_manager_cannot_delete_clock_out_to_reopen_attendance(self):
        team_record = self.attendance_records["team"]
        # Set an initial clock_out
        team_record.clock_out = timezone.now() + timedelta(hours=8)
        team_record.clock_out_location = "HQ"
        team_record.save(
            update_fields=["clock_out", "clock_out_location", "updated_at"]
        )

        res = self.delete(
            "api_v1:attendance-clock-out",
            role=ROLE_LINE_MANAGER,
            reverse_kwargs={"pk": team_record.pk},
        )
        self.assert_denied(res)

    def test_manual_entry_records_authenticated_employee(self):
        target_date = (timezone.now().date() + timedelta(days=7)).isoformat()
        target_clock_in = (timezone.now() + timedelta(days=7)).isoformat()
        payload = {
            "date": target_date,
            "clock_in": target_clock_in,
            "clock_in_location": "HQ kiosk",
        }
        employee_id = self.roles[ROLE_EMPLOYEE].employee.pk
        allowed = self.post(
            "employee-attendance-manual-entry",
            role=ROLE_EMPLOYEE,
            payload=payload,
            reverse_kwargs={"employee_id": employee_id},
        )
        self.assert_http_status(allowed, status.HTTP_201_CREATED)
        assert allowed.data["employee"] == employee_id

    def test_manual_entry_ignores_submitted_employee_id(self):
        target_date = (timezone.now().date() + timedelta(days=8)).isoformat()
        target_clock_in = (timezone.now() + timedelta(days=8)).isoformat()
        payload = {
            "employee": self.roles[ROLE_MANAGER].employee.pk,
            "date": target_date,
            "clock_in": target_clock_in,
            "clock_in_location": "HQ kiosk",
        }
        employee_id = self.roles[ROLE_EMPLOYEE].employee.pk
        allowed = self.post(
            "employee-attendance-manual-entry",
            role=ROLE_EMPLOYEE,
            payload=payload,
            reverse_kwargs={"employee_id": employee_id},
        )
        self.assert_http_status(allowed, status.HTTP_201_CREATED)
        assert allowed.data["employee"] == employee_id

    def test_clock_in_ignores_submitted_employee_id(self):
        OfficeNetwork.objects.create(
            label="Loopback", cidr="127.0.0.1/32", is_active=True
        )
        target_date = (timezone.now().date() + timedelta(days=9)).isoformat()
        target_clock_in = (timezone.now() + timedelta(days=9)).isoformat()
        payload = {
            "employee": self.roles[ROLE_MANAGER].employee.pk,
            "date": target_date,
            "clock_in": target_clock_in,
            "clock_in_location": "HQ kiosk",
        }
        employee_id = self.roles[ROLE_EMPLOYEE].employee.pk
        allowed = self.post(
            "employee-attendance-clock-in",
            role=ROLE_EMPLOYEE,
            payload=payload,
            reverse_kwargs={"employee_id": employee_id},
        )
        self.assert_http_status(allowed, status.HTTP_201_CREATED)
        assert allowed.data["employee"] == employee_id

    def test_attendance_today_returns_structure_without_records(self):
        future_date = (timezone.now().date() + timedelta(days=5)).isoformat()
        self.authenticate(ROLE_EMPLOYEE)
        url = (
            f"{reverse('employee-attendance-today', kwargs={'employee_id': self.roles[ROLE_EMPLOYEE].employee.pk})}"  # noqa: E501
            f"?date={future_date}"
        )
        response = self.client.get(url)
        self.assert_http_status(response, status.HTTP_200_OK)
        assert response.data["punches"] == []
        assert response.data["attendance_id"] is None

    def test_attendance_today_includes_existing_clock_in(self):
        self.authenticate(ROLE_EMPLOYEE)
        response = self.client.get(
            reverse(
                "employee-attendance-today",
                kwargs={"employee_id": self.roles[ROLE_EMPLOYEE].employee.pk},
            )
        )
        self.assert_http_status(response, status.HTTP_200_OK)
        assert len(response.data["punches"]) == 1
        assert response.data["punches"][0]["type"] == "check_in"

    def test_attendance_actions_endpoint_lists_available_routes(self):
        allowed = self.get(
            "employee-attendance-actions",
            role=ROLE_EMPLOYEE,
            reverse_kwargs={"employee_id": self.roles[ROLE_EMPLOYEE].employee.pk},
        )
        self.assert_http_status(allowed, status.HTTP_200_OK)
        assert any(a["name"] == "today" for a in allowed.data["actions"])

    def test_attendance_check_requires_office_network(self):
        target_date = (timezone.now().date() + timedelta(days=6)).isoformat()
        payload = {
            "action": "check_in",
            "location": "HQ kiosk",
            "date": target_date,
            "time": "08:05",
        }
        denied = self.post(
            "employee-attendance-check",
            role=ROLE_EMPLOYEE,
            payload=payload,
            reverse_kwargs={"employee_id": self.roles[ROLE_EMPLOYEE].employee.pk},
        )
        self.assert_denied(denied, code=status.HTTP_403_FORBIDDEN)

    def test_attendance_check_creates_clock_in_with_network(self):
        OfficeNetwork.objects.create(
            label="Loopback", cidr="127.0.0.1/32", is_active=True
        )
        target_date = (timezone.now().date() + timedelta(days=7)).isoformat()
        payload = {
            "action": "check_in",
            "location": "HQ kiosk",
            "date": target_date,
            "time": "08:10",
        }
        allowed = self.post(
            "employee-attendance-check",
            role=ROLE_EMPLOYEE,
            payload=payload,
            reverse_kwargs={"employee_id": self.roles[ROLE_EMPLOYEE].employee.pk},
        )
        self.assert_http_status(allowed, status.HTTP_201_CREATED)
        assert len(allowed.data["punches"]) == 1
        assert allowed.data["punches"][0]["type"] == "check_in"

    def test_attendance_check_closes_open_record(self):
        payload = {
            "action": "check_out",
            "location": "HQ kiosk",
            "timestamp": (timezone.now() + timedelta(hours=8)).isoformat(),
        }
        allowed = self.post(
            "employee-attendance-check",
            role=ROLE_EMPLOYEE,
            payload=payload,
            reverse_kwargs={"employee_id": self.roles[ROLE_EMPLOYEE].employee.pk},
        )
        self.assert_http_status(allowed, status.HTTP_200_OK)
        assert len(allowed.data["punches"]) == 2
        assert allowed.data["punches"][1]["type"] == "check_out"

    def test_line_manager_can_only_approve_in_scope(self):
        team_record = self.attendance_records["team"]
        response = self.post(
            "api_v1:attendance-approve",
            role=ROLE_LINE_MANAGER,
            reverse_kwargs={"pk": team_record.pk},
        )
        self.assert_http_status(response, status.HTTP_200_OK)

        other_record = self.attendance_records["other"]
        denied = self.post(
            "api_v1:attendance-approve",
            role=ROLE_LINE_MANAGER,
            reverse_kwargs={"pk": other_record.pk},
        )
        assert denied.status_code in (
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        )


class AttendanceDepartmentListTests(RoleAPITestCase):
    def test_manager_sees_departments_summary_with_counts(self):
        response = self.get("api_v1:attendance-departments-summary", role=ROLE_MANAGER)
        self.assert_http_status(response, status.HTTP_200_OK)
        data = self.extract_results(response)
        # Both departments exist in fixtures.
        assert {d["department_name"] for d in data} == {"HQ", "Remote"}

        hq = next(d for d in data if d["department_name"] == "HQ")
        remote = next(d for d in data if d["department_name"] == "Remote")

        # HQ has 5 active employees in setUp, but only 1 attendance record.
        assert hq["total_employees"] == 5
        assert hq["present"] == 1
        assert hq["permitted"] == 0
        assert hq["absent"] == 4

        assert remote["total_employees"] == 1
        assert remote["present"] == 1
        assert remote["absent"] == 0

    def test_line_manager_sees_only_own_department_in_summary(self):
        response = self.get(
            "api_v1:attendance-departments-summary", role=ROLE_LINE_MANAGER
        )
        self.assert_http_status(response, status.HTTP_200_OK)
        data = self.extract_results(response)
        assert len(data) == 1
        assert data[0]["department_name"] == "HQ"

    def test_line_manager_cannot_view_other_department_detail(self):
        remote_id = self.departments["remote"].id
        denied = self.get(
            "api_v1:attendance-department-attendance",
            role=ROLE_LINE_MANAGER,
            reverse_kwargs={"department_id": remote_id},
        )
        self.assert_denied(denied)

    def test_manager_can_view_department_detail_rows(self):
        hq_id = self.departments["hq"].id
        response = self.get(
            "api_v1:attendance-department-attendance",
            role=ROLE_MANAGER,
            reverse_kwargs={"department_id": hq_id},
        )
        self.assert_http_status(response, status.HTTP_200_OK)
        rows = self.extract_results(response)
        # One row per employee in the department.
        assert len(rows) == 5
        statuses = {r["status"] for r in rows}
        assert "PRESENT" in statuses
        assert "ABSENT" in statuses


class AttendancePunchSecurityTests(RoleAPITestCase):
    def test_employee_cannot_clock_in_for_another_employee_by_url_tweaking(self):
        OfficeNetwork.objects.create(
            label="Loopback", cidr="127.0.0.1/32", is_active=True
        )
        other_emp_id = self.others["employee"].employee.pk
        payload = {"clock_in_location": "HQ kiosk"}
        denied = self.post(
            "employee-attendance-clock-in",
            role=ROLE_EMPLOYEE,
            payload=payload,
            reverse_kwargs={"employee_id": other_emp_id},
        )
        self.assert_denied(denied)
