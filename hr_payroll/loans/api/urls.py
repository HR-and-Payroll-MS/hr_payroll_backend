from rest_framework.routers import DefaultRouter

from .views import LoanRequestViewSet

router = DefaultRouter()
router.register("loans", LoanRequestViewSet, basename="loans")

urlpatterns = router.urls
