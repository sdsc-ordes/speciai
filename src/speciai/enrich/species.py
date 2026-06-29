from functools import lru_cache
from itertools import product
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

@lru_cache(maxsize=1024)
def fetch_gbif_species(genus: str, species: str) -> dict[str, str] | None:
    """Retrieves species taxonomic data in a dictionary of darwin core terms.
    Returns None if there is no species-level match."""
    taxo = {}
    resp = requests.get(
        f"https://api.gbif.org/v2/species/match?scientificName={genus}+{species}"
    )
    resp.raise_for_status()

    data = resp.json()
    try:
        usage = data['usage']
    except KeyError:
        return None
    # Give up if we're hitting a higher order taxon
    if usage['rank'] != "SPECIES":
        return None

    taxo['scientificNameAuthorship'] = usage['authorship']
    taxo['scientificName'] = usage['name']
    taxo['specificEpithet'] = usage['specificEpithet']

    for classif in data['classification']:
        rank = classif['rank'].lower()
        if rank in TAXONOMIC_RANKS:
            taxo[rank] = classif['name']

    return taxo

def enrich_species(scientific_name: list[str]) -> dict[str, str | None]:

    output: dict[str, str | None] = {}
    # Drop duplicates
    unique_names = set(scientific_name)

    # Assuming genera are capitalized, and not species
    genera = filter(lambda name: name.istitle(), unique_names)
    species = filter(lambda name: name.islower(), unique_names)

    taxonomic_data = None
    for (genus, sp) in product(genera, species): # all g x s combinations
        taxonomic_data = fetch_gbif_species(genus, sp)
        if taxonomic_data is not None:
            # NOTE: abort on first good enough match to go faster. We could scan all and take the best.
            output['verbatimIdentification'] = f"{genus} {sp}"
            break

    if taxonomic_data is not None:
        output |= taxonomic_data

    return output
