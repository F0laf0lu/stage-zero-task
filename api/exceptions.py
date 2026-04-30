# exceptions.py
from rest_framework.exceptions import Throttled
from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if isinstance(exc, Throttled):
        custom_data = {"status": "error", "errors": "Too Many Requests"}
        response.data = custom_data
        return response

    if response is not None:
        custom_data = {"status": "error", "errors": response.data["detail"]}
        response.data = custom_data
    return response
