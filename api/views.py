from datetime import datetime, timezone
import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status


def _cors(response):
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response["Access-Control-Allow-Headers"] = "*"
    return response


def _error(message, status_code):
    return _cors(Response({"status": "error", "message": message}, status=status_code))


class ClassifyView(APIView):

    def options(self, request, *args, **kwargs):
        return _cors(Response(status=status.HTTP_200_OK))

    def get(self, request, *args, **kwargs):
        if "name" not in request.query_params:
            return _error("Missing required query parameter: name", status.HTTP_400_BAD_REQUEST)

        name = request.query_params.get("name")

        if name is None or name.strip() == "":
            return _error("Query parameter 'name' cannot be empty", status.HTTP_400_BAD_REQUEST)

        name = name.strip()

        if not any(c.isalpha() for c in name):
            return _error("Unprocessable Entity", status.HTTP_422_UNPROCESSABLE_ENTITY)

        try:
            api_response = requests.get(
                "https://api.genderize.io/",    
                params={"name": name},
                timeout=10,
            )
            api_response.raise_for_status()
            data = api_response.json()
        except requests.Timeout:
            return _error("Genderize API request timed out", status.HTTP_502_BAD_GATEWAY)
        except requests.RequestException:
            return _error("Failed to reach Genderize API", status.HTTP_502_BAD_GATEWAY)
        except ValueError:
            return _error("Invalid response from Genderize API", status.HTTP_502_BAD_GATEWAY)

        gender = data.get("gender")
        probability = data.get("probability")
        sample_size = data.get("count")

        if gender is None or sample_size in (None, 0):
            return _error("No prediction available for the provided name", status.HTTP_200_OK)

        try:
            probability = float(probability)
            sample_size = int(sample_size)
        except (TypeError, ValueError):
            return _error("Invalid response from Genderize API", status.HTTP_502_BAD_GATEWAY)

        is_confident = probability >= 0.7 and sample_size >= 100
        processed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        return _cors(Response(
            {
                "status": "success",
                "data": {
                    "name": name,
                    "gender": gender,
                    "probability": probability,
                    "sample_size": sample_size,
                    "is_confident": is_confident,
                    "processed_at": processed_at,
                },
            },
            status=status.HTTP_200_OK,
        ))
