from pathlib import Path
from rdflib import Graph
import sys


# Ruta del proyecto
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Ruta de la ontología
ONTOLOGY_PATH = PROJECT_ROOT / "dataset" / "modelo_conceptual" / "ontology.ttl"


def validar_ontologia():
    print(f"Validando: {ONTOLOGY_PATH}")

    if not ONTOLOGY_PATH.exists():
        print("❌ No se encontró el archivo ontology.ttl")
        print(f"Ruta buscada: {ONTOLOGY_PATH}")
        sys.exit(1)

    graph = Graph()

    try:
        graph.parse(ONTOLOGY_PATH, format="turtle")

        print("✅ Ontology válida")
        print(f"📊 Triples encontrados: {len(graph)}")

    except Exception as e:
        print("❌ Ontology inválida")
        print("\nError:")
        print(e)
        sys.exit(1)


if __name__ == "__main__":
    validar_ontologia()