from django.http import JsonResponse


class CheckVersionHeaderMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/api/profiles"):
            version_header = request.META.get("HTTP_X_API_VERSION", None)
            if version_header is None:
                return JsonResponse(
                    {"status": "error", "message": "API version header required"}, status=400
                )
        response = self.get_response(request)
        return response
