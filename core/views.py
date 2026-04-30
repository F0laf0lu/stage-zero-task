import math

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Profile
from core.permissions import CanCreateProfile, CanUpdateProfile
from core.serializers import ProfileSerializer
from core.services import ExternalAPIError, agify, genderize, nationalize
from core.utils import apply_filters, parse_nl_query, parse_pagination, parse_sorting

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
        # --- Parse & validate sorting ---
        try:
            sort_by, order = parse_sorting(request)
        except ValueError as e:
            return _error(str(e), status.HTTP_422_UNPROCESSABLE_ENTITY)

        # --- Parse & validate pagination ---
        try:
            page, limit = parse_pagination(request)
        except ValueError as e:
            return _error(str(e), status.HTTP_422_UNPROCESSABLE_ENTITY)

        # --- Parse numeric filter params ---
        raw_params = {}
        numeric_fields = {
            "min_age": int,
            "max_age": int,
            "min_gender_probability": float,
            "min_country_probability": float,
        }
        for field, cast in numeric_fields.items():
            val = request.query_params.get(field)
            if val is not None:
                try:
                    raw_params[field] = cast(val)
                except (ValueError, TypeError):
                    return _error(
                        f"'{field}' must be a valid number",
                        status.HTTP_422_UNPROCESSABLE_ENTITY,
                    )

        for field in ("gender", "age_group", "country_id"):
            val = request.query_params.get(field)
            if val is not None:
                raw_params[field] = val

        # --- Build queryset ---
        queryset = Profile.objects.all()
        queryset = apply_filters(queryset, raw_params)

        # --- Sorting ---
        if sort_by:
            prefix = "-" if order == "desc" else ""
            queryset = queryset.order_by(f"{prefix}{sort_by}")
        else:
            queryset = queryset.order_by("-created_at")

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
    permission_classes = [IsAuthenticated]

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
