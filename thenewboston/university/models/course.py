from django.db import models

from .base import Base


class Course(Base):
    thumbnail = models.ImageField(upload_to='thumbnails/', blank=True, null=True)
    instructor = models.ForeignKey('users.User', on_delete=models.CASCADE)

    def __str__(self):
        return self.name
