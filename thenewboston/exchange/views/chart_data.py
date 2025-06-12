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

    def get_interval_minutes(self, time_range):
        """Get fixed interval minutes based on time range."""
        intervals = {
            '1d': 5,  # 5 minute intervals
            '1w': 60,  # 1 hour intervals
            '1m': 360,  # 6 hour intervals
            '3m': 360,  # 1 day intervals
            '1y': 360,  # 1 day intervals
            'all': 360,  # 1 week intervals
        }
        return intervals.get(time_range, 60)  # Default to 1 hour

    def round_time_to_interval(self, dt, interval_minutes):
        """Round datetime down to the nearest interval."""
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

    def get_start_time(self, time_range, now):
        """Get the start time based on the time range."""
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
        else:  # 'all'
            return None  # Will be set to first trade date

    def aggregate_interval_data(self, interval_trades):
        """Aggregate OHLC data for an interval."""
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
            'close': last_trade.trade_price,  # closing price
            'volume': volume
        }

    def get(self, request, *args, **kwargs):
        # Get query parameters
        asset_pair_id = request.query_params.get('asset_pair')
        time_range = request.query_params.get('time_range')

        if not asset_pair_id or not time_range:
            return Response({'error': 'asset_pair and time_range parameters are required'}, status=400)

        try:
            asset_pair = AssetPair.objects.get(pk=asset_pair_id)
        except AssetPair.DoesNotExist:
            return Response({'error': 'Invalid asset_pair'}, status=400)

        # Get trades for this asset pair
        trades = Trade.objects.filter(
            buy_order__primary_currency=asset_pair.primary_currency,
            buy_order__secondary_currency=asset_pair.secondary_currency
        ).order_by('created_date')

        if not trades.exists():
            return Response({
                'data': [],
                'interval_minutes': 0,
                'start_time': timezone.now(),
                'end_time': timezone.now()
            })

        # Determine time range
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
        data_points = []
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
                data_points.append(ohlc_data)
            elif data_points:
                # Carry forward the previous closing price for empty intervals
                last_point = data_points[-1]
                data_points.append({
                    'start': current_time,
                    'end': interval_end,
                    'open': last_point['close'],
                    'high': last_point['close'],
                    'low': last_point['close'],
                    'close': last_point['close'],
                    'volume': 0
                })

            current_time = interval_end

        # Prepare response
        response_data = {
            'data': data_points,
            'interval_minutes': interval_minutes,
            'start_time': start_time,
            'end_time': now,
            'primary_currency': asset_pair.primary_currency_id,
            'secondary_currency': asset_pair.secondary_currency_id
        }

        serializer = self.get_serializer(data=response_data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data)
