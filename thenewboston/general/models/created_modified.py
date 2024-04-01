from django.db import models

from .custom_model import CustomModel


class CreatedModified(CustomModel):
    # TODO(dmu) LOW: Consider rename: `created_date` -> `created_at`
    created_date = models.DateTimeField(auto_now_add=True)
    # TODO(dmu) LOW: Consider rename: `modified_date` -> `updated_at`
    modified_date = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
