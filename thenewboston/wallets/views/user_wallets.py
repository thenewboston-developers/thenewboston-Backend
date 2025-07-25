from django.db import models
from django.db.models import Count, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.users.models import User

from ..models import Wallet
from ..serializers.user_wallets import UserWalletSerializer


class UserWalletListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserWalletSerializer

    def get_queryset(self):
        user_id = self.kwargs.get('user_id')

        total_users_subquery = (
            Wallet.objects.filter(currency=OuterRef('currency'),
                                  balance__gt=0).values('currency').annotate(total=Count('owner', distinct=True)
                                                                             ).values('total')
        )

        rank_subquery = (
            Wallet.objects.filter(currency=OuterRef('currency'),
                                  balance__gt=OuterRef('balance')).values('currency').annotate(
                                      rank=Count('owner', distinct=True)
                                  ).values('rank')  # noqa: E126
        )

        queryset = Wallet.objects.filter(owner_id=user_id, balance__gt=0).select_related(
            'currency', 'currency__owner'
        ).annotate(
            rank=Coalesce(Subquery(rank_subquery, output_field=models.IntegerField()), Value(0)) + 1,
            total_users=Coalesce(Subquery(total_users_subquery, output_field=models.IntegerField()), Value(1))
        ).order_by('-balance')

        return queryset

    def list(self, request, *args, **kwargs):  # noqa: A003
        user_id = self.kwargs.get('user_id')
        try:
            User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)

        return super().list(request, *args, **kwargs)
