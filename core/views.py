import re

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Profile
from core.serializers import ProfileSerializer
from core.services import ExternalAPIError, agify, genderize, nationalize

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

COUNTRY_NAME_TO_CODE = {
    "afghanistan": "AF", "albania": "AL", "algeria": "DZ", "angola": "AO",
    "argentina": "AR", "australia": "AU", "austria": "AT", "azerbaijan": "AZ",
    "bahrain": "BH", "bangladesh": "BD", "belarus": "BY", "belgium": "BE",
    "benin": "BJ", "bolivia": "BO", "botswana": "BW", "brazil": "BR",
    "bulgaria": "BG", "burkina faso": "BF", "burundi": "BI",
    "cameroon": "CM", "canada": "CA", "cape verde": "CV",
    "central african republic": "CF", "chad": "TD", "chile": "CL",
    "china": "CN", "colombia": "CO", "comoros": "KM", "congo": "CG",
    "democratic republic of congo": "CD", "dr congo": "CD", "drc": "CD",
    "costa rica": "CR", "croatia": "HR", "cuba": "CU",
    "czech republic": "CZ", "czechia": "CZ",
    "denmark": "DK", "djibouti": "DJ",
    "ecuador": "EC", "egypt": "EG", "eritrea": "ER", "estonia": "EE",
    "ethiopia": "ET",
    "finland": "FI", "france": "FR",
    "gabon": "GA", "gambia": "GM", "georgia": "GE", "germany": "DE",
    "ghana": "GH", "greece": "GR", "guatemala": "GT", "guinea": "GN",
    "guinea-bissau": "GW",
    "haiti": "HT", "honduras": "HN", "hungary": "HU",
    "india": "IN", "indonesia": "ID", "iran": "IR", "iraq": "IQ",
    "ireland": "IE", "israel": "IL", "italy": "IT", "ivory coast": "CI",
    "cote d'ivoire": "CI",
    "jamaica": "JM", "japan": "JP", "jordan": "JO",
    "kazakhstan": "KZ", "kenya": "KE", "kuwait": "KW",
    "latvia": "LV", "lebanon": "LB", "lesotho": "LS", "liberia": "LR",
    "libya": "LY", "lithuania": "LT",
    "madagascar": "MG", "malawi": "MW", "malaysia": "MY", "mali": "ML",
    "mauritania": "MR", "mauritius": "MU", "mexico": "MX",
    "moldova": "MD", "mongolia": "MN", "morocco": "MA", "mozambique": "MZ",
    "myanmar": "MM",
    "namibia": "NA", "nepal": "NP", "netherlands": "NL",
    "new zealand": "NZ", "nicaragua": "NI", "niger": "NE", "nigeria": "NG",
    "norway": "NO",
    "oman": "OM",
    "pakistan": "PK", "palestine": "PS", "panama": "PA",
    "papua new guinea": "PG", "paraguay": "PY", "peru": "PE",
    "philippines": "PH", "poland": "PL", "portugal": "PT",
    "qatar": "QA",
    "romania": "RO", "russia": "RU", "rwanda": "RW",
    "saudi arabia": "SA", "senegal": "SN", "sierra leone": "SL",
    "singapore": "SG", "somalia": "SO", "south africa": "ZA",
    "south korea": "KR", "south sudan": "SS", "spain": "ES",
    "sri lanka": "LK", "sudan": "SD", "swaziland": "SZ", "eswatini": "SZ",
    "sweden": "SE", "switzerland": "CH", "syria": "SY",
    "taiwan": "TW", "tanzania": "TZ", "thailand": "TH", "togo": "TG",
    "tunisia": "TN", "turkey": "TR",
    "uganda": "UG", "ukraine": "UA",
    "united arab emirates": "AE", "uae": "AE",
    "united kingdom": "GB", "uk": "GB", "britain": "GB",
    "united states": "US", "usa": "US", "america": "US",
    "uruguay": "UY", "uzbekistan": "UZ",
    "venezuela": "VE", "vietnam": "VN",
    "yemen": "YE",
    "zambia": "ZM", "zimbabwe": "ZW",
}

VALID_SORT_FIELDS = {"age", "created_at", "gender_probability"}
VALID_AGE_GROUPS = {"child", "teenager", "adult", "senior"}


def _error(message, status_code):
    return Response({"status": "error", "message": message}, status=status_code)


def _paginate(queryset, page, limit):
    total = queryset.count()
    offset = (page - 1) * limit
    items = queryset[offset: offset + limit]
    return total, items


# ---------------------------------------------------------------------------
# Natural-language query parser (rule-based only, no AI/LLMs)
# ---------------------------------------------------------------------------

def parse_nl_query(q: str) -> dict | None:
    """
    Convert a plain-English query string into a dict of filter kwargs.
    Returns None if the query cannot be interpreted.
    """
    q = q.lower().strip()
    if not q:
        return None

    filters = {}

    # --- Gender ---
    if re.search(r'\bmales?\b', q) and not re.search(r'\bfemales?\b', q):
        filters["gender"] = "male"
    elif re.search(r'\bfemales?\b', q) and not re.search(r'\bmales?\b', q):
        filters["gender"] = "female"
    # "male and female" → no gender filter (both)

    # --- Age group / "young" mapping ---
    # "young" is parsed as 16–24, not a stored age group
    if re.search(r'\byoung\b', q):
        filters["min_age"] = 16
        filters["max_age"] = 24
    elif re.search(r'\bteenagers?\b', q):
        filters["age_group"] = "teenager"
    elif re.search(r'\bchildren\b|\bchild\b|\bkids?\b', q):
        filters["age_group"] = "child"
    elif re.search(r'\bseniors?\b|\belderly\b|\bold people\b', q):
        filters["age_group"] = "senior"
    elif re.search(r'\badults?\b', q):
        filters["age_group"] = "adult"

    # --- Explicit age bounds ("above X", "over X", "below X", "under X") ---
    above_match = re.search(r'\b(?:above|over|older than)\s+(\d+)\b', q)
    if above_match:
        filters["min_age"] = int(above_match.group(1)) + 1

    below_match = re.search(r'\b(?:below|under|younger than)\s+(\d+)\b', q)
    if below_match:
        filters["max_age"] = int(below_match.group(1))

    # --- Country ---
    # Try "from <country>" or "in <country>"
    country_match = re.search(
        r'\b(?:from|in)\s+([a-z][a-z\s\-\']+?)(?:\s+(?:who|that|with|and|above|below|over|under)|$)',
        q
    )
    if country_match:
        country_text = country_match.group(1).strip()
        code = COUNTRY_NAME_TO_CODE.get(country_text)
        if code:
            filters["country_id"] = code
        else:
            # Try partial match for multi-word countries
            for name, iso in COUNTRY_NAME_TO_CODE.items():
                if name in country_text or country_text in name:
                    filters["country_id"] = iso
                    break

    # Require at least one meaningful filter to avoid passing everything through
    if not filters:
        return None

    return filters


def apply_filters(queryset, params: dict):
    gender = params.get("gender")
    if gender:
        queryset = queryset.filter(gender__iexact=gender)

    age_group = params.get("age_group")
    if age_group:
        queryset = queryset.filter(age_group__iexact=age_group)

    country_id = params.get("country_id")
    if country_id:
        queryset = queryset.filter(country_id__iexact=country_id)

    min_age = params.get("min_age")
    if min_age is not None:
        queryset = queryset.filter(age__gte=min_age)

    max_age = params.get("max_age")
    if max_age is not None:
        queryset = queryset.filter(age__lte=max_age)

    min_gender_prob = params.get("min_gender_probability")
    if min_gender_prob is not None:
        queryset = queryset.filter(gender_probability__gte=min_gender_prob)

    min_country_prob = params.get("min_country_probability")
    if min_country_prob is not None:
        queryset = queryset.filter(country_probability__gte=min_country_prob)

    return queryset


def parse_pagination(request):
    """Returns (page, limit) or raises ValueError with a message."""
    try:
        page = int(request.query_params.get("page", 1))
        limit = int(request.query_params.get("limit", 10))
    except (ValueError, TypeError):
        raise ValueError("'page' and 'limit' must be integers")

    if page < 1:
        raise ValueError("'page' must be >= 1")
    if limit < 1:
        raise ValueError("'limit' must be >= 1")

    limit = min(limit, 50)

    return page, limit


def parse_sorting(request):
    """Returns (sort_field, order) or raises ValueError with a message."""
    sort_by = request.query_params.get("sort_by")
    order = request.query_params.get("order", "asc").lower()

    if sort_by and sort_by not in VALID_SORT_FIELDS:
        raise ValueError(f"'sort_by' must be one of: {', '.join(sorted(VALID_SORT_FIELDS))}")

    if order not in ("asc", "desc"):
        raise ValueError("'order' must be 'asc' or 'desc'")

    return sort_by, order


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class ProfileListCreateView(APIView):
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
                    return _error(f"'{field}' must be a valid number", status.HTTP_422_UNPROCESSABLE_ENTITY)

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
        total, items = _paginate(queryset, page, limit)

        return Response(
            {
                "status": "success",
                "page": page,
                "limit": limit,
                "total": total,
                "data": ProfileSerializer(items, many=True).data,
            },
            status=status.HTTP_200_OK,
        )


class ProfileSearchView(APIView):
    def get(self, request, *args, **kwargs):
        q = request.query_params.get("q", "").strip()
        if not q:
            return _error("Missing or empty parameter 'q'", status.HTTP_400_BAD_REQUEST)

        filters = parse_nl_query(q)
        if filters is None:
            return Response(
                {"status": "error", "message": "Unable to interpret query"},
                status=status.HTTP_200_OK,
            )

        # --- Parse pagination ---
        try:
            page, limit = parse_pagination(request)
        except ValueError as e:
            return _error(str(e), status.HTTP_422_UNPROCESSABLE_ENTITY)

        queryset = Profile.objects.all()
        queryset = apply_filters(queryset, filters)
        queryset = queryset.order_by("-created_at")

        total, items = _paginate(queryset, page, limit)

        return Response(
            {
                "status": "success",
                "page": page,
                "limit": limit,
                "total": total,
                "data": ProfileSerializer(items, many=True).data,
            },
            status=status.HTTP_200_OK,
        )


class ProfileDetailView(APIView):
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
