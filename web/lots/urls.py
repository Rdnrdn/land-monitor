from django.urls import path

from .views import LotDetailView, LotListView, LotQuickActionView


app_name = "lots"

urlpatterns = [
    path("", LotListView.as_view(), name="list"),
    path("<int:pk>/action/", LotQuickActionView.as_view(), name="action"),
    path("<int:pk>/", LotDetailView.as_view(), name="detail"),
]
