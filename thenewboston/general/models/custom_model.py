from django.db import models

from ..managers import CustomManager


class CustomModel(models.Model):

    objects = CustomManager()

    class Meta:
        abstract = True

    def select_for_update(self):
        return self.__class__.objects.select_for_update().get(pk=self.pk)

    def is_adding(self):
        return self._state.adding
