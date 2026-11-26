from django.urls import path

from .views import ActionView, ActivityView, MessagesView, SeasonsView, StateView

urlpatterns = [
    path('tribes/messages', MessagesView.as_view(), name='tribes-messages'),
    path('tribes/activity', ActivityView.as_view(), name='tribes-activity'),
    path('tribes/state', StateView.as_view(), name='tribes-state'),
    path('tribes/seasons', SeasonsView.as_view(), name='tribes-seasons'),
    path('tribes/actions', ActionView.as_view(), name='tribes-actions'),
]
