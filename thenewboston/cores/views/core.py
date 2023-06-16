from rest_framework import viewsets
from rest_framework.parsers import FormParser, MultiPartParser

from ..models import Core
from ..serializers.core import CoreReadSerializer


class CoreViewSet(viewsets.ModelViewSet):
    parser_classes = (MultiPartParser, FormParser)
    queryset = Core.objects.all()
    serializer_class = CoreReadSerializer
