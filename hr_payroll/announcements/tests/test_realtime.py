import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from hr_payroll.employees.models import Employee

User = get_user_model()
TEST_PASSWORD = "password"  # noqa: S105


@pytest.mark.django_db
class TestAnnouncementRealtime:
    def setup_method(self):
        self.client = APIClient()
        # Manager user who can create announcements
        Group.objects.get_or_create(name="Manager")
        self.manager = User.objects.create_user(
            username="mgr", email="mgr@example.com", password=TEST_PASSWORD
        )
        self.manager.groups.add(Group.objects.get(name="Manager"))
        # Permission class requires employee profile
        self.manager_emp = Employee.objects.create(user=self.manager)

    def test_announcement_emits_to_groups(self, monkeypatch):
        self.client.force_authenticate(user=self.manager)

        # Two audience groups
        g1 = Group.objects.create(name="Engineering")
        g2 = Group.objects.create(name="Sales")

        calls = []

        def fake_emit_event_to_group(group_name, event, payload):
            calls.append((group_name, event, payload))

        monkeypatch.setattr(
            "hr_payroll.announcements.api.views.emit_event_to_group",
            fake_emit_event_to_group,
        )

        res = self.client.post(
            "/api/v1/announcements/",
            {
                "title": "Quarter Update",
                "message": "Targets and roadmap",
                "audience_group_ids": [g1.id, g2.id],
            },
            format="json",
        )
        assert res.status_code == 201, res.data
        # Emitted to both groups
        emitted_groups = [c[0] for c in calls]
        assert "Engineering" in emitted_groups
        assert "Sales" in emitted_groups
        # Event name
        assert all(c[1] == "announcement.created" for c in calls)
        # Payload includes title
        assert all(c[2].get("title") == "Quarter Update" for c in calls)

    def test_announcement_emits_to_all_when_no_groups(self, monkeypatch):
        self.client.force_authenticate(user=self.manager)

        calls = []

        def fake_emit_event_to_all(event, payload):
            calls.append((event, payload))

        monkeypatch.setattr(
            "hr_payroll.announcements.api.views.emit_event_to_all",
            fake_emit_event_to_all,
        )

        res = self.client.post(
            "/api/v1/announcements/",
            {"title": "Global Notice", "message": "All hands meeting"},
            format="json",
        )
        assert res.status_code == 201, res.data
        assert len(calls) == 1
        event, payload = calls[0]
        assert event == "announcement.created"
        assert payload.get("title") == "Global Notice"
