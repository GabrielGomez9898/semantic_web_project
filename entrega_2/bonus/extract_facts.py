
import csv
import json
import os
import time

from openai import OpenAI

# -----------------------------------
# Configuración
# -----------------------------------

INPUT_PATH = "artist_texts.csv"
OUTPUT_PATH = "extracted_facts_v2.json"

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

client = OpenAI()

# -----------------------------------
# Esquema de salida
# -----------------------------------

FACT_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "relation": {
                        "type": "string",
                        "enum": [
                            "associated_genre",
                            "influenced_by_genre",
                            "influenced_by_artist",
                            "plays_instrument",
                            "collaborated_with",
                            "produced_by"
                        ]
                    },
                    "target_name": {
                        "type": "string"
                    },
                    "evidence_quote": {
                        "type": "string"
                    }
                },
                "required": [
                    "relation",
                    "target_name",
                    "evidence_quote"
                ],
                "additionalProperties": False
            }
        }
    },
    "required": ["facts"],
    "additionalProperties": False
}

INSTRUCTIONS = """
Eres un extractor estricto de información para un grafo de conocimiento musical.

Analiza exclusivamente el texto fuente proporcionado. Extrae únicamente hechos explícitos y verificables sobre el artista analizado.

RELACIONES PERMITIDAS:

- associated_genre: género musical al que pertenece, con el que se identifica o que se asocia explícitamente al artista.
- influenced_by_genre: género musical que influyó explícitamente en el artista o en su música.
- influenced_by_artist: artista o grupo musical que influyó explícitamente en el artista analizado o en su música.
- plays_instrument: instrumento musical físico que toca explícitamente el artista analizado o un integrante identificado de ese grupo.
- collaborated_with: artista o grupo con el que el artista analizado colaboró musicalmente de forma explícita.
- produced_by: persona o entidad identificada explícitamente como productora musical de grabaciones del artista.

REGLAS OBLIGATORIAS:

1. No utilices conocimiento externo ni inventes información.
2. Cada hecho debe tener una cita literal que demuestre específicamente la relación indicada.
3. La cita debe aparecer exactamente en el texto fuente.
4. Una simple mención de una persona, banda, género o instrumento no demuestra una relación.
5. No confundas colaboración, pertenencia a una banda, participación en una gira o trabajo compartido con influencia artística.
6. influenced_by_artist exige evidencia explícita de influencia artística o musical. No infieras influencia porque dos artistas tocaron juntos, compartieron integrantes o pertenecieron a bandas relacionadas.
7. influenced_by_genre exige que el texto indique explícitamente que un género influyó en el artista o en su música. Una mención de un género no es suficiente.
8. associated_genre exige una asociación musical explícita. No infieras géneros a partir del nombre del artista ni de una descripción ambigua.
9. plays_instrument solo admite instrumentos físicos concretos, como guitar, bass, piano, drums, organ, keyboard, percussion, violin o saxophone.
10. No clasifiques vocals, singer, vocalist, DJ, producer, percussionist, multi-instrumentalist, painter, songwriter ni otras profesiones o funciones como instrumentos. Si la información no corresponde a una relación permitida, omítela.
11. Si el texto describe integrantes de una banda, solo extrae un instrumento cuando la cita identifique explícitamente al integrante y su instrumento. No atribuyas automáticamente a todos los integrantes los instrumentos mencionados.
12. collaborated_with requiere evidencia de colaboración musical real. No basta con que una persona haya pertenecido anteriormente a otra banda o haya sido mencionada junto al artista.
13. produced_by requiere evidencia explícita de producción musical. No confundas productor con integrante, compositor, diseñador gráfico u otro colaborador.
14. target_name debe contener únicamente el nombre de la entidad relacionada o el nombre concreto del instrumento o género. No incluyas explicaciones ni listas de conceptos heterogéneos.
15. No dividas automáticamente expresiones ambiguas para inventar varias relaciones. Si no puedes identificar cada entidad y su relación con certeza, omite el hecho.
16. Si una frase permite varias interpretaciones o no demuestra claramente la relación solicitada, no extraigas el hecho.
17. No extraigas hechos basados únicamente en el título de la página.
18. Es preferible devolver pocos hechos correctos que muchos hechos dudosos.
19. Si no encuentras hechos que cumplan todas estas reglas, devuelve una lista vacía.
"""

# -----------------------------------
# Persistencia y reanudación
# -----------------------------------

def load_results():
    if not os.path.exists(OUTPUT_PATH):
        return []

    with open(OUTPUT_PATH, encoding="utf-8") as file:
        return json.load(file).get("artists", [])


def save_results(results):
    temporary_path = OUTPUT_PATH + ".tmp"

    with open(temporary_path, "w", encoding="utf-8") as file:
        json.dump(
            {"artists": results},
            file,
            ensure_ascii=False,
            indent=2
        )

    os.replace(temporary_path, OUTPUT_PATH)


# -----------------------------------
# Extracción con OpenAI
# -----------------------------------

def extract_facts(text):
    response = client.responses.create(
        model=MODEL,
        instructions=INSTRUCTIONS,
        input=(
            "Extrae hechos verificables del siguiente texto.\n\n"
            f"TEXTO FUENTE:\n{text}"
        ),
        text={
            "format": {
                "type": "json_schema",
                "name": "music_facts",
                "strict": True,
                "schema": FACT_SCHEMA
            }
        }
    )

    if not response.output_text:
        raise ValueError("La API no devolvió contenido.")

    return json.loads(response.output_text)["facts"]


def main():
    with open(INPUT_PATH, newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))

    results = load_results()
    processed_ids = {
        item["artist_mbid"] for item in results
    }

    eligible = [
        row for row in rows
        if row.get("status") == "ok"
        and row.get("text", "").strip()
    ]

    print("Biografías disponibles:", len(eligible))
    print("Artistas ya procesados:", len(processed_ids))

    for index, row in enumerate(eligible, start=1):
        artist_id = row["artist_mbid"]

        if artist_id in processed_ids:
            continue

        text = row["text"].strip()

        print(
            f"[{index}/{len(eligible)}] "
            f"Extrayendo: {row['artist_name']}"
        )

        try:
            facts = extract_facts(text)

            # Verificación adicional: la evidencia debe aparecer
            # literalmente en el texto que recibimos.
            valid_facts = []

            for fact in facts:
                quote = fact["evidence_quote"]

                if (
                    quote
                    and quote in text
                    and fact["target_name"].strip()
                ):
                    valid_facts.append(fact)
                else:
                    print(
                        "  Hecho descartado: "
                        "la evidencia no coincide literalmente."
                    )

            result = {
                "artist_mbid": artist_id,
                "artist_name": row["artist_name"],
                "page_title": row["page_title"],
                "source_url": row["source_url"],
                "source_text": text,
                "facts": valid_facts
            }

            results.append(result)
            processed_ids.add(artist_id)
            save_results(results)

            print(
                f"  Hechos aceptados: {len(valid_facts)}"
            )

            time.sleep(1)

        except Exception as error:
            print(f"  Error: {error}")
            print("  Se podrá reintentar en otra ejecución.")
            continue

    print("\nExtracción terminada.")
    print("Artistas procesados:", len(results))
    print("Archivo:", OUTPUT_PATH)


if __name__ == "__main__":
    main()
