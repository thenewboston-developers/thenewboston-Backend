from datetime import timedelta

from django.utils import timezone
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from thenewboston.exchange.filters.chart_data import ChartDataFilter
from thenewboston.exchange.models import AssetPair, Trade
from thenewboston.exchange.serializers.chart_data import ChartDataResponseSerializer


class ChartDataView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    filterset_class = ChartDataFilter
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

    def get(self, request, *args, **kwargs):
        asset_pair_id = request.query_params.get('asset_pair')
        time_range = request.query_params.get('time_range')

        if not asset_pair_id or not time_range:
            return Response({'error': 'asset_pair and time_range parameters are required'}, status=400)

        try:
            asset_pair = AssetPair.objects.get(pk=asset_pair_id)
        except AssetPair.DoesNotExist:
            return Response({'error': 'Invalid asset_pair'}, status=400)

        trades = Trade.objects.filter(
            buy_order__primary_currency=asset_pair.primary_currency,
            buy_order__secondary_currency=asset_pair.secondary_currency
        ).order_by('created_date')

        if not trades.exists():
            return Response({
                'candlesticks': [],
                'interval_minutes': 0,
                'start_time': timezone.now(),
                'end_time': timezone.now()
            })

        now = timezone.now()
        first_trade = trades.first()

        start_time = self.get_start_time(time_range, now)
        if start_time is None or first_trade.created_date > start_time:
            start_time = first_trade.created_date

        interval_minutes = self.get_interval_minutes(time_range)

        # Round start time down to nearest interval
        start_time = self.round_time_to_interval(start_time, interval_minutes)

        # Filter trades within the time range and convert to list for efficiency
        trades = list(trades.filter(created_date__gte=start_time))

        # Generate intervals and aggregate data
        candlesticks = []
        current_time = start_time
        interval_delta = timedelta(minutes=interval_minutes)

        while current_time < now:
            interval_end = current_time + interval_delta

            # Get trades in this interval
            interval_trades = [trade for trade in trades if current_time <= trade.created_date < interval_end]

            if interval_trades:
                # Calculate OHLC data
                ohlc_data = self.aggregate_interval_data(interval_trades)
                ohlc_data['start'] = current_time
                ohlc_data['end'] = interval_end
                candlesticks.append(ohlc_data)
            elif candlesticks:
                # Carry forward the previous closing price for empty intervals
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
    def get_start_time(time_range, now):
        if time_range == '1d':
            return now - timedelta(days=1)
        elif time_range == '1w':
            return now - timedelta(days=7)
        elif time_range == '1m':
            return now - timedelta(days=30)
        elif time_range == '3m':
            return now - timedelta(days=90)
        elif time_range == '1y':
            return now - timedelta(days=365)
        else:
            return None

    @staticmethod
    def round_time_to_interval(dt, interval_minutes):
        # For intervals of 1 day or more, round to start of day
        if interval_minutes >= 1440:  # 1440 minutes = 1 day
            return dt.replace(hour=0, minute=0, second=0, microsecond=0)

        # For weekly intervals, round to start of week (Monday)
        if interval_minutes == 10080:  # 10080 minutes = 1 week
            days_since_monday = dt.weekday()
            start_of_week = dt - timedelta(days=days_since_monday)
            return start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)

        # For intervals less than a day
        # Convert to minutes since midnight
        minutes_since_midnight = dt.hour * 60 + dt.minute

        # Round down to nearest interval
        rounded_minutes = (minutes_since_midnight // interval_minutes) * interval_minutes

        # Calculate hours and minutes
        hours = rounded_minutes // 60
        minutes = rounded_minutes % 60

        # Return datetime with rounded time
        return dt.replace(hour=hours, minute=minutes, second=0, microsecond=0)
