from rest_framework import permissions


class IsFieldUserOrReadOnly(permissions.BasePermission):
    user_field: str | None = None

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True

        return getattr(obj, self.user_field) == request.user


class IsObjectFollowerOrReadOnly(IsFieldUserOrReadOnly):
    user_field = 'follower'


class IsObjectOwnerOrReadOnly(IsFieldUserOrReadOnly):
    user_field = 'owner'


class IsSelfOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True

        return obj == request.user
