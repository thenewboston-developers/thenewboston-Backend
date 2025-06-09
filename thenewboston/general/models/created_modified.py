from django.db import models

from .custom_model import CustomModel


class CreatedModified(CustomModel):
    created_date = models.DateTimeField(auto_now_add=True)
    modified_date = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
