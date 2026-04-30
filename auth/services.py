import os
from datetime import timedelta

import jwt
from django.utils import timezone
from dotenv import load_dotenv
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from auth.models import Token

load_dotenv()


def jwt_service(user_data):
    ACCESS_TOKEN_KEY = os.getenv("JWT_SECRET_KEY")
    REFRESH_TOKEN_KEY = os.getenv("REFRESH_SECRET_KEY")
    payload = {
        "id": user_data.get("id"),
        "role": user_data.get("role"),
    }
    access_token = jwt.encode(
        {"user": payload, "exp": timezone.now() + timedelta(days=3)},
        ACCESS_TOKEN_KEY,
        algorithm="HS256",
    )
    refresh_token = jwt.encode(
        {"user": payload, "exp": timezone.now() + timedelta(days=5)},
        key=REFRESH_TOKEN_KEY,
        algorithm="HS256",
    )
    Token.objects.create(token=refresh_token, type="refresh")
    return access_token, refresh_token


def jwt_decode(token):
    key_configs = [
        {"key": os.getenv("JWT_SECRET_KEY"), "type": "access"},
        {"key": os.getenv("REFRESH_SECRET_KEY"), "type": "refresh"},
    ]

    for config in key_configs:
        try:
            payload = jwt.decode(token, config["key"], algorithms=["HS256"])
            if payload:
                payload["type"] = config["type"]
                return payload
            continue

        except ExpiredSignatureError:
            raise ExpiredSignatureError("Token Expired")
        except InvalidTokenError:
            continue

    raise InvalidTokenError("Invalid token or type mismatch")
