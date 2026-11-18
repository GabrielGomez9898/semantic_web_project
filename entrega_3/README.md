# Entrega 3 — Grafo de conocimiento en Neo4j

## Punto 1. Carga del grafo de conocimiento en Neo4j

La ontología y las instancias de la Etapa 2 se cargan en Neo4j (AuraDB) con el mismo mecanismo del taller:
`rdflib` → filas extraídas de los triples RDF → `UNWIND` + `MERGE` por lotes con el driver de Python.
Luego se verifica con Cypher que las entidades y relaciones principales se recuperan correctamente.

### Estructura

```
entrega_3/
├── data/
│   ├── ontology.ttl        # Ontología de la Etapa 2 (RDFS/OWL + clases del bonus)
│   ├── instances.ttl       # Instancias (100k canciones, 27k artistas, países, tags, similitudes)
│   └── enrichment.ttl      # Bonus Etapa 2: géneros/instrumentos/personas extraídos de textos
├── notebooks/
│   └── 01_carga_grafo_neo4j.ipynb   # Carga + verificación (ejecutar de arriba a abajo)
├── scripts/
│   └── consultas_verificacion.cypher # Las consultas de verificación para Neo4j Browser / Aura
└── .env.example            # Plantilla de credenciales
```

### Cómo ejecutar

1. Crear una instancia **AuraDB Free** y guardar URI, usuario y contraseña.
2. Credenciales: copiar `.env.example` a `entrega_3/.env` y completarlo (`NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`).
   El notebook las lee de ahí (no las pide por consola). El `.env` está excluido de git.
3. Instalar dependencias (desde la raíz del repo): `pip install -r requirements.txt`
4. Abrir `notebooks/01_carga_grafo_neo4j.ipynb` y ejecutar todas las celdas.
   - En **Google Colab**: el notebook pide subir los tres `.ttl` y el `.env`.

La carga es idempotente (`MERGE`). Para empezar de cero, poner `REINICIAR = True` en la sección 3.1
(solo borra nodos con etiquetas de este proyecto).

### Modelo en Neo4j

| Nodos | Relaciones |
|---|---|
| `(:Track:CreativeWork)` 100.000 | `(:Track)-[:SUNG_BY]->(:Artist)` 100.000 |
| `(:Artist:Person)` 27.378 | `(:Artist)-[:ORIGIN]->(:Country)` 22.982 |
| `(:Country:GeographicalEntity)` 138 | `(:Track)-[:SIMILAR_TO {score}]->(:Track)` 6.380 |
| `(:Tag)` 245 | `(:Track)-[:HAS_TAG]->(:Tag)` 475 |
| `(:Genre)` 23, `(:Instrument)` 6, `(:Person)` 5 (bonus) | `ASSOCIATED_WITH_GENRE`, `INFLUENCED_BY_GENRE`, `PLAYS_INSTRUMENT`, `PRODUCED_BY`, `COLLABORATED_WITH` `{evidence, sources}` |
| Ontología: `(:OntologyClass)`, `(:OntologyProperty)`, `(:Datatype)`, `(:Restriction)` | `SUBCLASS_OF`, `DOMAIN`, `RANGE`, `SUBPROPERTY_OF`, `INVERSE_OF`, `DISJOINT_WITH`, `CHAIN_STEP`, `ON_PROPERTY`, `ON_CLASS` |

Total del proyecto: **127.843 nodos y 129.968 relaciones** (dentro de los límites de AuraDB Free: 200k nodos / 400k relaciones).

Decisiones principales:

- La jerarquía `subClassOf` se materializa como etiquetas múltiples (un `Track` también es `CreativeWork`).
- La similitud reificada con nodos en blanco (`res:Similarity`) se convierte en la relación `SIMILAR_TO` con propiedad `score`.
  Solo se cargan las 6.380 similitudes entre canciones del dataset; 54.582 apuntan a canciones externas sin datos.
- Los `res:ExtractedFact` del bonus se guardan como propiedades `evidence`/`sources` de la relación que respaldan.
- Todas las entidades conservan su URI original (`uri`, con restricción de unicidad).
- `year = "0"` se interpreta como año desconocido y no se guarda.

### Observaciones sobre la ontología de la Etapa 2 (detectadas automáticamente en el notebook)

- 3 axiomas usan `rdf:subClassOf` en lugar de `rdfs:subClassOf` (se interpretan como `rdfs:subClassOf`).
- `owl:disjointWith` referencia `res:Persona`, que no existe (la clase es `res:Person`).
- `res:Similarity`, `rbo:hasSimilarity`, `rbo:similarTrack` y `rbo:similarityScore` se usan en las instancias pero no están declarados.
- 3 canciones no tienen título (incumplen `owl:cardinality 1` sobre `rbo:title`).
