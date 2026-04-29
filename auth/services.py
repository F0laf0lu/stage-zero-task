import os
from datetime import timedelta

import jwt
from django.utils import timezone
from dotenv import load_dotenv

load_dotenv()


def jwt_service(user_data):
    ACCESS_TOKEN_KEY = os.getenv("JWT_SECRET_KEY")
    REFRESH_TOKEN_KEY = os.getenv("REFRESH_SECRET_KEY")
    payload = {
        "id": user_data.get("id"),
        "role": user_data.get("role"),
    }
    access_token = jwt.encode(
        {"user": payload, "exp": timezone.now() + timedelta(minutes=3)},
        ACCESS_TOKEN_KEY,
        algorithm="HS256",
    )
    refresh_token = jwt.encode(
        {"user": payload, "exp": timezone.now() + timedelta(minutes=5)},
        key=REFRESH_TOKEN_KEY,
        algorithm="HS256",
    )
    return access_token, refresh_token
