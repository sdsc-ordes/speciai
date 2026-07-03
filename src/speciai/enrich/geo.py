"""Geocoding functionality."""

from functools import lru_cache

from geopy.geocoders import Nominatim
from geopy.location import Location

OSMField = str
DWCTerm = str
OSM_ADDRESS_MAPPINGS: dict[OSMField, DWCTerm] = {
    'village': 'locality',
    'city': 'locality',
    'country_code': 'countryCode',
    'state': 'stateProvince',
    'country': 'country'
}

# Every Darwin Core field ``enrich_locations`` can emit. This is the module's
# output contract: callers (e.g. the review form's re-derive) key off it, and a
# test asserts the helper never emits a key outside this set. ``verbatimLocality``
# is the echoed input; the rest are interpreted/inferred.
LOCATION_FIELDS: tuple[DWCTerm, ...] = (
    'verbatimLocality',
    'locality',
    'continent',
    'country',
    'countryCode',
    'stateProvince',
    'decimalLatitude',
    'decimalLongitude',
)

# Country code -> continent name Based on wikipedia
COUNTRY_ALPHA2_TO_CONTINENT = {
    'AB': 'Asia',
    'AD': 'Europe',
    'AE': 'Asia',
    'AF': 'Asia',
    'AG': 'North America',
    'AI': 'North America',
    'AL': 'Europe',
    'AM': 'Asia',
    'AO': 'Africa',
    'AR': 'South America',
    'AS': 'Oceania',
    'AT': 'Europe',
    'AU': 'Oceania',
    'AW': 'North America',
    'AX': 'Europe',
    'AZ': 'Asia',
    'BA': 'Europe',
    'BB': 'North America',
    'BD': 'Asia',
    'BE': 'Europe',
    'BF': 'Africa',
    'BG': 'Europe',
    'BH': 'Asia',
    'BI': 'Africa',
    'BJ': 'Africa',
    'BL': 'North America',
    'BM': 'North America',
    'BN': 'Asia',
    'BO': 'South America',
    'BQ': 'North America',
    'BR': 'South America',
    'BS': 'North America',
    'BT': 'Asia',
    'BV': 'Antarctica',
    'BW': 'Africa',
    'BY': 'Europe',
    'BZ': 'North America',
    'CA': 'North America',
    'CC': 'Asia',
    'CD': 'Africa',
    'CF': 'Africa',
    'CG': 'Africa',
    'CH': 'Europe',
    'CI': 'Africa',
    'CK': 'Oceania',
    'CL': 'South America',
    'CM': 'Africa',
    'CN': 'Asia',
    'CO': 'South America',
    'CR': 'North America',
    'CU': 'North America',
    'CV': 'Africa',
    'CW': 'North America',
    'CX': 'Asia',
    'CY': 'Asia',
    'CZ': 'Europe',
    'DE': 'Europe',
    'DJ': 'Africa',
    'DK': 'Europe',
    'DM': 'North America',
    'DO': 'North America',
    'DZ': 'Africa',
    'EC': 'South America',
    'EE': 'Europe',
    'EG': 'Africa',
    'ER': 'Africa',
    'ES': 'Europe',
    'ET': 'Africa',
    'FI': 'Europe',
    'FJ': 'Oceania',
    'FK': 'South America',
    'FM': 'Oceania',
    'FO': 'Europe',
    'FR': 'Europe',
    'GA': 'Africa',
    'GB': 'Europe',
    'GD': 'North America',
    'GE': 'Asia',
    'GF': 'South America',
    'GG': 'Europe',
    'GH': 'Africa',
    'GI': 'Europe',
    'GL': 'North America',
    'GM': 'Africa',
    'GN': 'Africa',
    'GP': 'North America',
    'GQ': 'Africa',
    'GR': 'Europe',
    'GS': 'South America',
    'GT': 'North America',
    'GU': 'Oceania',
    'GW': 'Africa',
    'GY': 'South America',
    'HK': 'Asia',
    'HM': 'Antarctica',
    'HN': 'North America',
    'HR': 'Europe',
    'HT': 'North America',
    'HU': 'Europe',
    'ID': 'Asia',
    'IE': 'Europe',
    'IL': 'Asia',
    'IM': 'Europe',
    'IN': 'Asia',
    'IO': 'Asia',
    'IQ': 'Asia',
    'IR': 'Asia',
    'IS': 'Europe',
    'IT': 'Europe',
    'JE': 'Europe',
    'JM': 'North America',
    'JO': 'Asia',
    'JP': 'Asia',
    'KE': 'Africa',
    'KG': 'Asia',
    'KH': 'Asia',
    'KI': 'Oceania',
    'KM': 'Africa',
    'KN': 'North America',
    'KP': 'Asia',
    'KR': 'Asia',
    'KW': 'Asia',
    'KY': 'North America',
    'KZ': 'Asia',
    'LA': 'Asia',
    'LB': 'Asia',
    'LC': 'North America',
    'LI': 'Europe',
    'LK': 'Asia',
    'LR': 'Africa',
    'LS': 'Africa',
    'LT': 'Europe',
    'LU': 'Europe',
    'LV': 'Europe',
    'LY': 'Africa',
    'MA': 'Africa',
    'MC': 'Europe',
    'MD': 'Europe',
    'ME': 'Europe',
    'MF': 'North America',
    'MG': 'Africa',
    'MH': 'Oceania',
    'MK': 'Europe',
    'ML': 'Africa',
    'MM': 'Asia',
    'MN': 'Asia',
    'MO': 'Asia',
    'MP': 'Oceania',
    'MQ': 'North America',
    'MR': 'Africa',
    'MS': 'North America',
    'MT': 'Europe',
    'MU': 'Africa',
    'MV': 'Asia',
    'MW': 'Africa',
    'MX': 'North America',
    'MY': 'Asia',
    'MZ': 'Africa',
    'NA': 'Africa',
    'NC': 'Oceania',
    'NE': 'Africa',
    'NF': 'Oceania',
    'NG': 'Africa',
    'NI': 'North America',
    'NL': 'Europe',
    'NO': 'Europe',
    'NP': 'Asia',
    'NR': 'Oceania',
    'NU': 'Oceania',
    'NZ': 'Oceania',
    'OM': 'Asia',
    'OS': 'Asia',
    'PA': 'North America',
    'PE': 'South America',
    'PF': 'Oceania',
    'PG': 'Oceania',
    'PH': 'Asia',
    'PK': 'Asia',
    'PL': 'Europe',
    'PM': 'North America',
    'PR': 'North America',
    'PS': 'Asia',
    'PT': 'Europe',
    'PW': 'Oceania',
    'PY': 'South America',
    'QA': 'Asia',
    'RE': 'Africa',
    'RO': 'Europe',
    'RS': 'Europe',
    'RU': 'Europe',
    'RW': 'Africa',
    'SA': 'Asia',
    'SB': 'Oceania',
    'SC': 'Africa',
    'SD': 'Africa',
    'SE': 'Europe',
    'SG': 'Asia',
    'SH': 'Africa',
    'SI': 'Europe',
    'SJ': 'Europe',
    'SK': 'Europe',
    'SL': 'Africa',
    'SM': 'Europe',
    'SN': 'Africa',
    'SO': 'Africa',
    'SR': 'South America',
    'SS': 'Africa',
    'ST': 'Africa',
    'SV': 'North America',
    'SY': 'Asia',
    'SZ': 'Africa',
    'TC': 'North America',
    'TD': 'Africa',
    'TG': 'Africa',
    'TH': 'Asia',
    'TJ': 'Asia',
    'TK': 'Oceania',
    'TM': 'Asia',
    'TN': 'Africa',
    'TO': 'Oceania',
    'TP': 'Asia',
    'TR': 'Asia',
    'TT': 'North America',
    'TV': 'Oceania',
    'TW': 'Asia',
    'TZ': 'Africa',
    'UA': 'Europe',
    'UG': 'Africa',
    'US': 'North America',
    'UY': 'South America',
    'UZ': 'Asia',
    'VC': 'North America',
    'VE': 'South America',
    'VG': 'North America',
    'VI': 'North America',
    'VN': 'Asia',
    'VU': 'Oceania',
    'WF': 'Oceania',
    'WS': 'Oceania',
    'XK': 'Europe',
    'YE': 'Asia',
    'YT': 'Africa',
    'ZA': 'Africa',
    'ZM': 'Africa',
    'ZW': 'Africa',
}


def country_alpha2_to_continent_name(country_alpha2: str):
    """Convert country code to continent name.
    """
    upper_code = country_alpha2.upper()
    if upper_code not in COUNTRY_ALPHA2_TO_CONTINENT:
        raise KeyError

    return COUNTRY_ALPHA2_TO_CONTINENT[upper_code]


@lru_cache(maxsize=1024)
def nominatim_locate(location: str) -> Location | None:
    nom = Nominatim(user_agent="speciai")
    resp = nom.geocode(query=location, addressdetails=True)
    return resp


def parse_address(loc: Location) -> dict[str, str | None]:
    out_address = {}
    address = loc.raw['address']
    for (osm, dct) in OSM_ADDRESS_MAPPINGS.items():
        if osm in address:
            out_address[dct] = address[osm]

    # DWC terms not in OSM address
    if 'country_code' in address:

        continent = country_alpha2_to_continent_name(address['country_code'])
        out_address['continent'] = continent

    return out_address


def enrich_locations(location_texts: list[str]) -> dict[str, str | None]:
    locations: list[Location] = []
    for loc_text in location_texts:
        loc_data = nominatim_locate(loc_text)
        if loc_data is not None:
            locations.append({'text': loc_text, 'loc': loc_data})

    # No valid location hit
    if not locations:
        return {}

    finest_location = sorted(
        locations,
        key=lambda loc: loc['loc'].raw.get("place_rank", 0)
    )[-1]

    output: dict[str, str | None] = {}
    loc = finest_location['loc']
    output = parse_address(loc)
    output['decimalLatitude'] = loc.latitude
    output['decimalLongitude'] = loc.longitude
    output['verbatimLocality'] = finest_location['text']

    return output
