from rest_framework import serializers

from ..models import ConnectFiveEloSnapshot


class ConnectFiveEloSnapshotSerializer(serializers.ModelSerializer):
    date = serializers.DateField(source='snapshot_date')

    class Meta:
        model = ConnectFiveEloSnapshot
        fields = ('date', 'elo')
