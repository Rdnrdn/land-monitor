from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import include, path
from django.views.generic import RedirectView
from lots.views import NoticeDetailView, NoticeListView

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="lots:list", permanent=False)),
    path(
        "accounts/login/",
        LoginView.as_view(
            template_name="registration/login.html",
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
    path("lots/", include("lots.urls")),
    path("notices/", NoticeListView.as_view(), name="notices"),
    path("notices/<str:notice_number>/", NoticeDetailView.as_view(), name="notice-detail"),
    path('admin/', admin.site.urls),
]
