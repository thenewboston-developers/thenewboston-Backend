from django.contrib import admin

from .models import FrontendDeployment


@admin.register(FrontendDeployment)
class FrontendDeploymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'deployed_at', 'deployed_by', 'created_date')
    list_filter = ('deployed_at', 'created_date')
    search_fields = ('deployed_by__username',)
    readonly_fields = ('deployed_at', 'created_date', 'modified_date')
    ordering = ('-deployed_at',)

    def save_model(self, request, obj, form, change):
        """Automatically set deployed_by to current user if not set."""
        if not obj.deployed_by_id:
            obj.deployed_by = request.user
        super().save_model(request, obj, form, change)

        # Broadcast deployment update to all connected clients
        from .consumers.frontend_deployment import FrontendDeploymentConsumer
        FrontendDeploymentConsumer.broadcast_deployment_update(deployed_at=obj.deployed_at)
