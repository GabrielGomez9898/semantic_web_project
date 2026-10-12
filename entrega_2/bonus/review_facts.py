
import json
from collections import Counter

INPUT_PATH = "extracted_facts.json"

with open(INPUT_PATH, encoding="utf-8") as file:
    data = json.load(file)

artists = data["artists"]

relation_counts = Counter()
total_facts = 0
artists_with_facts = 0

for artist in artists:
    facts = artist.get("facts", [])

    total_facts += len(facts)

    if facts:
        artists_with_facts += 1

    for fact in facts:
        relation_counts[fact["relation"]] += 1

print("Artistas procesados:", len(artists))
print("Artistas con hechos:", artists_with_facts)
print("Total de hechos aceptados:", total_facts)

print("\nHechos por tipo de relación:")
for relation, count in relation_counts.most_common():
    print(f"  {relation}: {count}")

print("\nEjemplos de hechos:")
shown = 0

for artist in artists:
    for fact in artist.get("facts", []):
        print(f"\nArtista: {artist['artist_name']}")
        print(f"Relación: {fact['relation']}")
        print(f"Entidad: {fact['target_name']}")
        print(f"Evidencia: {fact['evidence_quote']}")
        print(f"Fuente: {artist['source_url']}")

        shown += 1
        if shown >= 5:
            break

    if shown >= 5:
        break
