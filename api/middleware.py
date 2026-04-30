import logging

from django.utils import timezone

logger = logging.getLogger("request_logger")


class RequestLoggerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = timezone.now()

        response = self.get_response(request)

        end_time = timezone.now()
        status_code = response.status_code
        path = request.path
        method = request.method
        response_time = end_time - start_time
        logger.info(f"{response_time} -- {path}--{method} --{status_code}")
        return response
