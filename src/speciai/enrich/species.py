from functools import lru_cache

import requests

TAXONOMIC_RANKS = {
    "kingdom",
    "phylum",
    "order",
    "family",
    "subfamily",
    "tribe",
    "genus",
}

# Every Darwin Core field ``enrich_species`` can emit. This is the module's output
# contract: callers (e.g. the review form's re-derive) key off it, and a test
# asserts the helper never emits a key outside this set. Ranks are listed in a fixed
# (high-to-low) order so the output is deterministic; the assert keeps that list in
# sync with ``TAXONOMIC_RANKS``. Note that subfamily and tribe never arrive from this
# endpoint -- the match returns class/family/genus/kingdom/order/phylum/species only,
# so filling them needs a second call to /species/{key}/parents.
SPECIES_FIELDS: tuple[str, ...] = (
    "scientificName",
    "scientificNameAuthorship",
    "specificEpithet",
    "kingdom",
    "phylum",
    "order",
    "family",
    "subfamily",
    "tribe",
    "genus",
)
assert TAXONOMIC_RANKS <= set(SPECIES_FIELDS), (
    "SPECIES_FIELDS is missing a rank declared in TAXONOMIC_RANKS"
)

GBIF_MATCH_URL = "https://api.gbif.org/v2/species/match"


@lru_cache(maxsize=1024)
def fetch_gbif_species(scientific_name: str) -> dict[str, str] | None:
    """Retrieves species taxonomic data in a dictionary of darwin core terms.

    GBIF fuzzy-matches the whole name, so the caller passes the label's reading
    verbatim rather than pre-splitting it into genus and epithet.
    Returns None if there is no species-level match."""
    taxo = {}
    resp = requests.get(GBIF_MATCH_URL, params={"scientificName": scientific_name})
    resp.raise_for_status()

    data = resp.json()
    try:
        usage = data["usage"]
    except KeyError:
        return None
    if usage["rank"] != "SPECIES":
        return None

    taxo["scientificNameAuthorship"] = usage["authorship"]
    taxo["scientificName"] = usage["name"]
    taxo["specificEpithet"] = usage["specificEpithet"]

    for classif in data["classification"]:
        rank = classif["rank"].lower()
        if rank in TAXONOMIC_RANKS:
            taxo[rank] = classif["name"]

    return taxo


def enrich_species(scientific_name: str) -> dict[str, str | None]:
    """Match one identification string against GBIF's taxonomic backbone.

    Returns an empty dict when GBIF has no species-level match.
    """
    return fetch_gbif_species(scientific_name) or {}
