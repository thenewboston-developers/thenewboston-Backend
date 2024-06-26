from typing import Optional

from rest_framework import permissions

from thenewboston.general.utils.misc import get_nested_attr


class IsFieldUserOrReadOnly(permissions.BasePermission):
    user_field: Optional[str] = None

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True

        return getattr(obj, self.user_field) == request.user


class IsObjectBuyerOrReadOnly(IsFieldUserOrReadOnly):
    user_field = 'buyer'


class IsObjectCourseInstructorOrReadOnly(IsFieldUserOrReadOnly):
    user_field = 'course__instructor'

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True

        return get_nested_attr(obj, self.user_field) == request.user


class IsObjectFollowerOrReadOnly(IsFieldUserOrReadOnly):
    user_field = 'follower'


class IsObjectInstructorOrReadOnly(IsFieldUserOrReadOnly):
    user_field = 'instructor'


class IsObjectOwnerOrReadOnly(IsFieldUserOrReadOnly):
    user_field = 'owner'


class IsObjectSellerOrReadOnly(IsFieldUserOrReadOnly):
    user_field = 'seller'


class IsObjectSenderOrReadOnly(IsFieldUserOrReadOnly):
    user_field = 'sender'


class IsSelfOrReadOnly(permissions.BasePermission):

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True

        return obj == request.user
