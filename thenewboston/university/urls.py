from rest_framework.routers import SimpleRouter

from .views.course import CourseViewSet
from .views.lecture import LectureViewSet

router = SimpleRouter(trailing_slash=False)
router.register('courses', CourseViewSet)
router.register('lectures', LectureViewSet)

urlpatterns = router.urls
