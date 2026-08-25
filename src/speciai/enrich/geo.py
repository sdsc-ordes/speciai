"""Geocoding functionality."""

from functools import lru_cache

from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim
from geopy.location import Location

from speciai.enrich.continents import continent_name

OSMField = str
DWCTerm = str

# Nominatim answers in the place's own language unless asked otherwise, which would
# put "Schweiz" in country and localise stateProvince per record. Darwin Core wants
# one stable form, and the target collection's sheet is English.
LANGUAGE = "en"

USER_AGENT = "speciai"
# geopy defaults to a 1 second read timeout, which the public Nominatim service
# routinely exceeds -- every slow lookup surfaced as GeocoderUnavailable.
GEOCODE_TIMEOUT = 10
# Nominatim's usage policy allows one request per second from a single client. A batch
# run walks straight through that without pacing, and gets throttled or blocked.
MIN_DELAY_SECONDS = 1.0
# Retry a failed lookup rather than losing the record's whole locality to one blip.
MAX_RETRIES = 2
RETRY_WAIT_SECONDS = 5.0

# OSM address keys per Darwin Core term, most specific first: the first key present
# wins. Ordered explicitly because Nominatim returns whichever administrative level
# fits the place -- a Swiss village may come back as ``village``, ``town`` or
# ``municipality``, and picking by dict insertion order silently lost the finer one.
OSM_ADDRESS_MAPPINGS: dict[DWCTerm, tuple[OSMField, ...]] = {
    "locality": ("hamlet", "village", "suburb", "town", "municipality", "city"),
    "stateProvince": ("state", "region"),
    "country": ("country",),
    "countryCode": ("country_code",),
}

# Every Darwin Core field ``enrich_locations`` can emit. This is the module's
# output contract: callers (e.g. the review form's re-derive) key off it, and a
# test asserts the helper never emits a key outside this set.
LOCATION_FIELDS: tuple[DWCTerm, ...] = (
    "locality",
    "continent",
    "country",
    "countryCode",
    "stateProvince",
    "decimalLatitude",
    "decimalLongitude",
)


@lru_cache(maxsize=1)
def _geocode():
    """Build the rate-limited geocoder once.

    One instance per process, because the pacing is per client: a limiter created per
    call would never delay anything.
    """
    nominatim = Nominatim(user_agent=USER_AGENT, timeout=GEOCODE_TIMEOUT)
    return RateLimiter(
        nominatim.geocode,
        min_delay_seconds=MIN_DELAY_SECONDS,
        max_retries=MAX_RETRIES,
        error_wait_seconds=RETRY_WAIT_SECONDS,
    )


@lru_cache(maxsize=1024)
def nominatim_locate(location: str) -> Location | None:
    return _geocode()(query=location, addressdetails=True, language=LANGUAGE)


def parse_address(loc: Location) -> dict[str, str | None]:
    """Map a Nominatim address onto Darwin Core terms."""
    address = loc.raw["address"]
    out_address: dict[str, str | None] = {}
    for term, osm_keys in OSM_ADDRESS_MAPPINGS.items():
        value = next((address[key] for key in osm_keys if key in address), None)
        if value is not None:
            out_address[term] = value

    # Nominatim reports the code lowercase; ISO 3166-1 alpha-2 is uppercase.
    code = out_address.get("countryCode")
    if code is not None:
        out_address["countryCode"] = code.upper()
        out_address["continent"] = continent_name(code)

    return out_address


def enrich_locations(location_text: str) -> dict[str, str | None]:
    """Geocode one locality string into Darwin Core location terms.

    Returns an empty dict when Nominatim has no match.
    """
    loc = nominatim_locate(location_text)
    if loc is None:
        return {}

    output = parse_address(loc)
    output["decimalLatitude"] = loc.latitude
    output["decimalLongitude"] = loc.longitude

    return output
