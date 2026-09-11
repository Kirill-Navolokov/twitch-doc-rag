from django.urls import path
from retrieval.views import AskView

urlpatterns = [path("api/ask", AskView.as_view())]
