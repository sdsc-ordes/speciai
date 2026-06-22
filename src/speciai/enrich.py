
from geopy.geocoders import Nominatim
from geopy.location import Location
import pycountry_convert as pc

OSMField = str
DCTerm = str
OSM_ADDRESS_MAPPINGS: dict[OSMField, DCTerm] = {
    'village': 'locality',
    'city': 'locality',
    'country_code': 'countryCode',
    'state': 'stateProvince',
    'country': 'country'
}

doc = {
  "location": ["CH SH.", "ifcrishausen", "Chlosterfeid,"],
  "catalogNumber": [ "ETHZ-ENT", "D", "0082619", "OO" ],
  "verbatimCoordinate": "Koord. .686.7/288.5",
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

#NOTE: This is hard-coded since all records use this system so far.
output['geodeticDatum'] = "WGS84"
output['verbatimCoordinateSystem'] = "WGS84"
output['verbatimCoordinates'] = doc['verbatimCoordinates']

output |= parse_address(loc)

#NOTE: These are not (yet) covered:
# coordinateUncertaintyInMeters: float | None = Field( default=None, ge=0, description="Horizontal coordinate uncertainty, in metres.")
# verbatimCoordinateSystem: str | None = Field( default=None, description="Coordinate system of the verbatim coordinates.")
# minimumElevationInMeters: float | None = Field( default=None, description="Minimum elevation, in metres.")
# maximumElevationInMeters: float | None = Field( default=None, description="Maximum elevation, in metres.")

# catalog
output["catalogNumber"] = doc["catalogNumber"]

#NOTE: These are not (yet) covered:
# collectionCode: str | None = Field( default=None, description="Name/code identifying the collection.")
# otherCatalogNumbers: str | None = Field( default=None, description="Additional catalog numbers (e.g. previous IDs).")
# preparations: str | None = Field( default=None, description="Preparation/preservation method (e.g. 'pinned', 'in ethanol').")
# partOfOrganism: str | None = Field( default=None, description="Which part of the organism the record represents (NOT a Darwin Core term; needs explicit mapping).",)

# species
#    # --- Taxonomy (Identification -> Taxon) --------------------------------
#    scientificName: str | None = Field( default=None, description="Full scientific name, with authorship if known.")
#    scientificNameAuthorship: str | None = Field( default=None, description="Authorship of the scientific name.")
#    kingdom: str | None = Field(default=None, description="Taxonomic kingdom.")
#    phylum: str | None = Field(default=None, description="Taxonomic phylum.")
#    order: str | None = Field(default=None, description="Taxonomic order.")
#    family: str | None = Field(default=None, description="Taxonomic family.")
#    subfamily: str | None = Field(default=None, description="Taxonomic subfamily.")
#    tribe: str | None = Field(default=None, description="Taxonomic tribe.")
#    genus: str | None = Field(default=None, description="Taxonomic genus.")
#    specificEpithet: str | None = Field(default=None, description="Species epithet.")
#    infraspecificEpithet: str | None = Field( default=None, description="Subspecies / infraspecific epithet.")
#    taxonRank: str | None = Field( default=None, description="Rank of the most specific name (e.g. 'species').")
#    taxonId: str | None = Field( default=None, description="Taxon identifier (DwC canonical term is 'taxonID'; kept as 'taxonId' to match target headers).",)
#    associatedTaxa: str | None = Field( default=None, description="Other taxa associated with the specimen (e.g. host).")
#    caste: str | None = Field( default=None, description="Social caste of the specimen, e.g. 'worker', 'queen' (Darwin Core term for eusocial insects).",)

# date

# coordinates

#
#
#    # --- Determination -----------------------------------------------------
#    identifiedBy: str | None = Field( default=None, description="Person(s) who determined the taxon.")
#    dateIdentified: str | None = Field( default=None, description="Date of determination (ISO 8601; may be partial).")
#    verbatimIdentification: str | None = Field( default=None, description="Verbatim taxonomic identification as written on the label.")
#
#    # --- Type status -------------------------------------------------------
#    typeStatus: str | None = Field( default=None, description="Nomenclatural type status (e.g. 'holotype').")
#    typeDesignatedBy: str | None = Field( default=None, description="Agent who designated the type status (NOT a Darwin Core term; needs explicit mapping).",)
#    typifiedName: str | None = Field( default=None, description="Scientific name based on this type specimen (Darwin Core nomenclature term).")
#
#    # --- Occurrence --------------------------------------------------------
#    recordedBy: str | None = Field( default=None, description="Collector(s) of the specimen.")
#    sex: str | None = Field(default=None, description="Sex of the specimen.")
#    lifeStage: str | None = Field( default=None, description="Life stage (e.g. 'adult', 'larva').")
#    organismRemarks: str | None = Field( default=None, description="Free-text remarks about the organism.")
#
#    # --- Event (CollectingEvent) -------------------------------------------
#    eventDate: str | None = Field( default=None, description="Interpreted collection date (ISO 8601; may be partial or a range).")
#    verbatimEventDate: str | None = Field( default=None, description="Verbatim collection date as written on the label.")
#    habitat: str | None = Field(default=None, description="Habitat description.")
#
#
#    # --- Media & provenance ------------------------------------------------
#    associatedMedia: str | None = Field( default=None, description="URI(s) of associated media (e.g. label/specimen images).")
#    associatedReferences: str | None = Field( default=None, description="Associated literature references.")
#    verbatimLabel: str | None = Field( default=None, description="Full verbatim transcription of the specimen label text.")
#    source: str | None = Field( default=None, description="Provenance of the record / data source (NOT a Darwin Core term; needs explicit mapping).",)
