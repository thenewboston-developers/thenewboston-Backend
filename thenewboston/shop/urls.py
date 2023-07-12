from rest_framework.routers import SimpleRouter

from .views.cart_product import CartProductViewSet
from .views.product import ProductViewSet

router = SimpleRouter(trailing_slash=False)
router.register('cart_products', CartProductViewSet)
router.register('products', ProductViewSet)

urlpatterns = router.urls
