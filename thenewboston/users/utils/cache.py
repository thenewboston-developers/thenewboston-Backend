import hashlib
import logging
from typing import Any, List, Optional

from django.contrib.auth import get_user_model
from django.core.cache import cache, caches
from django.db.models import Count, Q
from django.utils import timezone

logger = logging.getLogger(__name__)


def get_cache_backend(cache_name: str):
    """Get cache backend with fallback to default."""
    try:
        return caches[cache_name]
    except Exception:
        return cache


# Use dedicated caches for different purposes with fallback
user_search_cache = get_cache_backend('user_search')
popular_users_cache = get_cache_backend('popular_users')
default_cache = cache


def generate_cache_key(prefix: str, query: str) -> str:
    """
    Generate a cache key based on prefix and normalized query.
    Query is lowercased for case-insensitive matching.
    """
    normalized_query = query.lower().strip()
    # Use hash for long queries to avoid key length issues
    query_hash = hashlib.md5(normalized_query.encode()).hexdigest()[:12]
    return f'{prefix}:{query_hash}'


def get_lfu_cache(key: str, cache_backend=None) -> Optional[Any]:
    """
    Get cached value with LFU-like behavior simulation.
    Increments access count for frequency tracking.
    """
    cache_to_use = cache_backend or user_search_cache

    # Try to get the cached value
    cached_data = cache_to_use.get(key)

    if cached_data is not None:
        # Track access frequency asynchronously (fire and forget)
        try:
            freq_key = f'{key}:freq'
            frequency = cache_to_use.get(freq_key, 0)
            cache_to_use.set(freq_key, frequency + 1, timeout=3600)
        except Exception as e:
            logger.warning(f'Failed to update cache frequency: {e}')

    return cached_data


def set_lfu_cache(key: str, value: Any, timeout: int = 300, cache_backend=None) -> None:
    """
    Set cache value with LFU-like behavior simulation.
    Optimized TTL for better cache hit rates.

    Args:
        key: Cache key
        value: Value to cache
        timeout: TTL in seconds (default 300s/5min for user search)
        cache_backend: Specific cache backend to use
    """
    cache_to_use = cache_backend or user_search_cache

    try:
        # Store the main value with optimized TTL
        cache_to_use.set(key, value, timeout=timeout)

        # Initialize frequency counter (async, non-blocking)
        freq_key = f'{key}:freq'
        cache_to_use.set(freq_key, 1, timeout=3600)
    except Exception as e:
        logger.error(f'Failed to set cache: {e}')


def warm_popular_users_cache():
    """
    Pre-populate cache with frequently mentioned users.
    Should be called periodically via Celery task.
    """
    User = get_user_model()

    try:
        # Get top mentioned users from last 7 days
        seven_days_ago = timezone.now() - timezone.timedelta(days=7)

        # Query for most mentioned users in posts and comments
        popular_users = (
            User.objects.filter(
                Q(mentioned_in_posts__created__gte=seven_days_ago)
                | Q(mentioned_in_comments__created__gte=seven_days_ago)
            )
            .annotate(mention_count=Count('mentioned_in_posts') + Count('mentioned_in_comments'))
            .order_by('-mention_count')[:100]
        )

        # Cache each popular user's search variations
        for user in popular_users:
            username_lower = user.username.lower()

            # Cache for different query lengths (autocomplete scenarios)
            for i in range(1, min(len(username_lower) + 1, 10)):
                partial_username = username_lower[:i]
                cache_key = generate_cache_key('user_search', partial_username)

                # Get all users starting with this prefix
                matching_users = (
                    User.objects.filter(username__istartswith=partial_username)
                    .only('id', 'username', 'avatar')
                    .order_by('username')[:10]
                )

                from thenewboston.users.serializers.user_search import UserSearchSerializer

                serializer = UserSearchSerializer(matching_users, many=True)

                # Cache with longer TTL for popular users
                popular_users_cache.set(cache_key, serializer.data, timeout=86400)  # 24 hours

        logger.info(f'Warmed cache for {len(popular_users)} popular users')

    except Exception as e:
        logger.error(f'Failed to warm popular users cache: {e}')


def get_cached_user_search(query: str) -> Optional[List[dict]]:
    """
    Try to get user search results from multiple cache tiers.
    """
    cache_key = generate_cache_key('user_search', query)

    # Try popular users cache first (longer TTL)
    result = popular_users_cache.get(cache_key)
    if result:
        return result

    # Fall back to regular user search cache
    return get_lfu_cache(cache_key)


def set_cached_user_search(query: str, results: List[dict]) -> None:
    """
    Cache user search results with appropriate TTL.
    """
    cache_key = generate_cache_key('user_search', query)
    set_lfu_cache(cache_key, results, timeout=300)  # 5 minutes


def invalidate_user_cache(username: str) -> None:
    """
    Invalidate cache entries for a specific user.
    Called when username changes or user is deleted.
    """
    username_lower = username.lower()

    # Clear cache for all possible prefixes
    for i in range(1, min(len(username_lower) + 1, 10)):
        partial_username = username_lower[:i]
        cache_key = generate_cache_key('user_search', partial_username)

        user_search_cache.delete(cache_key)
        popular_users_cache.delete(cache_key)


def invalidate_user_search_cache() -> None:
    """
    Invalidate all user search cache entries.
    This can be called when user data changes significantly.
    """
    # Clear all user search cache
    try:
        user_search_cache.clear()
        popular_users_cache.clear()
    except Exception as e:
        logger.error(f'Failed to clear cache: {e}')
