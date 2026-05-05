from django.urls import path

from .views import AuthView, CliCallbakView, GithubCallBackView, LogoutView, RefreshTokenView

urlpatterns = [
    path("github", AuthView.as_view()),
    path("github/callback", GithubCallBackView.as_view()),
    path("github/cli_callback", CliCallbakView.as_view()),
    path("refresh", RefreshTokenView.as_view(), name="token-refresh"),
    path("logout", LogoutView.as_view(), name="logout"),
]
