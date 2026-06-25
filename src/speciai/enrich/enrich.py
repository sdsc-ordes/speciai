from speciai.enrich.authors import enrich_authorships
from speciai.enrich.geo import enrich_locations
from speciai.enrich.species import enrich_species
from speciai.schema import DarwinCoreRecord



def enrich_record(doc: dict[str, list[str] | str]) -> dict[str, str | None]:

    output: dict[str, str | None] = {}

    output |= enrich_locations(doc['location'])

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

    output |= enrich_species(doc['scientificName'])
    #NOTE: These are not (yet) covered:
    # infraspecificEpithet: str | None = Field( default=None, description="Subspecies / infraspecific epithet.")
    # taxonId: str | None = Field( default=None, description="Taxon identifier (DwC canonical term is 'taxonID'; kept as 'taxonId' to match target headers).",)
    # associatedTaxa: str | None = Field( default=None, description="Other taxa associated with the specimen (e.g. host).")
    # caste: str | None = Field( default=None, description="Social caste of the specimen, e.g. 'worker', 'queen' (Darwin Core term for eusocial insects).",)

    output |= enrich_authorships(doc['authorship'], output.get('scientificNameAuthorship'))

    return output

if __name__ == "__main__":
    doc = {
      "location": ["CH SH.", "ifcrishausen", "Chlosterfeid,"],
      "verbatimCoordinates": "Koord. .686.7/288.5",
      "catalogNumber": [ "ETHZ-ENT", "D", "0082619", "OO" ],
      "authorship": [
            "(Linnaeus, 1758)",
            "leg. L. Vidmer",
            "det. L. Widmer",
            "det. L. Widmer 1999",
            "Raymond Guenin 2017",
      ],
      "scientificName": [
            "Zygaena",
            "filipendalae",
            "Zygaena",
            "filipendulae",
            "Zygaenidae:",
            "Zygaeninae"
        ],
    }
    enriched = enrich_record(doc)
    record = DarwinCoreRecord(**enriched)
    print(record.model_dump_json(indent=2, exclude_none=True))

#NOTE: These are not (yet) covered:
# verbatimIdentification: str | None = Field( default=None, description="Verbatim taxonomic identification as written on the label.")
# sex: str | None = Field(default=None, description="Sex of the specimen.")
# lifeStage: str | None = Field( default=None, description="Life stage (e.g. 'adult', 'larva').")
# organismRemarks: str | None = Field( default=None, description="Free-text remarks about the organism.")
#
# # --- Event (CollectingEvent) -------------------------------------------
# habitat: str | None = Field(default=None, description="Habitat description.")
#
#
# # --- Media & provenance ------------------------------------------------
# associatedMedia: str | None = Field( default=None, description="URI(s) of associated media (e.g. label/specimen images).")
# associatedReferences: str | None = Field( default=None, description="Associated literature references.")
# verbatimLabel: str | None = Field( default=None, description="Full verbatim transcription of the specimen label text.")
# source: str | None = Field( default=None, description="Provenance of the record / data source (NOT a Darwin Core term; needs explicit mapping).",)
