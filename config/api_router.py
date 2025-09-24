from django.conf import settings
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from hr_payroll.users.api.views import UserViewSet
from hr_payroll.employees.api.views import (
	DepartmentViewSet,
	EmployeeDocumentViewSet,
	EmployeeViewSet,
)

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("users", UserViewSet)
router.register("departments", DepartmentViewSet)
router.register("employees", EmployeeViewSet)
router.register("employee-documents", EmployeeDocumentViewSet)


app_name = "api"
urlpatterns = router.urls
