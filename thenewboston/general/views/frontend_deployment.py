from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, DjangoModelPermissions
from rest_framework.response import Response

from ..consumers.frontend_deployment import FrontendDeploymentConsumer
from ..enums import MessageType
from ..models import FrontendDeployment
from ..serializers import FrontendDeploymentSerializer


class FrontendDeploymentViewSet(viewsets.ModelViewSet):
    queryset = FrontendDeployment.objects.all()
    serializer_class = FrontendDeploymentSerializer
    permission_classes = [DjangoModelPermissions]

    def perform_create(self, serializer):
        deployment = serializer.save(deployed_by=self.request.user)
        deployment_data = FrontendDeploymentSerializer(deployment).data
        FrontendDeploymentConsumer.stream_frontend_deployment(
            message_type=MessageType.UPDATE_FRONTEND_DEPLOYMENT, deployment_data=deployment_data
        )

    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def status(self, request):
        deployment = FrontendDeployment.get_latest_deployment()

        if deployment:
            serializer = self.get_serializer(deployment)
            return Response(serializer.data)

        return Response(None)
