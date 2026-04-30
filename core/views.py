import csv
import math

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Profile
from core.permissions import CanCreateProfile, CanUpdateProfile
from core.serializers import ProfileSerializer
from core.services import ExternalAPIError, agify, genderize, nationalize
from core.utils import (
    apply_filters,
    build_profile_queryset,
    parse_nl_query,
    parse_pagination,
)

# import logging
# logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_SORT_FIELDS = {"age", "created_at", "gender_probability"}
VALID_AGE_GROUPS = {"child", "teenager", "adult", "senior"}


def _error(message, status_code):
    return Response({"status": "error", "message": message}, status=status_code)


def _paginate(queryset, page, limit, path):
    total = queryset.count()
    total_pages = math.ceil(total / limit)
    offset = (page - 1) * limit
    items = queryset[offset : offset + limit]
    prev_page = None if page <= 1 else f"{path}/?page={page - 1}&limit={limit}"
    next_page = None if page == total_pages else f"{path}/?page={page + 1}&limit={limit}"
    page_links = {
        "self": f"{path}/?page={page}&limit={limit}",
        "next": next_page,
        "prev": prev_page,
    }
    return total, items, total_pages, page_links


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


class ProfileListCreateView(APIView):
    throttle_scope = "profile"
    permission_classes = [CanCreateProfile]

    def post(self, request, *args, **kwargs):
        if "name" not in request.data:
            return _error("'name' is required", status.HTTP_400_BAD_REQUEST)

        name = request.data.get("name")

        if not isinstance(name, str):
            return _error("'name' must be a string", status.HTTP_422_UNPROCESSABLE_ENTITY)

        name = name.strip()
        if not name:
            return _error("'name' cannot be empty", status.HTTP_400_BAD_REQUEST)

        existing = Profile.objects.filter(name__iexact=name).first()
        if existing:
            return Response(
                {
                    "status": "success",
                    "message": "Profile already exists",
                    "data": ProfileSerializer(existing).data,
                },
                status=status.HTTP_200_OK,
            )

        try:
            enrichment = {
                **genderize(name),
                **agify(name),
                **nationalize(name),
            }
        except ExternalAPIError as exc:
            return _error(exc.message, status.HTTP_502_BAD_GATEWAY)

        profile = Profile.objects.create(name=name, **enrichment)
        return Response(
            {"status": "success", "data": ProfileSerializer(profile).data},
            status=status.HTTP_201_CREATED,
        )

    def get(self, request, *args, **kwargs):
        try:
            queryset = build_profile_queryset(request)
        except Exception as e:
            return Response({"status": "error", "message": str(e)})

        # --- Parse & validate pagination ---
        try:
            page, limit = parse_pagination(request)
        except ValueError as e:
            return _error(str(e), status.HTTP_422_UNPROCESSABLE_ENTITY)

        # --- Paginate ---
        total, items, total_pages, page_links = _paginate(queryset, page, limit, request.path)

        return Response(
            {
                "status": "success",
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": total_pages,
                "links": {
                    "self": page_links["self"],
                    "next": page_links["next"],
                    "prev": page_links["prev"],
                },
                "data": ProfileSerializer(items, many=True).data,
            },
            status=status.HTTP_200_OK,
        )


class ProfileSearchView(APIView):
    throttle_scope = "profile"
    permission_classes = [CanCreateProfile]

    def get(self, request, *args, **kwargs):
        q = request.query_params.get("q", "").strip()
        if not q:
            return _error("Missing or empty parameter", status.HTTP_400_BAD_REQUEST)

        filters = parse_nl_query(q)
        if filters is None:
            return Response(
                {"status": "error", "message": "Unable to interpret query"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- Parse pagination ---
        try:
            page, limit = parse_pagination(request)
        except ValueError as e:
            return _error(str(e), status.HTTP_422_UNPROCESSABLE_ENTITY)

        queryset = Profile.objects.all()
        queryset = apply_filters(queryset, filters)
        queryset = queryset.order_by("-created_at")

        total, items, total_pages, page_links = _paginate(queryset, page, limit, request.path)

        return Response(
            {
                "status": "success",
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": total_pages,
                "links": {
                    "self": page_links["self"],
                    "next": page_links["next"],
                    "prev": page_links["prev"],
                },
                "data": ProfileSerializer(items, many=True).data,
            },
            status=status.HTTP_200_OK,
        )


class ProfileDetailView(APIView):
    throttle_scope = "profile"
    permission_classes = [CanUpdateProfile]

    def _get_object(self, id):
        try:
            return Profile.objects.get(pk=id)
        except Profile.DoesNotExist:
            return None

    def get(self, request, id, *args, **kwargs):
        profile = self._get_object(id)
        if profile is None:
            return _error("Profile not found", status.HTTP_404_NOT_FOUND)
        return Response(
            {"status": "success", "data": ProfileSerializer(profile).data},
            status=status.HTTP_200_OK,
        )

    def delete(self, request, id, *args, **kwargs):
        profile = self._get_object(id)
        if profile is None:
            return _error("Profile not found", status.HTTP_404_NOT_FOUND)
        profile.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ExportDataView(APIView):
    throttle_scope = "profile"
    permission_classes = [CanCreateProfile]

    def get(self, request, *args, **kwargs):
        file_format = request.query_params.get("format", None)
        if file_format is None:
            return _error("Specify valid file format", status_code=400)
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="profiles_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(
            [
                "id",
                "name",
                "gender",
                "gender_probability",
                "age",
                "age_group",
                "country_id",
                "country_name",
                "country_probability",
                "created_at",
            ]
        )

        profiles = build_profile_queryset(request)
        for profile in profiles:
            writer.writerow(
                [
                    profile.id,
                    profile.name,
                    profile.gender,
                    profile.gender_probability,
                    profile.age,
                    profile.age_group,
                    profile.country_id,
                    profile.country_name,
                    profile.country_probability,
                    profile.created_at,
                ]
            )
        return response
