from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

urlpatterns = [
    # The page only answers GET. Without the CSRF check a POST from a scanner gets a plain 405, with it every such
    # request was reported to Sentry as a CSRF failure.
    path('', csrf_exempt(TemplateView.as_view(template_name='api_index.html')), name='api_index'),
]
