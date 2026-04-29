from django.urls import path
from .views import AuthView, GithubCallBackView

urlpatterns = [
    path('github', AuthView.as_view()),
    path('github/callback', GithubCallBackView.as_view()),
]
