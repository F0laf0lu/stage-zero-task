import requests


class ExternalAPIError(Exception):
    def __init__(self, provider: str):
        self.provider = provider
        self.message = f"{provider} returned an invalid response"
        super().__init__(self.message)


def _get_json(url: str, name: str, provider: str) -> dict:
    try:
        response = requests.get(url, params={"name": name}, timeout=10)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        raise ExternalAPIError(provider)


def _classify_age_group(age: int) -> str:
    if age >= 60:
        return "senior"
    if age >= 20:
        return "adult"
    if age >= 13:
        return "teenager"
    return "child"


def genderize(name: str) -> dict:
    data = _get_json("https://api.genderize.io/", name, "Genderize")
    gender = data.get("gender")
    sample_size = data.get("count")

    if gender is None or not sample_size:
        raise ExternalAPIError("Genderize")

    try:
        probability = float(data.get("probability"))
        sample_size = int(sample_size)
    except (TypeError, ValueError):
        raise ExternalAPIError("Genderize")

    return {
        "gender": gender,
        "gender_probability": probability,
        "sample_size": sample_size,
    }


def agify(name: str) -> dict:
    data = _get_json("https://api.agify.io/", name, "Agify")
    age = data.get("age")

    if age is None:
        raise ExternalAPIError("Agify")

    try:
        age = int(age)
    except (TypeError, ValueError):
        raise ExternalAPIError("Agify")

    return {"age": age, "age_group": _classify_age_group(age)}


def nationalize(name: str) -> dict:
    data = _get_json("https://api.nationalize.io/", name, "Nationalize")
    country_list = data.get("country") or []

    if not country_list:
        raise ExternalAPIError("Nationalize")

    try:
        top = max(country_list, key=lambda c: c["probability"])
        return {
            "country_id": top["country_id"],
            "country_probability": float(top["probability"]),
        }
    except (KeyError, TypeError, ValueError):
        raise ExternalAPIError("Nationalize")

