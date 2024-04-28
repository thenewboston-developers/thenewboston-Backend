from django.db import models

from .base import Base


class Lecture(Base):
    course = models.ForeignKey('university.Course', on_delete=models.CASCADE)
    youtube_id = models.CharField(max_length=255)
    position = models.PositiveIntegerField()
    thumbnail_url = models.URLField(blank=True, null=True)

    def __str__(self):
        return self.name
