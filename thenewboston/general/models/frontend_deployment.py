from django.db import models

from .created_modified import CreatedModified


class FrontendDeployment(CreatedModified):
    deployed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    deployed_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='frontend_deployments'
    )

    class Meta:
        ordering = ['-deployed_at']
        verbose_name = 'Frontend Deployment'
        verbose_name_plural = 'Frontend Deployments'

    def __str__(self):
        return f'Deployment at {self.deployed_at}'

    @classmethod
    def get_latest_deployment(cls):
        return cls.objects.first()

    @classmethod
    def get_latest_timestamp(cls):
        latest = cls.get_latest_deployment()
        return latest.deployed_at if latest else None
