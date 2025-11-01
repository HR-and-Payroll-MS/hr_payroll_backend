from typing import Any, Dict

from django.utils import timezone
from rest_framework import serializers

from hr_payroll.employees.models import (
	Contract,
	Employee,
	EmployeeDocument,
	JobHistory,
)
from hr_payroll.org.models import Department
from django.db.models import Sum
from hr_payroll.users.models import User


class LineManagerMiniSerializer(serializers.ModelSerializer):
	id = serializers.SerializerMethodField()
	full_name = serializers.CharField(read_only=True)
	photo = serializers.ImageField(allow_null=True, required=False)

	class Meta:
		model = Employee
		fields = ["id", "full_name", "photo"]

	def get_id(self, obj: Employee) -> str:
		return str(obj.pk)


class JobHistorySerializer(serializers.ModelSerializer):

	class Meta:
		model = JobHistory
		fields = [
			"id",
			"effective_date",
			"job_title",
			"position_type",
			"employment_type",
		]


class ContractSerializer(serializers.ModelSerializer):
	class Meta:
		model = Contract
		fields = [
			"id",
			"contract_number",
			"contract_name",
			"contract_type",
			"start_date",
			"end_date",
		]


class EmployeeDocumentSerializer(serializers.ModelSerializer):
	class Meta:
		model = EmployeeDocument
		fields = ["id", "file", "name", "uploaded_at"]


class DepartmentSerializer(serializers.ModelSerializer):
	id = serializers.SerializerMethodField()

	class Meta:
		model = Department
		fields = ["id", "name", "description", "location", "budget_code"]

	def get_id(self, obj: Department) -> str:
		return str(obj.pk)


class EmployeeSerializer(serializers.ModelSerializer):
	id = serializers.SerializerMethodField()
	photo = serializers.ImageField(allow_null=True, required=False)
	full_name = serializers.CharField(read_only=True)
	position = serializers.CharField(read_only=True)
	status = serializers.SerializerMethodField()
	email = serializers.CharField(read_only=True)
	phone = serializers.CharField(read_only=True)
	timezone = serializers.SerializerMethodField()
	department = serializers.SerializerMethodField()
	line_manager = LineManagerMiniSerializer(read_only=True)

	# General (from user's profile)
	gender = serializers.SerializerMethodField()
	date_of_birth = serializers.SerializerMethodField()
	nationality = serializers.SerializerMethodField()
	health_care = serializers.SerializerMethodField()
	marital_status = serializers.SerializerMethodField()
	personal_tax_id = serializers.SerializerMethodField()
	social_insurance = serializers.SerializerMethodField()

	# Job
	service_years = serializers.SerializerMethodField()
	job_history = JobHistorySerializer(many=True, read_only=True)
	contracts = ContractSerializer(many=True, read_only=True)

	# Payroll
	employment_type = serializers.SerializerMethodField()
	job_title = serializers.CharField(source="title", read_only=True)
	total_compensation = serializers.SerializerMethodField()
	salary = serializers.SerializerMethodField()
	recurring = serializers.SerializerMethodField()
	one_off = serializers.SerializerMethodField()
	offset = serializers.SerializerMethodField()

	# Documents
	documents = EmployeeDocumentSerializer(many=True, read_only=True)

	class Meta:
		model = Employee
		fields = [
			# Base
			"id",
			"photo",
			"full_name",
			"position",
			"status",
			"email",
			"phone",
			"timezone",
			"department",
			"office",
			"line_manager",
			# General
			"gender",
			"date_of_birth",
			"nationality",
			"health_care",
			"marital_status",
			"personal_tax_id",
			"social_insurance",
			# Job
			"employee_id",
			"join_date",
			"service_years",
			"job_history",
			"contracts",
			# Payroll
			"employment_type",
			"job_title",
			"last_working_date",
			"total_compensation",
			"salary",
			"recurring",
			"one_off",
			"offset",
			# Documents
			"documents",
		]

	# Base fields
	def get_id(self, obj: Employee) -> str:
		return str(obj.pk)

	def get_status(self, obj: Employee) -> str:
		return "ACTIVE" if obj.is_active else "INACTIVE"

	def get_timezone(self, obj: Employee) -> str:
		tz = obj.time_zone or getattr(getattr(obj.user, "profile", None), "time_zone", "")
		return tz or ""

	def get_department(self, obj: Employee) -> str:
		return obj.department.name if obj.department else ""

	# General fields
	def _profile_value(self, obj: Employee, attr: str) -> Any:
		profile = getattr(obj.user, "profile", None)
		return getattr(profile, attr, None) if profile else None

	def get_gender(self, obj: Employee) -> str:
		return self._profile_value(obj, "gender") or ""

	def get_date_of_birth(self, obj: Employee) -> str:
		dob = self._profile_value(obj, "date_of_birth")
		return dob.isoformat() if dob else ""

	def get_nationality(self, obj: Employee) -> str:
		return self._profile_value(obj, "nationality") or ""

	def get_health_care(self, obj: Employee) -> str:
		return getattr(obj, "health_care", "") or ""

	def get_marital_status(self, obj: Employee) -> str:
		return self._profile_value(obj, "marital_status") or ""

	def get_personal_tax_id(self, obj: Employee) -> str:
		return self._profile_value(obj, "personal_tax_id") or ""

	def get_social_insurance(self, obj: Employee) -> str:
		return self._profile_value(obj, "social_insurance") or ""

	# Job fields
	def get_service_years(self, obj: Employee) -> str:
		return obj.service_years

	# Payroll aggregations from latest Compensation
	def _latest_comp(self, obj: Employee):
		# Access reverse relation from payroll without importing its models
		return getattr(obj, "compensations", None).order_by("-created_at").first() if hasattr(obj, "compensations") else None

	def _sum_components(self, comp, kind: str) -> str:
		if not comp:
			return "0.00"
		qs = comp.components.filter(kind=kind)
		total = qs.aggregate(s=Sum("amount")).get("s") or 0
		return f"{total:.2f}"

	def get_total_compensation(self, obj: Employee) -> str:
		comp = self._latest_comp(obj)
		if not comp:
			return "0.00"
		return f"{comp.total_compensation:.2f}"

	def get_salary(self, obj: Employee) -> str:
		return self._sum_components(self._latest_comp(obj), "base")

	def get_recurring(self, obj: Employee) -> str:
		return self._sum_components(self._latest_comp(obj), "recurring")

	def get_one_off(self, obj: Employee) -> str:
		return self._sum_components(self._latest_comp(obj), "one_off")

	def get_offset(self, obj: Employee) -> str:
		return self._sum_components(self._latest_comp(obj), "offset")

	def get_employment_type(self, obj: Employee) -> str:
		latest_jh = obj.job_history.order_by("-effective_date", "-pk").first()
		return getattr(latest_jh, "employment_type", "") or ""


class EmployeeWriteSerializer(serializers.ModelSerializer):
	# Write-focused fields; nested collections are read-only for now
	department_id = serializers.PrimaryKeyRelatedField(
		source="department",
		queryset=Department.objects.all(),
		required=False,
		allow_null=True,
	)
	line_manager_id = serializers.PrimaryKeyRelatedField(
		source="line_manager",
		queryset=Employee.objects.all(),
		required=False,
		allow_null=True,
	)

	class Meta:
		model = Employee
		fields = [
			"employee_id",
			"title",
			"department_id",
			"line_manager_id",
			"join_date",
			"last_working_date",
			"time_zone",
			"office",
			"health_care",
			"is_active",
			"photo",
		]


class OnboardExistingSerializer(serializers.Serializer):
	"""Payload for onboarding an existing User into an Employee record."""

	# Select an existing user (without an Employee) to onboard
	user = serializers.PrimaryKeyRelatedField(
		queryset=User.objects.filter(employee__isnull=True),
		help_text="User id of an existing user without an Employee record",
	)
	department_id = serializers.PrimaryKeyRelatedField(
		source="department",
		queryset=Department.objects.all(),
		required=False,
		allow_null=True,
	)
	title = serializers.CharField(required=False, allow_blank=True)
	employee_id = serializers.CharField(required=False, allow_blank=True)


class EmployeeCreateSerializer(serializers.ModelSerializer):
	# Create-focused serializer: excludes line_manager selection; it will be
	# derived from Department.manager automatically on create.
	user = serializers.PrimaryKeyRelatedField(
		queryset=User.objects.filter(employee__isnull=True),
		help_text="User id of an existing user without an Employee record",
	)
	department_id = serializers.PrimaryKeyRelatedField(
		source="department",
		queryset=Department.objects.all(),
		required=False,
		allow_null=True,
	)

	class Meta:
		model = Employee
		fields = [
			"user",
			"employee_id",
			"title",
			"department_id",
			"join_date",
			"last_working_date",
			"time_zone",
			"office",
			"health_care",
			"is_active",
			"photo",
		]


class UserCandidateSerializer(serializers.ModelSerializer):
	"""Lightweight user representation for onboarding selection."""

	full_name = serializers.CharField(source="name", read_only=True)

	class Meta:
		model = User
		fields = ["id", "username", "full_name", "email"]
