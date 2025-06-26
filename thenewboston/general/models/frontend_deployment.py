from django.db import models

from .created_modified import CreatedModified


class FrontendDeployment(CreatedModified):
    deployed_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='frontend_deployments'
    )

    class Meta:
        ordering = ['-created_date']

    def __str__(self):
        return f'Deployment at {self.created_date}'

    @classmethod
    def get_latest_deployment(cls):
        return cls.objects.first()

    @classmethod
    def get_latest_timestamp(cls):
        latest = cls.get_latest_deployment()
        return latest.created_date if latest else None
