from django.contrib.auth import get_user_model
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from rest_framework import status
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import APIException

from auth.services import jwt_decode

User = get_user_model()


class AuthenticationFailed(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Authentication failed."
    default_code = "authentication_failed"


class CustomAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return None
        token = auth_header.split("Bearer ")[-1] if "Bearer " in auth_header else auth_header
        try:
            payload = jwt_decode(token)
        except (ExpiredSignatureError, InvalidTokenError) as e:
            raise AuthenticationFailed(str(e))
        user_id = payload["user"]["id"]

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise AuthenticationFailed("Invalid credentials")
        return (user, None)

    def authenticate_header(self, request):
        # Adding this method ensures a 401 is raised when authenticate() returns None
        return 'Bearer realm="api"'
