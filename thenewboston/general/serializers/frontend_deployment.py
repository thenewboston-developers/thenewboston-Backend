from rest_framework import serializers

from ..models import FrontendDeployment
from .general import BaseModelSerializer


class FrontendDeploymentSerializer(BaseModelSerializer):
    deployed_by_username = serializers.CharField(source='deployed_by.username', read_only=True)

    class Meta:
        model = FrontendDeployment
        fields = ('id', 'created_date', 'deployed_by', 'deployed_by_username')
        read_only_fields = ('id', 'created_date', 'deployed_by', 'deployed_by_username')
