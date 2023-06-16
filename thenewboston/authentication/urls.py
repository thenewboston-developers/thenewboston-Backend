from django.urls import path

from .views.login import LoginView

urlpatterns = [
    path('login', LoginView.as_view()),
]
