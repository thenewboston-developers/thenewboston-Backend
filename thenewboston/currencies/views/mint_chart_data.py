from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.currencies.filters.mint_chart_data import MintChartDataFilter
from thenewboston.currencies.models import Mint
from thenewboston.currencies.serializers.mint_chart_data import MintChartDataResponseSerializer


class MintChartDataView(generics.ListAPIView):
    filter_backends = [DjangoFilterBackend]
    filterset_class = MintChartDataFilter
    permission_classes = [IsAuthenticated]
    queryset = Mint.objects.select_related('currency').order_by('created_date')
    serializer_class = MintChartDataResponseSerializer

    def list(self, request, *args, **kwargs):  # noqa: A003
        queryset = self.filter_queryset(self.get_queryset())
        filterset = self.filterset_class(request.query_params, queryset=queryset)
        queryset = filterset.qs
        currency = filterset.currency_obj

        if not currency:
            return Response({'error': 'Invalid currency'}, status=400)

        mints = list(queryset)

        if not mints:
            return Response({'data_points': [], 'currency': currency.id})

        data_points = []
        cumulative_total = 0

        for mint in mints:
            cumulative_total += mint.amount
            data_points.append(
                {'timestamp': mint.created_date, 'amount_minted': mint.amount, 'cumulative_total': cumulative_total}
            )

        serializer = self.get_serializer(data={'data_points': data_points, 'currency': currency.id})
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data)
