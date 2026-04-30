# exceptions.py
from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    # ({"status": "error", "message": message}, status=status_code)

    if response is not None:
        custom_data = {"status": "error", "errors": response.data["detail"]}
        response.data = custom_data
    return response
