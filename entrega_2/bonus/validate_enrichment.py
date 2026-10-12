
from rdflib import Graph, Namespace, RDF

INPUT_PATH = "enrichment.ttl"

RES = Namespace(
    "http://uniandes.edu.co/wsproject2026/vocab/lit#"
)
RBO = Namespace(
    "http://uniandes.edu.co/wsproject2026/vocab/ontology#"
)

g = Graph()
g.parse(INPUT_PATH, format="turtle")

print("Archivo Turtle válido.")
print("Tripletas:", len(g))

checks = {
    "Géneros": (None, RDF.type, RES.Genre),
    "Instrumentos": (None, RDF.type, RES.Instrument),
    "Fuentes": (None, RDF.type, RES.TextSource),
    "Hechos extraídos": (None, RDF.type, RES.ExtractedFact),
}

for label, pattern in checks.items():
    print(f"{label}: {len(list(g.triples(pattern)))}")

print(
    "Evidencias:",
    len(list(g.triples((None, RBO.evidenceQuote, None))))
)
print(
    "Relaciones con fuente:",
    len(list(g.triples((None, RBO.extractedFrom, None))))
)
