from django.urls import path

from .views.user import UserDetailView

urlpatterns = [
    path('users', UserDetailView.as_view()),
]
