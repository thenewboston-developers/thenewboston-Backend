from datetime import timedelta

from django.db.models import Max, Min, Sum
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

    def get_interval_minutes(self, start_time, end_time):
        """Calculate interval minutes based on time range."""
        # Calculate total minutes in the time range
        total_minutes = int((end_time - start_time).total_seconds() / 60)

        # Divide by 100 to get approximately 100 data points
        interval_minutes = max(1, total_minutes // 100)

        return interval_minutes

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
        else:  # 'all'
            return None  # Will be set to first trade date

    def aggregate_interval_data(self, interval_trades):
        """Aggregate OHLC data for an interval."""
        first_trade = interval_trades.first()
        last_trade = interval_trades.last()

        aggregated = interval_trades.aggregate(
            high=Max('trade_price'), low=Min('trade_price'), volume=Sum('fill_quantity')
        )

        return {
            'open': first_trade.trade_price,
            'high': aggregated['high'],
            'low': aggregated['low'],
            'price': last_trade.trade_price,  # closing price
            'volume': aggregated['volume'] or 0
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
                'total_points': 0,
                'start_time': timezone.now(),
                'end_time': timezone.now()
            })

        # Determine time range
        now = timezone.now()
        first_trade = trades.first()

        start_time = self.get_start_time(time_range, now)
        if start_time is None or first_trade.created_date > start_time:
            start_time = first_trade.created_date

        interval_minutes = self.get_interval_minutes(start_time, now)

        # Filter trades within the time range
        trades = trades.filter(created_date__gte=start_time)

        # Generate intervals and aggregate data
        data_points = []
        current_time = start_time
        interval_delta = timedelta(minutes=interval_minutes)

        while current_time < now and len(data_points) < 100:
            interval_end = current_time + interval_delta

            # Get trades in this interval
            interval_trades = trades.filter(created_date__gte=current_time, created_date__lt=interval_end)

            if interval_trades.exists():
                # Calculate OHLC data
                ohlc_data = self.aggregate_interval_data(interval_trades)
                ohlc_data['timestamp'] = interval_end
                data_points.append(ohlc_data)
            elif data_points:
                # Carry forward the previous closing price for empty intervals
                last_point = data_points[-1]
                data_points.append({
                    'timestamp': interval_end,
                    'open': last_point['price'],
                    'high': last_point['price'],
                    'low': last_point['price'],
                    'price': last_point['price'],
                    'volume': 0
                })

            current_time = interval_end

        # Prepare response
        response_data = {
            'data': data_points,
            'interval_minutes': interval_minutes,
            'total_points': len(data_points),
            'start_time': start_time,
            'end_time': now
        }

        serializer = self.get_serializer(data=response_data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data)
