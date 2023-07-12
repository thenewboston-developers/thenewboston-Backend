from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.permissions import IsObjectBuyerOrReadOnly

from ..models import CartProduct
from ..serializers.cart_product import CartProductReadSerializer, CartProductWriteSerializer


class CartProductViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsObjectBuyerOrReadOnly]
    queryset = CartProduct.objects.none()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        cart_product = serializer.save()
        read_serializer = CartProductReadSerializer(cart_product, context={'request': request})

        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    def get_queryset(self):
        user = self.request.user
        return CartProduct.objects.filter(buyer=user)

    def get_serializer_class(self):
        if self.action == 'create':
            return CartProductWriteSerializer

        return CartProductReadSerializer
