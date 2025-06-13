from datetime import timedelta

from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.exchange.filters.chart_data import ChartDataFilter
from thenewboston.exchange.models import Trade
from thenewboston.exchange.serializers.chart_data import ChartDataResponseSerializer


class ChartDataView(generics.ListAPIView):
    filter_backends = [DjangoFilterBackend]
    filterset_class = ChartDataFilter
    permission_classes = [IsAuthenticated]
    queryset = Trade.objects.select_related('buy_order__primary_currency',
                                            'buy_order__secondary_currency').order_by('created_date')
    serializer_class = ChartDataResponseSerializer

    @staticmethod
    def aggregate_interval_data(interval_trades):
        if not interval_trades:
            return None

        first_trade = interval_trades[0]
        last_trade = interval_trades[-1]

        high = max(trade.trade_price for trade in interval_trades)
        low = min(trade.trade_price for trade in interval_trades)
        volume = sum(trade.fill_quantity for trade in interval_trades)

        return {
            'open': first_trade.trade_price,
            'high': high,
            'low': low,
            'close': last_trade.trade_price,
            'volume': volume
        }

    def list(self, request, *args, **kwargs):  # noqa: A003
        queryset = self.filter_queryset(self.get_queryset())

        filterset = self.filterset_class(request.query_params, queryset=queryset)
        if not filterset.is_valid():
            return Response(filterset.errors, status=400)

        queryset = filterset.qs
        asset_pair = filterset.asset_pair_obj
        time_range = filterset.time_range_value

        if not asset_pair:
            return Response({'error': 'Invalid asset pair'}, status=400)

        trades = list(queryset)

        if not trades:
            return Response({
                'candlesticks': [],
                'interval_minutes': 0,
                'start_time': timezone.now(),
                'end_time': timezone.now()
            })

        now = timezone.now()
        first_trade = trades[0]

        start_time = filterset.start_time
        if start_time is None or first_trade.created_date > start_time:
            start_time = first_trade.created_date

        interval_minutes = self.get_interval_minutes(time_range)
        start_time = self.round_time_to_interval(start_time, interval_minutes)

        candlesticks = []
        current_time = start_time
        interval_delta = timedelta(minutes=interval_minutes)

        while current_time < now:
            interval_end = current_time + interval_delta
            interval_trades = [trade for trade in trades if current_time <= trade.created_date < interval_end]

            if interval_trades:
                ohlc_data = self.aggregate_interval_data(interval_trades)
                ohlc_data['start'] = current_time
                ohlc_data['end'] = interval_end
                candlesticks.append(ohlc_data)
            elif candlesticks:
                last_candlestick = candlesticks[-1]
                candlesticks.append({
                    'start': current_time,
                    'end': interval_end,
                    'open': last_candlestick['close'],
                    'high': last_candlestick['close'],
                    'low': last_candlestick['close'],
                    'close': last_candlestick['close'],
                    'volume': 0
                })

            current_time = interval_end

        serializer = self.get_serializer(
            data={
                'candlesticks': candlesticks,
                'interval_minutes': interval_minutes,
                'start_time': start_time,
                'end_time': now,
                'primary_currency': asset_pair.primary_currency_id,
                'secondary_currency': asset_pair.secondary_currency_id
            }
        )
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data)

    @staticmethod
    def get_interval_minutes(time_range):
        intervals = {
            '1d': 5,
            '1w': 60,
            '1m': 360,
            '3m': 360,
            '1y': 360,
            'all': 360,
        }
        return intervals[time_range]

    @staticmethod
    def round_time_to_interval(start_time, interval_minutes):
        minutes_since_midnight = start_time.hour * 60 + start_time.minute
        rounded_minutes = (minutes_since_midnight // interval_minutes) * interval_minutes
        hours = rounded_minutes // 60
        minutes = rounded_minutes % 60
        return start_time.replace(hour=hours, minute=minutes, second=0, microsecond=0)
