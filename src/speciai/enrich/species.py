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
    "taxonId",
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

# Ranks whose matched name is the organism itself, so its epithets and authorship
# describe this specimen. A coarser match (GBIF calls it HIGHERRANK) names a genus
# or a family instead, and only its classification is usable.
NAMED_RANKS = frozenset({"SPECIES", "SUBSPECIES", "VARIETY", "FORM"})


@lru_cache(maxsize=1024)
def fetch_gbif_species(scientific_name: str) -> dict[str, str] | None:
    """Retrieves species taxonomic data in a dictionary of darwin core terms.

    GBIF fuzzy-matches the whole name, so the caller passes the label's reading
    verbatim rather than pre-splitting it into genus and epithet.

    Whatever rank matched, the classification is kept: a label naming a genus GBIF
    cannot resolve to a species still yields the family and the order. The matched
    name, its authorship and its epithet are only taken from a rank in
    ``NAMED_RANKS``, since a coarser match names a higher taxon and not the
    specimen. ``infraspecificEpithet`` is deliberately not emitted -- the label
    supplies it, and ``SPECIES_FIELDS`` is what this module owns.

    Returns None when GBIF matched nothing at all."""
    resp = requests.get(GBIF_MATCH_URL, params={"scientificName": scientific_name})
    resp.raise_for_status()

    data = resp.json()
    usage = data.get("usage")
    if usage is None:
        return None

    taxo = {}
    if usage.get("rank") in NAMED_RANKS:
        taxo["scientificNameAuthorship"] = usage.get("authorship")
        taxo["scientificName"] = usage.get("name")
        taxo["specificEpithet"] = usage.get("specificEpithet")
        # The backbone key, which is what the sheet files as taxonId. It outlives a
        # rename, where scientificName does not. Only for a named rank: the key of a
        # genus-level match identifies the genus, not this specimen.
        taxo["taxonId"] = usage.get("key")

    for classif in data.get("classification", ()):
        rank = classif["rank"].lower()
        if rank in TAXONOMIC_RANKS:
            taxo[rank] = classif["name"]

    return {term: value for term, value in taxo.items() if value} or None


def enrich_species(scientific_name: str) -> dict[str, str | None]:
    """Match one identification string against GBIF's taxonomic backbone.

    Returns an empty dict when GBIF has no species-level match.
    """
    return fetch_gbif_species(scientific_name) or {}
