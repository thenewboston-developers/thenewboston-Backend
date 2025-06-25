from ..models import FrontendDeployment
from .general import BaseModelSerializer


class FrontendDeploymentSerializer(BaseModelSerializer):

    class Meta:
        model = FrontendDeployment
        fields = ('id', 'created_date', 'deployed_by')
        read_only_fields = ('id', 'created_date', 'deployed_by')
