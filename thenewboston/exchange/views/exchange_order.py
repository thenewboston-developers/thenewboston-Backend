from django.db import transaction
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import CreateModelMixin, ListModelMixin, RetrieveModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.general.pagination import CustomPageNumberPagination
from thenewboston.general.permissions import IsObjectOwnerOrReadOnly
from thenewboston.general.views.base import UPDATE_METHODS, CustomGenericViewSet, PatchOnlyUpdateModelMixin

from ..models import ExchangeOrder
from ..models.exchange_order import ORDER_PROCESSING_LOCK_ID, UNFILLED_STATUSES, ExchangeOrderSide
from ..serializers.exchange_order import (
    ExchangeOrderCreateSerializer, ExchangeOrderReadSerializer, ExchangeOrderUpdateSerializer
)


# We do not to support order deletion, because we already have a cancellation mechanism
class ExchangeOrderViewSet(
    # PUT support is dropped due to complications related to updating order amount (related to wallet balances)
    # and also to avoid mess up with primary keys
    CreateModelMixin,
    PatchOnlyUpdateModelMixin,
    RetrieveModelMixin,
    ListModelMixin,
    CustomGenericViewSet
):
    # We are using declarative style to define serializer classes, queryset, etc., to follow DRF conventions
    serializer_class = ExchangeOrderReadSerializer
    serializer_classes = {'create': ExchangeOrderCreateSerializer, 'partial_update': ExchangeOrderUpdateSerializer}
    assert 'update' not in serializer_classes, 'Avoid PUT support, use PATCH only'
    pagination_class = CustomPageNumberPagination
    permission_classes = [IsAuthenticated, IsObjectOwnerOrReadOnly]
    limit_to_user_id_field = 'owner_id'
    queryset = ExchangeOrder.objects.order_by('-created_date')

    # TODO(dmu) CRITICAL: Restrict any changes to order other than status, because corresponding updates to wallet
    #                     balances is not supported yet

    def get_queryset(self):
        queryset = super().get_queryset()

        if self.request.method in UPDATE_METHODS:
            queryset = queryset.with_advisory_xact_lock(ORDER_PROCESSING_LOCK_ID)

        return queryset

    @action(detail=False, methods=['get'], url_path='book')
    def book(self, request):
        # TODO(dmu) HIGH: Move to dedicated endpoint, so regular DRF filtering can be used
        primary_currency_id = request.query_params.get('primary_currency')
        secondary_currency_id = request.query_params.get('secondary_currency')

        if not primary_currency_id or not secondary_currency_id:
            # TODO(dmu) MEDIUM: Mimic DRF format error response
            return Response({'error': 'Both primary_currency and secondary_currency parameters are required'},
                            status=status.HTTP_400_BAD_REQUEST)

        filter_kwargs = {
            'primary_currency_id': primary_currency_id,
            'secondary_currency_id': secondary_currency_id,
            'status__in': UNFILLED_STATUSES,
        }

        buy_orders = ExchangeOrder.objects.filter(
            side=ExchangeOrderSide.BUY.value, **filter_kwargs
        ).order_by('-price')[:50]  # TODO(dmu) MEDIUM: Unhardcode in favor of `limit` query parameter
        sell_orders = ExchangeOrder.objects.filter(
            side=ExchangeOrderSide.SELL.value, **filter_kwargs
        ).order_by('price')[:50]  # TODO(dmu) MEDIUM: Unhardcode in favor of `limit` query parameter
        return Response({
            'sell_orders': ExchangeOrderReadSerializer(sell_orders, many=True).data,
            'buy_orders': ExchangeOrderReadSerializer(buy_orders, many=True).data,
        })

    def create(self, *args, **kwargs):
        assert transaction.get_connection().in_atomic_block, "Ensure `'ATOMIC_REQUESTS': True`"
        return super().create(*args, **kwargs)

    def update(self, *args, **kwargs):
        assert transaction.get_connection().in_atomic_block, "Ensure `'ATOMIC_REQUESTS': True`"
        return super().update(*args, **kwargs)
