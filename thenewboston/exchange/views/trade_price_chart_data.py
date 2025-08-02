from datetime import timedelta
from itertools import groupby

from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.exchange.filters.trade_price_chart_data import TradePriceChartDataFilter
from thenewboston.exchange.models import Trade
from thenewboston.exchange.serializers.trade_price_chart_data import TradePriceChartDataResponseSerializer


class TradePriceChartDataView(generics.ListAPIView):
    filter_backends = [DjangoFilterBackend]
    filterset_class = TradePriceChartDataFilter
    permission_classes = [IsAuthenticated]
    queryset = Trade.objects.select_related(
        'buy_order__asset_pair', 'buy_order__asset_pair__primary_currency', 'buy_order__asset_pair__secondary_currency'
    ).order_by('created_date')
    serializer_class = TradePriceChartDataResponseSerializer

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

    def list(self, request, *args, **kwargs):  # noqa: A003
        # TODO(dmu) HIGH: This has potential performance issues. Instead calculate historical candlestick and store
        #                 them in the database.
        queryset = self.filter_queryset(self.get_queryset())
        filterset = self.filterset_class(request.query_params, queryset=queryset)
        queryset = filterset.qs
        asset_pair = filterset.asset_pair_obj
        time_range = filterset.time_range_value

        if not asset_pair:
            return Response({'error': 'Invalid asset pair'}, status=400)

        trades = list(queryset)
        interval_minutes = self.get_interval_minutes(time_range)

        if not trades:
            return Response({
                'candlesticks': [],
                'interval_minutes': interval_minutes,
                'start_time': timezone.now(),
                'end_time': timezone.now(),
                'primary_currency': asset_pair.primary_currency_id,
                'secondary_currency': asset_pair.secondary_currency_id
            })

        now = timezone.now()
        first_trade = trades[0]

        start_time = filterset.start_time
        if start_time is None or first_trade.created_date > start_time:
            start_time = first_trade.created_date

        start_time = self.snap_time_down_to_interval_start(start_time, interval_minutes)
        candlesticks = []
        interval_delta = timedelta(minutes=interval_minutes)

        def get_interval_key(trade):
            trade_time = trade.created_date
            minutes_since_start = int((trade_time - start_time).total_seconds() / 60)
            return minutes_since_start // interval_minutes

        last_close_price = None
        current_interval_index = 0

        for interval_index, group_iter in groupby(trades, key=get_interval_key):
            interval_trades = list(group_iter)

            # Carry through empty candlestick intervals between the last processed interval and current interval
            while current_interval_index < interval_index and last_close_price is not None:
                interval_start = start_time + timedelta(minutes=current_interval_index * interval_minutes)
                interval_end = interval_start + interval_delta
                candlesticks.append({
                    'start': interval_start,
                    'end': interval_end,
                    'open': last_close_price,
                    'high': last_close_price,
                    'low': last_close_price,
                    'close': last_close_price,
                    'volume': 0
                })
                current_interval_index += 1

            # Process the current interval with actual trades
            interval_start = start_time + timedelta(minutes=interval_index * interval_minutes)
            interval_end = interval_start + interval_delta
            ohlc_data = {
                'start': interval_start,
                'end': interval_end,
                'open': interval_trades[0].price,
                'high': max(trade.price for trade in interval_trades),
                'low': min(trade.price for trade in interval_trades),
                'close': interval_trades[-1].price,
                'volume': sum(trade.filled_quantity for trade in interval_trades)
            }
            candlesticks.append(ohlc_data)
            last_close_price = ohlc_data['close']
            current_interval_index = interval_index + 1

        # Carry through empty candlestick intervals from the last trade up to the current time
        while True:
            interval_start = start_time + timedelta(minutes=current_interval_index * interval_minutes)
            if interval_start >= now:
                break

            interval_end = interval_start + interval_delta
            if last_close_price is not None:
                candlesticks.append({
                    'start': interval_start,
                    'end': interval_end,
                    'open': last_close_price,
                    'high': last_close_price,
                    'low': last_close_price,
                    'close': last_close_price,
                    'volume': 0
                })

            current_interval_index += 1

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
    def snap_time_down_to_interval_start(start_time, interval_minutes):
        if interval_minutes < 1440:  # Sub-day intervals (5 min, 60 min, 360 min/6 hours)
            minutes_since_midnight = start_time.hour * 60 + start_time.minute
            rounded_minutes = (minutes_since_midnight // interval_minutes) * interval_minutes
            hours = rounded_minutes // 60
            minutes = rounded_minutes % 60
            return start_time.replace(hour=hours, minute=minutes, second=0, microsecond=0)
        elif interval_minutes == 1440:  # Daily interval (1440 minutes = 1 day)
            return start_time.replace(hour=0, minute=0, second=0, microsecond=0)
        elif interval_minutes == 10080:  # Weekly interval (10080 minutes = 1 week)
            days_since_monday = start_time.weekday()
            start_of_week = start_time - timedelta(days=days_since_monday)
            return start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        elif interval_minutes == 43200:  # Monthly interval (43200 minutes = 30 days approx)
            return start_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif interval_minutes == 525600:  # Yearly interval (525600 minutes = 365 days)
            return start_time.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            raise ValueError(f'Unsupported interval size: {interval_minutes} minutes')
