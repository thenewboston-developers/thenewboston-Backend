from django.db import models

from ..managers import CustomManager


class TrackerMixin:
    # These field must be added to the child model
    # tracker = FieldTracker()

    def changed_fields(self):
        return self.tracker.changed()

    def has_changes(self):
        return bool(self.changed_fields()) or self.is_adding()

    def has_changed(self, field_name, *field_names):
        if field_names:
            return bool(self.changed_fields().keys() & ({field_name} | set(field_names)))
        else:
            return self.tracker.has_changed(field_name)


class CustomModel(models.Model):
    objects = CustomManager()

    class Meta:
        abstract = True

    def select_for_update(self):
        return self.__class__.objects.select_for_update().get(pk=self.pk)

    def is_adding(self):
        return self._state.adding

    def advisory_unlock(self, lock_id: int) -> bool:
        return self.__class__.objects.with_advisory_unlock(lock_id).get(pk=self.pk)

    @classmethod
    def get_field_names(cls):
        return [field.name for field in cls._meta.fields]
