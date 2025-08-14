from .general import BaseModelSerializer
from ..models import FrontendDeployment


class FrontendDeploymentSerializer(BaseModelSerializer):
    class Meta:
        model = FrontendDeployment
        fields = ('id', 'created_date', 'deployed_by')
        read_only_fields = ('id', 'created_date', 'deployed_by')
