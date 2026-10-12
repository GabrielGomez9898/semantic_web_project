
import csv
import json
import hashlib
import re
import unicodedata

from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD

# -----------------------------------
# Configuración
# -----------------------------------

FACTS_PATH = "extracted_facts_v3.json"
ARTISTS_PATH = "artists_catalog.csv"
OUTPUT_PATH = "enrichment.ttl"

RES = Namespace(
    "http://uniandes.edu.co/wsproject2026/vocab/lit#"
)
RBO = Namespace(
    "http://uniandes.edu.co/wsproject2026/vocab/ontology#"
)

g = Graph()
g.bind("res", RES)
g.bind("rbo", RBO)
g.bind("rdf", RDF)
g.bind("rdfs", RDFS)

# -----------------------------------
# Funciones auxiliares
# -----------------------------------

def normalize_name(value):
    value = unicodedata.normalize("NFKC", str(value))
    return " ".join(value.casefold().split())


def make_uri(prefix, value):
    normalized = normalize_name(value)

    slug = unicodedata.normalize("NFKD", normalized)
    slug = slug.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", slug).strip("_")

    digest = hashlib.sha1(
        normalized.encode("utf-8")
    ).hexdigest()[:10]

    return RES[f"{prefix}_{slug or 'entity'}_{digest}"]


def source_uri(url):
    digest = hashlib.sha1(
        url.encode("utf-8")
    ).hexdigest()

    return RES[f"TextSource_{digest}"]


# -----------------------------------
# Índice de artistas existentes
# -----------------------------------

artists_by_name = {}

with open(ARTISTS_PATH, newline="", encoding="utf-8") as file:
    for row in csv.DictReader(file):
        name = row.get("artist_name", "").strip()
        mbid = row.get("artist_mbid", "").strip()

        if name and mbid:
            key = normalize_name(name)
            artists_by_name.setdefault(key, []).append(
                RES[f"Artist_{mbid}"]
            )


def resolve_person(name):
    """Reutiliza el artista si la coincidencia es inequívoca."""

    matches = artists_by_name.get(normalize_name(name), [])

    if len(matches) == 1:
        return matches[0]

    # Si no hay coincidencia inequívoca, no asociamos el nombre
    # a un artista existente arbitrariamente.
    person = make_uri("ExternalPerson", name)

    g.add((person, RDF.type, RES.Person))
    g.add((person, RDFS.label, Literal(name, lang="en")))

    return person


# -----------------------------------
# Mapeo de relaciones extraídas
# -----------------------------------

RELATIONS = {
    "associated_genre": ("genre", RBO.associatedWithGenre),
    "influenced_by_genre": ("genre", RBO.influencedByGenre),
    "plays_instrument": ("instrument", RBO.playsInstrument),
    "influenced_by_artist": ("person", RBO.influencedByArtist),
    "collaborated_with": ("person", RBO.collaboratedWith),
    "produced_by": ("person", RBO.producedBy),
}

# -----------------------------------
# Carga de hechos
# -----------------------------------

with open(FACTS_PATH, encoding="utf-8") as file:
    data = json.load(file)

seen_facts = set()
accepted = 0

for artist_data in data["artists"]:
    mbid = artist_data["artist_mbid"]
    artist_uri = RES[f"Artist_{mbid}"]
    source_url = artist_data.get("source_url", "").strip()
    source_text = artist_data.get("source_text", "")

    if not source_url:
        print(
            "Se omite artista sin URL:",
            artist_data["artist_name"]
        )
        continue

    source = source_uri(source_url)

    g.add((source, RDF.type, RES.TextSource))
    g.add((
        source,
        RBO.sourceUrl,
        Literal(source_url, datatype=XSD.anyURI)
    ))

    for fact in artist_data.get("facts", []):
        relation = fact.get("relation")
        target_name = fact.get("target_name", "").strip()
        quote = fact.get("evidence_quote", "")

        if relation not in RELATIONS or not target_name:
            continue

        # Validación adicional de evidencia literal
        if not quote or quote not in source_text:
            print(
                "Evidencia no válida:",
                artist_data["artist_name"],
                target_name
            )
            continue

        entity_type, predicate = RELATIONS[relation]

        if entity_type == "genre":
            target_uri = make_uri("Genre", target_name)
            g.add((target_uri, RDF.type, RES.Genre))
            g.add((
                target_uri,
                RDFS.label,
                Literal(target_name, lang="en")
            ))

        elif entity_type == "instrument":
            # Algunos valores contienen varios instrumentos separados
            # por "/". Separamos solo para esta relación.
            instruments = [
                part.strip()
                for part in target_name.split("/")
                if part.strip()
            ]

            for instrument_name in instruments:
                target_uri = make_uri(
                    "Instrument", instrument_name
                )

                g.add((target_uri, RDF.type, RES.Instrument))
                g.add((
                    target_uri,
                    RDFS.label,
                    Literal(instrument_name, lang="en")
                ))

                fact_key = (
                    str(artist_uri),
                    str(predicate),
                    str(target_uri),
                    source_url,
                    quote
                )

                if fact_key in seen_facts:
                    continue

                seen_facts.add(fact_key)
                g.add((artist_uri, predicate, target_uri))

                record = URIRef(
                    "http://uniandes.edu.co/wsproject2026/vocab/lit#"
                    "ExtractedFact_"
                    + hashlib.sha1(
                        "|".join(fact_key).encode("utf-8")
                    ).hexdigest()
                )

                g.add((record, RDF.type, RES.ExtractedFact))
                g.add((record, RDF.subject, artist_uri))
                g.add((record, RDF.predicate, predicate))
                g.add((record, RDF.object, target_uri))
                g.add((record, RBO.evidenceQuote, Literal(quote)))
                g.add((record, RBO.extractedFrom, source))

                accepted += 1

            continue

        else:
            target_uri = resolve_person(target_name)

        fact_key = (
            str(artist_uri),
            str(predicate),
            str(target_uri),
            source_url,
            quote
        )

        if fact_key in seen_facts:
            continue

        seen_facts.add(fact_key)

        # Relación directa en el grafo
        g.add((artist_uri, predicate, target_uri))

        # Registro de procedencia y evidencia
        record = URIRef(
            "http://uniandes.edu.co/wsproject2026/vocab/lit#"
            "ExtractedFact_"
            + hashlib.sha1(
                "|".join(fact_key).encode("utf-8")
            ).hexdigest()
        )

        g.add((record, RDF.type, RES.ExtractedFact))
        g.add((record, RDF.subject, artist_uri))
        g.add((record, RDF.predicate, predicate))
        g.add((record, RDF.object, target_uri))
        g.add((record, RBO.evidenceQuote, Literal(quote)))
        g.add((record, RBO.extractedFrom, source))

        accepted += 1

# -----------------------------------
# Serialización
# -----------------------------------

g.serialize(destination=OUTPUT_PATH, format="turtle")

print("Enriquecimiento generado correctamente.")
print("Tripletas en enrichment.ttl:", len(g))
print("Relaciones extraídas aceptadas:", accepted)
print("Archivo:", OUTPUT_PATH)
