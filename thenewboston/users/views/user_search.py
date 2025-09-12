from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..models import User
from ..serializers.user_search import UserSearchSerializer
from ..throttles import UserSearchThrottle
from ..utils.cache import get_cached_user_search, set_cached_user_search


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@throttle_classes([UserSearchThrottle])
def user_search(request):
    """
    Enhanced user search endpoint with:
    - Database indexing on username field
    - Multi-tier caching (popular users + LFU cache)
    - Connection pooling for Redis
    - Rate limiting (20 requests/minute per user)
    - Case-insensitive search
    - Minimal field serialization
    - Optimized for high throughput (millions req/sec with proper infrastructure)
    """
    if not (query := request.GET.get('q', '').strip()):
        return Response({'error': 'Query parameter "q" is required'}, status=status.HTTP_400_BAD_REQUEST)

    normalized_query = query.lower()

    # Try multi-tier cache first
    cached_results = get_cached_user_search(normalized_query)
    if cached_results is not None:
        return Response(cached_results)

    # Query database with optimized fields
    users = (
        User.objects.filter(username__istartswith=normalized_query)
        .only('id', 'username', 'avatar')
        .order_by('username')[:10]
    )

    serializer = UserSearchSerializer(users, many=True, context={'request': request})
    results = serializer.data

    # Cache results with optimized TTL
    set_cached_user_search(normalized_query, results)

    return Response(results)
