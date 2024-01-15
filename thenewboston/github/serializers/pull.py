from rest_framework import serializers

from ..models import Pull


class PullSerializer(serializers.ModelSerializer):

    class Meta:
        model = Pull
        fields = '__all__'
