from rest_framework.routers import SimpleRouter

from .views.address import AddressViewSet
from .views.cart_product import CartProductViewSet
from .views.order import OrderViewSet
from .views.product import ProductViewSet

router = SimpleRouter(trailing_slash=False)
router.register('addresses', AddressViewSet)
router.register('cart_products', CartProductViewSet)
router.register('orders', OrderViewSet)
router.register('products', ProductViewSet)

urlpatterns = router.urls
