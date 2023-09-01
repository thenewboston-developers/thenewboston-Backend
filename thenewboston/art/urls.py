from rest_framework.routers import SimpleRouter

from .views.openai_image import OpenAIImageViewSet

router = SimpleRouter(trailing_slash=False)
router.register('openai_images', OpenAIImageViewSet, basename='openai-images')

urlpatterns = router.urls
