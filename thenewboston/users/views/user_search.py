from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..models import User
from ..serializers.user import UserReadSerializer


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_search(request):
    if not (query := request.GET.get('q', '').strip()):
        return Response({'error': 'Query parameter "q" is required'}, status=status.HTTP_400_BAD_REQUEST)

    users = User.objects.filter(username__istartswith=query).order_by('username')[:10]
    serializer = UserReadSerializer(users, many=True, context={'request': request})
    return Response(serializer.data)
