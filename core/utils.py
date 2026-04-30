import re

from core.models import Profile

VALID_SORT_FIELDS = {"age", "created_at", "gender_probability"}
VALID_AGE_GROUPS = {"child", "teenager", "adult", "senior"}

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
    if re.search(r"\bmales?\b", q) and not re.search(r"\bfemales?\b", q):
        filters["gender"] = "male"
    elif re.search(r"\bfemales?\b", q) and not re.search(r"\bmales?\b", q):
        filters["gender"] = "female"
    # "male and female" → no gender filter (both)

    # --- Age group / "young" mapping ---
    # "young" is parsed as 16–24, not a stored age group
    if re.search(r"\byoung\b", q):
        filters["min_age"] = 16
        filters["max_age"] = 24
    elif re.search(r"\bteenagers?\b", q):
        filters["age_group"] = "teenager"
    elif re.search(r"\bchildren\b|\bchild\b|\bkids?\b", q):
        filters["age_group"] = "child"
    elif re.search(r"\bseniors?\b|\belderly\b|\bold people\b", q):
        filters["age_group"] = "senior"
    elif re.search(r"\badults?\b", q):
        filters["age_group"] = "adult"

    # --- Explicit age bounds ("above X", "over X", "below X", "under X") ---
    above_match = re.search(r"\b(?:above|over|older than)\s+(\d+)\b", q)
    if above_match:
        filters["min_age"] = int(above_match.group(1)) + 1

    below_match = re.search(r"\b(?:below|under|younger than)\s+(\d+)\b", q)
    if below_match:
        filters["max_age"] = int(below_match.group(1))

    # --- Country ---
    # Try "from <country>" or "in <country>"
    country_match = re.search(
        r"\b(?:from|in)\s+([a-z][a-z\s\-\']+?)(?:\s+(?:who|that|with|and|above|below|over|under)|$)",
        q,
    )
    if country_match:
        filters["country_name"] = country_match.group(1).strip()

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

    country_name = params.get("country_name")
    if country_name:
        queryset = queryset.filter(country_name__icontains=country_name)

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
        # raise ValueError(f"'sort_by' must be one of: {', '.join(sorted(VALID_SORT_FIELDS))}")
        raise ValueError("Invalid parameter type")

    if order not in ("asc", "desc"):
        raise ValueError("Invalid parameter type")

    return sort_by, order


def build_profile_queryset(request):
    # --- Parse & validate sorting ---
    try:
        sort_by, order = parse_sorting(request)
    except ValueError:
        raise

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
                raise
                # return _error(
                #     f"'{field}' must be a valid number",
                #     status.HTTP_422_UNPROCESSABLE_ENTITY,
                # )

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
    return queryset
