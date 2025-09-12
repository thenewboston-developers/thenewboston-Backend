from rest_framework.throttling import UserRateThrottle


class UserSearchThrottle(UserRateThrottle):
    """
    Custom throttle class for user search endpoint.
    Limits to 20 requests per minute per authenticated user.
    """

    rate = '20/minute'
