from rest_framework import serializers

from ..models import BonsaiHighlight


class BonsaiHighlightSerializer(serializers.ModelSerializer):
    order = serializers.IntegerField(required=False)

    class Meta:
        model = BonsaiHighlight
        fields = ('id', 'text', 'order')
        read_only_fields = ('id',)
