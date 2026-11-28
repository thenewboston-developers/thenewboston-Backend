from django.urls import path

from .views import ActionView, ActivityView, CatalogView, EmblemView, MessagesView, StateView, TournamentsView

urlpatterns = [
    path('tribes/catalog', CatalogView.as_view(), name='tribes-catalog'),
    path('tribes/messages', MessagesView.as_view(), name='tribes-messages'),
    path('tribes/activity', ActivityView.as_view(), name='tribes-activity'),
    path('tribes/state', StateView.as_view(), name='tribes-state'),
    path('tribes/tournaments', TournamentsView.as_view(), name='tribes-tournaments'),
    path('tribes/actions', ActionView.as_view(), name='tribes-actions'),
    path('tribes/emblem', EmblemView.as_view(), name='tribes-emblem'),
]
