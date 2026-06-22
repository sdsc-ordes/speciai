from itertools import product

import dateutil.parser
from geopy.geocoders import Nominatim
from geopy.location import Location
import pycountry_convert as pc
import requests

OSMField = str
DCTerm = str
OSM_ADDRESS_MAPPINGS: dict[OSMField, DCTerm] = {
    'village': 'locality',
    'city': 'locality',
    'country_code': 'countryCode',
    'state': 'stateProvince',
    'country': 'country'
}
TAXONOMIC_RANKS = {
    "kingdom"
    "phylum"
    "order"
    "family"
    "subfamily"
    "tribe"
    "genus"
}

doc = {
  "location": ["CH SH.", "ifcrishausen", "Chlosterfeid,"],
  "verbatimCoordinate": "Koord. .686.7/288.5",
  "catalogNumber": [ "ETHZ-ENT", "D", "0082619", "OO" ],
  "authorship": ["(Linnaeus, 1758)", "leg. L. Vidmer", "det. L. Widmer", "det. L. Widmer 1999", "Raymond Guenin 2017"],
  "scientificName": [ "Zygaena", "filipendalae", "Zygaena", "filipendulae", "Zygaenidae:", "Zygaeninae"],
}
output = {}

# nominatim

def locate(location: str) -> Location:
    nom = Nominatim(user_agent="speciai")
    location = nom.geocode(query=location, addressdetails=True)
    return location

locations = []
for loc_text in doc.get("location", []):
    locations.append({'text': loc_text, 'loc': locate(loc_text)})

finest_location = sorted(
    locations,
    key=lambda loc: loc['loc'].raw.get("place_rank", 0)
)[-1]


def parse_address(loc: Location) -> dict[str, str]:
    out_address = {}
    address = loc.raw['address']
    for (osm, dct) in OSM_ADDRESS_MAPPINGS.items():
        if osm in address:
            out_address[dct] = address[osm]

    # DCT fields not in OSM address
    if 'country_code' in address:
        continent = pc.country_alpha2_to_continent_name(address['country_code'])
        out_address['continent'] = continent

    return out_address

loc = finest_location['loc']
output['verbatimLocality'] = finest_location['text']
output['decimalLatitude'] = loc['lat']
output['decimalLongitude'] = loc['lon']

output |= parse_address(loc)

# coordinates
#NOTE: This is hard-coded since all records use this system so far.
output['geodeticDatum'] = "WGS84"
output['verbatimCoordinateSystem'] = "WGS84"
output['verbatimCoordinates'] = doc['verbatimCoordinates']


#NOTE: These are not (yet) covered:
# coordinateUncertaintyInMeters: float | None = Field( default=None, ge=0, description="Horizontal coordinate uncertainty, in metres.")
# verbatimCoordinateSystem: str | None = Field( default=None, description="Coordinate system of the verbatim coordinates.")
# minimumElevationInMeters: float | None = Field( default=None, description="Minimum elevation, in metres.")
# maximumElevationInMeters: float | None = Field( default=None, description="Maximum elevation, in metres.")

# catalog
output["catalogNumber"] = ' '.join(doc["catalogNumber"])

#NOTE: These are not (yet) covered:
# collectionCode: str | None = Field( default=None, description="Name/code identifying the collection.")
# otherCatalogNumbers: str | None = Field( default=None, description="Additional catalog numbers (e.g. previous IDs).")
# preparations: str | None = Field( default=None, description="Preparation/preservation method (e.g. 'pinned', 'in ethanol').")
# partOfOrganism: str | None = Field( default=None, description="Which part of the organism the record represents (NOT a Darwin Core term; needs explicit mapping).",)

# species

# Go to highest resolution -> traceback encounters other terms in our list?
unique_names = set(doc['scientificName'])

def parse_species(genus: str, species: str) -> dict[str, str] | None:
    """Retrieves species taxonomic data in a dictionary of dcTerms keys.
    Returns None if there is no species-level match."""
    taxo = {}
    resp = requests.get(
        f"https://api.gbif.org/v2/species/match?scientificName={genus}+{species}"
    )
    resp.raise_for_status()

    data = resp.json()
    usage = data['usage']
    # Give up if we're hitting a higher order taxon
    if usage['rank'] != "SPECIES":
        return None

    taxo['scientificNameAuthorship'] = usage['authorship']
    taxo['scientificName'] = usage['name']
    taxo['specificEpithet'] = usage['specificEpithet']
    taxo['taxonRank'] = usage['rank'].lower()

    for classif in data['classification']:
        rank = classif['rank'].lower()
        if rank in TAXONOMIC_RANKS:
            taxo[rank] = classif['name']

    return taxo




# Assuming genera are capitalized, and not species
genera = filter(lambda name: name.istitle(), unique_names)
species = filter(lambda name: name.islower(), unique_names)

taxonomic_data = None
for (genus, sp) in product(genera, species): # all g x s combinations
    taxonomic_data = parse_species(genus, sp)
    if taxonomic_data is not None:
        # NOTE: abort on first good enough match to go faster. We could scan all and take the best.
        break

if taxonomic_data is not None:
    output |= taxonomic_data

#NOTE: These are not (yet) covered:
# infraspecificEpithet: str | None = Field( default=None, description="Subspecies / infraspecific epithet.")
# taxonId: str | None = Field( default=None, description="Taxon identifier (DwC canonical term is 'taxonID'; kept as 'taxonId' to match target headers).",)
# associatedTaxa: str | None = Field( default=None, description="Other taxa associated with the specimen (e.g. host).")
# caste: str | None = Field( default=None, description="Social caste of the specimen, e.g. 'worker', 'queen' (Darwin Core term for eusocial insects).",)

# identification

output['recordedBy'] = doc['recordedBy']
output['dateIdentifiedBy'] = str(dateutil.parser.parse(doc['dateIdentified']).date())

#NOTE: These are not (yet) covered:
# verbatimIdentification: str | None = Field( default=None, description="Verbatim taxonomic identification as written on the label.")
# recordedBy: str | None = Field( default=None, description="Collector(s) of the specimen.")
# sex: str | None = Field(default=None, description="Sex of the specimen.")
# lifeStage: str | None = Field( default=None, description="Life stage (e.g. 'adult', 'larva').")
# organismRemarks: str | None = Field( default=None, description="Free-text remarks about the organism.")
#
# # --- Event (CollectingEvent) -------------------------------------------
# eventDate: str | None = Field( default=None, description="Interpreted collection date (ISO 8601; may be partial or a range).")
# verbatimEventDate: str | None = Field( default=None, description="Verbatim collection date as written on the label.")
# habitat: str | None = Field(default=None, description="Habitat description.")
#
#
# # --- Media & provenance ------------------------------------------------
# associatedMedia: str | None = Field( default=None, description="URI(s) of associated media (e.g. label/specimen images).")
# associatedReferences: str | None = Field( default=None, description="Associated literature references.")
# verbatimLabel: str | None = Field( default=None, description="Full verbatim transcription of the specimen label text.")
# source: str | None = Field( default=None, description="Provenance of the record / data source (NOT a Darwin Core term; needs explicit mapping).",)
