from rest_framework.mixins import UpdateModelMixin
from rest_framework.serializers import BaseSerializer
from rest_framework.viewsets import GenericViewSet

UPDATE_METHODS = frozenset(('PATCH', 'PUT'))


class GetCurrentUserMixin:

    def get_current_user(self):
        user = self.request.user
        if not user or user.is_anonymous:
            return None

        return user


class LimitToUserMixin(GetCurrentUserMixin):
    limit_to_user_id_field: str | None = None

    def get_queryset(self):
        queryset = super().get_queryset()
        if limit_to_user_id_field := self.limit_to_user_id_field:
            if not ((user := self.get_current_user()) and user.is_authenticated):
                queryset = queryset.none()
            else:
                queryset = queryset.filter(**{limit_to_user_id_field: user.id})

        return queryset


class SerializerClassesMixin:
    serializer_classes: dict[str, BaseSerializer] = {}

    def get_serializer_class(self):
        return self.serializer_classes.get(self.action) or super().get_serializer_class()


class CustomGenericViewSet(LimitToUserMixin, SerializerClassesMixin, GenericViewSet):

    def get_queryset(self):
        queryset = super().get_queryset()

        if self.request.method in UPDATE_METHODS:
            queryset = queryset.select_for_update()

        return queryset


class PatchOnlyUpdateModelMixin(UpdateModelMixin):
    # PUT method should be disabled if we allow modification only subset of
    # attributes of a resource once or/and we do not allow
    # to resource id for creation (a special case of PUT)
    # TODO(dmu) LOW: Provide a better way to disable PUT (by modifying action_map)
    http_method_names = [name for name in CustomGenericViewSet.http_method_names if name != 'put']
