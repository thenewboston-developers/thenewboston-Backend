from rest_framework.routers import SimpleRouter

from .views.artwork import ArtworkViewSet
from .views.openai_image import OpenAIImageViewSet

router = SimpleRouter(trailing_slash=False)
router.register('artworks', ArtworkViewSet)
router.register('openai_images', OpenAIImageViewSet, basename='openai-images')

urlpatterns = router.urls
