from rest_framework.routers import DefaultRouter

from .views import ExpenseRequestViewSet

router = DefaultRouter()
router.register("expenses", ExpenseRequestViewSet, basename="expenses")

urlpatterns = router.urls
