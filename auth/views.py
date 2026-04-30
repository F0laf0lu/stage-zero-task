import base64
import hashlib
import random
import secrets
import string

import requests
from django.contrib.auth import get_user_model
from django.shortcuts import redirect
from django.utils import timezone
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from auth.models import Token
from auth.services import jwt_decode, jwt_service

User = get_user_model()


def generate_random_string(length):
    characters = string.ascii_letters + string.digits
    return "".join(random.choices(characters, k=length))


def generate_secure_string(length):
    characters = string.ascii_letters + string.digits
    return "".join(secrets.choice(characters) for _ in range(length))


GITHUB_CLIENT_ID = "Ov23liXLLRFdo7qsj8gt"
GITHUB_CLIENT_SECRET = "2c32be0a812a684af5204482b452091796d59e83"
STATE = generate_random_string(16)
CODE_VERIFIER = generate_secure_string(43)
sha256_hash = hashlib.sha256(CODE_VERIFIER.encode("utf-8")).digest()
CODE_CHALLENGE = base64.urlsafe_b64encode(sha256_hash).decode("utf-8").replace("=", "")


# http://127.0.0.1:8000/auth/github


class AuthView(APIView):
    def get(self, request, *args, **kwargs):

        return redirect(
            f"https://github.com/login/oauth/authorize?client_id={GITHUB_CLIENT_ID}&code_challenge_method=S256&code_challenge={CODE_CHALLENGE}&scope=user&state={STATE}&redirect_uri=http://127.0.0.1:8000/auth/github/callback"
        )


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "github_id",
            "avatar_url",
            "email",
            "role",
            "last_login",
            "created_at",
        ]


class GithubCallBackView(APIView):
    def get(self, request, *args, **kwargs):
        auth_code = request.query_params.get("code")
        state = request.query_params.get("state", None)
        access_token = None

        if state is None or state != STATE:
            return Response(
                {"error": "Invalid request", "states": [state, STATE]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # GET TOKENS FROM GITHUB
        token_url = "https://github.com/login/oauth/access_token"
        payload = {
            "client_id": GITHUB_CLIENT_ID,
            "client_secret": GITHUB_CLIENT_SECRET,
            "code": auth_code,
            "redirect_uri": "http://127.0.0.1:8000/auth/github/callback",
            "code_verifier": CODE_VERIFIER,
        }
        headers = {"Accept": "application/json"}
        try:
            response = requests.post(token_url, data=payload, headers=headers)
            response_data = response.json()
            if "error" in response_data:
                return Response(response_data, status=status.HTTP_400_BAD_REQUEST)
            access_token = response_data.get("access_token")
        except Exception as e:
            return Response(
                {"message": "Error getting token", "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # GET USER
        try:
            user_url = "https://api.github.com/user"
            user_headers = {"Authorization": f"Bearer {access_token}"}
            github_response = requests.get(user_url, headers=user_headers)
            github_response_data = github_response.json()
            if "error" in github_response_data:
                return Response(github_response_data, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {"message": "Error getting user info", "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # GET EMAIL
        try:
            email_url = "https://api.github.com/user/emails"
            email_headers = {"Authorization": f"Bearer {access_token}"}
            email_response = requests.get(email_url, headers=email_headers)
            email_response_data = email_response.json()
            if "error" in email_response_data:
                return Response(email_response_data, status=status.HTTP_400_BAD_REQUEST)
            email = email_response_data[0]["email"]

            user, _ = User.objects.get_or_create(
                github_id=github_response_data.get("id"),
                defaults={
                    "username": email,
                    "avatar_url": github_response_data.get("avatar_url"),
                    "email": email,
                    "role": User.UserRole.ANALYST,
                },
            )
            user.last_login = timezone.now()
            user.save(update_fields=["last_login"])
            access_token, refresh_token = jwt_service({"id": str(user.id), "role": user.role})
            Token.objects.create(user=user, token=refresh_token, type="refresh")
            return Response(
                {
                    "user": UserSerializer(user).data,
                    "tokens": {"access_token": access_token, "refresh_token": refresh_token},
                },
                status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {"message": "Error getting email", "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class RefreshTokenView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny()]

    def post(self, request, *args, **kwargs):
        refresh_token = request.data.get("refresh_token", None)
        if refresh_token is None:
            return Response(
                {"status": "error", "message": "Validation error"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = jwt_decode(refresh_token)
        if payload["type"] != "refresh":
            return Response(
                {"status": "error", "message": "Invalid Token type"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = Token.objects.get(token=refresh_token)
            if token.is_revoked:
                return Response(
                    {"status": "error", "message": "Invalid Token"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if token.user.id != payload["user"]["id"]:
                return Response(
                    {"status": "error", "message": "Invalid Token"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except Token.DoesNotExist:
            return Response(
                {"status": "error", "message": "Invalid Token"}, status=status.HTTP_400_BAD_REQUEST
            )

        token.is_revoked = True
        token.save()

        new_access_token, new_refresh_token = jwt_service(
            {"id": payload["user"]["id"], "role": payload["user"]["role"]}
        )
        Token.objects.create(token=new_refresh_token, type="refresh", user=token.user)

        return Response(
            {
                "status": "success",
                "tokens": {"access_token": new_access_token, "refresh_token": new_refresh_token},
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    def post(self, request):
        refresh_token = request.data.get("refresh_token", None)
        if refresh_token is None:
            return Response(
                {"status": "error", "message": "Validation error"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = Token.objects.get(token=refresh_token, is_revoked=False)
            token.is_revoked = True
            token.save()
            return Response({"status": "success", "message": "Logout Successful"})
        except Token.DoesNotExist:
            return Response(
                {"status": "error", "message": "Invalid Token"}, status=status.HTTP_400_BAD_REQUEST
            )
