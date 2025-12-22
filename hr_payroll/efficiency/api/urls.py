from rest_framework.routers import DefaultRouter

from hr_payroll.efficiency.api.views import EfficiencyEvaluationViewSet
from hr_payroll.efficiency.api.views import EfficiencyTemplateViewSet

router = DefaultRouter()
router.register(
    "templates",
    EfficiencyTemplateViewSet,
    basename="efficiency-templates",
)
router.register(
    "evaluations",
    EfficiencyEvaluationViewSet,
    basename="efficiency-evaluations",
)

urlpatterns = router.urls
