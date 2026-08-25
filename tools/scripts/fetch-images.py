#!/usr/bin/env python
"""Download the pinned benchmark sample of specimen photos from the ETH export.

Files are named after the nahima asset id, and `manifest.csv` maps filename -> URL so
`run-pipeline.py` can trace each record back to the sheet row describing its photo.

ASSETS is fixed rather than computed so every batch scores the same photos and results
stay comparable across runs; SAMPLE decides how many of them to take. It was chosen greedily, taking at each step the photo
adding the most unseen traits across family, genus, collector, determiner, country, type
status, decade and label size. That yields 100 photos covering 42 families, 96 genera, 87
collectors and 72 countries, where the first 100 rows of the export cover a small
fraction of that -- the sheet is grouped by collection, so any positional sample
measures a few families in a few hands.

    uv run --with openpyxl tools/scripts/fetch-images.py
"""

import csv
from pathlib import Path

import requests
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[2]
SHEET = ROOT / "examples" / "eth-output.xlsx"
DESTINATION = ROOT / "examples" / "bugs"
# How many of ASSETS to use. The list is in greedy order -- each entry was picked for
# adding the most unseen traits -- so the first N is itself the most varied N available.
SAMPLE = 25
# One per line, family / collector. 100 photos covering 42 families, 96 genera,
# 87 collectors and 72 countries; the first 25 cover 25 families and 24 collectors.
ASSETS = (
    "137671",  # Zygaenidae / Widmer, Luzia
    "973461",  # Carabidae / Tarrier, Michel (*1947)
    "598326",  # Psychidae / Httenschwiler, Sereina
    "600568",  # Chrysididae / Nadig, Adolf (1877-1960)
    "867300",  # Crambidae / Zeller
    "868708",  # Noctuidae / Grunder, Hans-Ueli (*194
    "835048",  # Scoliidae / Hoffmann, Fritz
    "889774",  # Leucospidae / Friese, Heinrich (1860-1
    "718429",  # Andrenidae / von Schulthess-Rechberg,
    "749019",  # Megachilidae / Sausa
    "834972",  # Papilionidae / Zaugg, Paul (1913-1985)
    "203703",  # Geometridae / Noack, Herbert
    "709946",  # Phryganeidae / Rutz, H.
    "626660",  # Lepidostomatidae / Malicky, Hans (*1935)
    "780593",  # Histeridae / Kardasch, Gregor
    "835806",  # Formicidae / Seitz, Oliver
    "964503",  # Bombyliidae / ?
    "889977",  # Pyralidae / Ebert, Gnter (*1935)
    "682102",  # Apidae / von Buttel-Reepen, Hugo
    "791840",  # Libellulidae / Georg, N.
    "656955",  # Aeshnidae / Krebs, Albert (*1931)
    "825953",  # Pompilidae / Minozzi (Menozzi), Carlo
    "813086",  # Gyrinidae / Wolf, Johann Peter Dr.
    "824821",  # Rhysodidae / Leder, Hans (1843-1921)
    "886256",  # Halictidae / Reith, Martin
    "867937",  # Colletidae / Heller, Philipp
    "863177",  # Chrysididae / Mavromoustakis, G.A. (*1
    "626592",  # Argidae / Mader, Leopold (1886-196
    "687707",  # Ichneumonidae / Aeschlimann, Jean-Paul
    "681022",  # Chrysididae / Junod, Henri Alexandre
    "951194",  # Pieridae / Page, Malcolm G.P. (*195
    "947753",  # Nymphalidae / Horak, Egon (*1937)
    "260383",  # Psychidae / Httenschwiler, Peter (1
    "670979",  # Saturniidae / Ruckstuhl, P.
    "694618",  # Psychidae / Kallies, Axel
    "579417",  # Chrysididae / Bieri, Simon (*1970)
    "700333",  # Chrysididae / Nadig, Adolf (1910-2003)
    "662874",  # Chrysididae / Sedivy, Claudio | Praz,
    "657091",  # Chrysididae / Pillich, Ferenc (1876-19
    "634335",  # Chrysididae / Merz, Bernhard (1963-202
    "693249",  # Chrysididae / Krger, Georg C.
    "699732",  # Chrysididae / Thurner, Josef (1889-197
    "606607",  # Chrysididae / Praz, Christophe | Sediv
    "683703",  # Chrysididae / Enslin, Eduard (1879-197
    "775011",  # Chrysididae / Mochi, A.
    "716854",  # Pteromalidae / ?
    "791826",  # Histeridae / Reitter, Edmund (1845-19
    "972770",  # Carabidae / Cornu
    "836653",  # Lucanidae / ?
    "884233",  # Plutellidae / Hnseler, Ernst (1925-20
    "870923",  # Crabronidae / Neumeyer, Rainer (*1952)
    "843299",  # Histeridae / Donis, Camille (1917-198
    "873596",  # Histeridae / Kricheldorff, A.
    "890169",  # Pyralidae / Bttiker, Willi (1921-20
    "856324",  # Chrysididae / Bttcher, Ernst August
    "886847",  # Chrysididae / Hoffmann
    "894970",  # Mycetophilidae / ?
    "983203",  # Bombyliidae / Forel, August Henry (184
    "710092",  # Heptageniidae / ?
    "719255",  # Mutillidae / ?
    "634613",  # Chrysididae / ?
    "651266",  # Staphylinidae / Heer, Oswald (1809-1883)
    "648674",  # Hydrophilidae / ?
    "710836",  # Pseudostigmatidae / Gbelmann, Gabuser
    "706227",  # Scarabaeidae / Holub, Emil (1847-1902)
    "849292",  # Papilionidae / Haugum, J.
    "868290",  # Papilionidae / Djean, P.
    "880968",  # Papilionidae / Gugelmann, Wilhelm
    "867964",  # Papilionidae / Hf.
    "834158",  # Papilionidae / Sidler, Peter
    "854831",  # Papilionidae / Rolle, Herman (1864-1929
    "859241",  # Papilionidae / Kern, F.
    "961946",  # Carabidae / Cumming, R.B.
    "885064",  # Scoliidae / Buchwald
    "946773",  # Pieridae / ?
    "944410",  # Pieridae / Fassl, Anton Hermann (18
    "946724",  # Pieridae / Lwandi, Peter
    "947723",  # Pieridae / Farmer, Ren (1902-1990)
    "949715",  # Pieridae / Holliger, Kurt (1930-201
    "944469",  # Pieridae / Landolt, Eduard Heinrich
    "954750",  # Nymphalidae / Lorez, C.F.
    "954556",  # Nymphalidae / Van Patten
    "980292",  # Nymphalidae / Gerstner, H.
    "638970",  # Saturniidae / Gehrig, Hansruedi
    "742513",  # Psychidae / Parpan, S. + M.
    "722349",  # Psychidae / Lichtenberger, Franz (*1
    "652520",  # Chrysididae / Enslin, Eduard (1879-197
    "796661",  # Chrysididae / Salvioni, A.
    "676478",  # Chrysididae / Mller, Andreas (*1963)
    "588307",  # Chrysididae / Stubli, Anna
    "781110",  # Chrysididae / Linsenmaier, Walter (191
    "594832",  # Chrysididae / Steck, Theodor (1857-193
    "663642",  # Chrysididae / Vilarrubia, A.
    "670223",  # Chrysididae / Schischma, J.
    "617500",  # Andrenidae / Sauter, Willi (1928-2020
    "643774",  # Chrysididae / von Demelt, Carl (1913-1
    "827578",  # Histeridae / Leder, Hans (1843-1921)
    "844075",  # Histeridae / ?
    "818600",  # Scoliidae / Junod, Henri Alexandre
    "813112",  # Crambidae / ?
)


def photos():
    """Yield (asset id, url) for each row linking exactly one photo."""
    rows = load_workbook(SHEET, read_only=True, data_only=True).active.values
    media = next(rows).index("associatedMedia")
    for row in rows:
        url = str(row[media]).strip()
        if "|" not in url:
            yield url.split("/")[-3], url


def selected() -> list[tuple[str, str]]:
    """Look up the URL of every pinned asset, in ASSETS order.

    Scans the whole sheet, since a pinned id says nothing about where its row sits.
    Anything ASSETS names that the sheet no longer links is reported, not skipped
    silently: a shrinking benchmark would quietly change what the scores mean.
    """
    wanted = ASSETS[:SAMPLE]
    found = {asset: url for asset, url in photos() if asset in set(wanted)}
    for asset in wanted:
        if asset not in found:
            print(f"{asset} is no longer in the sheet")
    return [(asset, found[asset]) for asset in wanted if asset in found]


def download(asset: str, url: str) -> tuple[str, str] | None:
    """Save one photo, reusing an earlier download; return its manifest row or None."""
    target = DESTINATION / f"{asset}.jpg"
    if not target.exists():
        print(f"{target.name} <- {url}")
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
        except requests.RequestException as error:
            print(f"    failed: {error}")
            return None
        target.write_bytes(response.content)
    return target.name, url


def main() -> int:
    """Download the pinned sample and write the manifest."""
    DESTINATION.mkdir(parents=True, exist_ok=True)

    fetched = [download(asset, url) for asset, url in selected()]
    rows = [row for row in fetched if row]

    manifest = DESTINATION / "manifest.csv"
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows([("filename", "url"), *rows])

    print(f"{len(rows)} photos in {DESTINATION}, manifest -> {manifest}")
    return 1 if len(rows) < len(fetched) else 0


if __name__ == "__main__":
    raise SystemExit(main())
