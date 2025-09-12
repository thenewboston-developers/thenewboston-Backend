"""
Cache configuration for Redis backend.
Optimized for high-throughput @ mention system with connection pooling.
"""

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://localhost:6379/1',  # Using DB 1 for cache (DB 0 for Celery)
        'KEY_PREFIX': 'tnb_cache',
        'TIMEOUT': 1800,  # Default timeout of 30 minutes for better cache hit rates
    },
    # Dedicated cache for user search with shorter TTL and LFU-like behavior
    'user_search': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://localhost:6379/2',  # Separate DB for user search
        'KEY_PREFIX': 'user_search',
        'TIMEOUT': 300,  # 5 minutes for frequently changing data
    },
    # Cache for popular/verified users with longer TTL
    'popular_users': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://localhost:6379/3',  # Separate DB for popular users
        'KEY_PREFIX': 'popular_users',
        'TIMEOUT': 86400,  # 24 hours for stable data
    },
}
