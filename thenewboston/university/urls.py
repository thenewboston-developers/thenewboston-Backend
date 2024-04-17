from rest_framework.routers import SimpleRouter

from .views.course import CourseViewSet

router = SimpleRouter(trailing_slash=False)
router.register('courses', CourseViewSet)

urlpatterns = router.urls
