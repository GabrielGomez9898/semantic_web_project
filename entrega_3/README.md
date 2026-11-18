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
│   ├── 01_carga_grafo_neo4j.ipynb                  # Punto 1: carga + verificación
│   ├── 02_integracion_resenas_critiquebrainz.ipynb # Punto 2: preferencias de usuarios + corpus RAG
│   └── 03_recomendacion_algoritmos_grafos.ipynb    # Punto 3: Louvain + Personalized PageRank
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

---

## Punto 2. Integración de preferencias de usuarios (CritiqueBrainz)

Notebook: `notebooks/02_integracion_resenas_critiquebrainz.ipynb` (requiere el grafo del punto 1 cargado en Neo4j).

### Fuente y archivos

| Archivo | Contenido |
|---|---|
| `data/critiquebrainz/reviews_{recording,release_group,artist}.jsonl.gz` | Caché de reseñas de CritiqueBrainz (API `/ws/1/review/`), campos relevantes. |
| `data/critiquebrainz/musicbrainz_{recording,release_group}.json` | Caché de la resolución en MusicBrainz (título + MBIDs de artistas acreditados). |
| `data/msd_recording_mbid.csv` | Mapeo MSD `track_id` → MusicBrainz `recording_mbid` (filtrado del archivo `msd-mbid-2016-01` usado en la Etapa 1). |
| `data/ontology_reviews.ttl` | Extensión de la ontología: `User`, `Review`, `Album`, `interactedWith` (cadenas OWL), etc. |
| `data/reviews.ttl` | Instancias RDF generadas (reseñas, usuarios, álbumes, `recordingMbid`). |
| `data/corpus_rag.jsonl.gz` | Corpus RAG: chunks con contexto (sin embeddings). |

Si se borran los cachés, el notebook vuelve a descargar todo (~15 min por los límites de las APIs).

### Reconciliación y cobertura

Las canciones del grafo usan IDs del Million Song Dataset, sin MBID de recording. Estrategias (de más a menos específica):

| Estrategia | Clave | Reseñas | Con texto | Canciones cubiertas |
|---|---|---|---|---|
| `recording_mbid` | MBID exacto vía mapeo MSD → MusicBrainz | 7 | 0 | 7 |
| `recording_artista_titulo` | MBID de artista + título normalizado | 7 | 4 | 7 |
| `album_artista_titulo` | MBID de artista + título normalizado del álbum (`rbo:released`) | 1.942 | 1.845 | 2.966 |
| `artista_mbid` | MBID de artista exacto | 50 | 18 | 313 |
| **Total** | | **2.006** de 14.600 | **1.867** | **3.206 (3,2 %)** — 2.999 con texto |

- CritiqueBrainz solo tiene 916 reseñas de *recordings* (361 con texto); las que coinciden con el grafo no tienen texto.
  Por eso la cobertura útil proviene de las reseñas de **álbumes** (13.079, en su mayoría críticas de la BBC con licencia CC).
- Siempre se exige el MBID del artista, lo que evita falsos positivos con títulos genéricos.
- Causas de no emparejamiento (reportadas en el notebook): artista ausente del grafo, título distinto, entidad fusionada/eliminada en MusicBrainz.

### Modelo en Neo4j

`(:User)<-[:WRITTEN_BY]-(:Review)-[:REVIEWS_ALBUM|REVIEWS_RECORDING|REVIEWS_ARTIST]->(:Album|:Track|:Artist)`,
`(:Track)-[:APPEARS_ON]->(:Album)-[:RELEASED_BY]->(:Artist)` y la preferencia materializada
`(:User)-[:INTERACTED_WITH {via, rating, review}]->(:Track)` (3.470 relaciones), derivada de las cadenas de propiedades de `rbo:interactedWith`.

### Corpus RAG

1.855 reseñas (≥ 10 palabras) → **5.335 chunks** (~130 palabras, por oraciones, solapamiento de una oración, encabezado de
contexto con la entidad reseñada) → embeddings `intfloat/multilingual-e5-small` (384 d, multilingüe) →
`(:Chunk)-[:PART_OF]->(:Review)` con índice vectorial `chunk_embedding`.
Recuperación global (`recuperar`) o restringida a canciones candidatas (`recuperar_para_canciones`).
Prueba de auto-recuperación (150 reseñas, en AuraDB): Recall@1 = 0,88, Recall@5 = 0,91, MRR = 0,90.

Totales del grafo tras el punto 2: ~137 mil nodos y ~148 mil relaciones (dentro de AuraDB Free).

---

## Punto 3. Generación de candidatos con algoritmos de grafos

Notebook: `notebooks/03_recomendacion_algoritmos_grafos.ipynb`. Requiere los puntos 1 y 2 cargados en Neo4j.

AuraDB Free no incluye Graph Data Science. Por eso se sigue el mecanismo del taller: el grafo se **proyecta desde Neo4j
con Cypher**, los algoritmos se ejecutan con **NetworkX** y los resultados se **escriben de vuelta en Neo4j**.

### Proyección

Es un grafo no dirigido y ponderado de 130.031 nodos y 136.721 aristas:

| Arista | Peso |
|---|---|
| canción–artista, canción–tag, canción–álbum–artista, usuario–entidad reseñada (punto 2), artista–entidades del bonus | 1 |
| canción–canción (`SIMILAR_TO`) | 10 × score |
| artista–país | 0,2 |

El análisis de componentes conexas (WCC) muestra que sin el país solo el 27 % de las canciones está en el núcleo
conectado. Por eso el país entra con peso bajo, como respaldo.

### Algoritmos

| Algoritmo | Parte del grafo | Información que produce | Contribución a los candidatos |
|---|---|---|---|
| **Louvain** | Co-grafo de artistas: similitud entre canciones, tags compartidos, críticos en común, bonus | 133 comunidades («escenas»), modularidad 0,81. Se guardan en `Artist.community` | Escena de la preferencia. Modo «misma escena» (Louvain selecciona, PPR ordena). Anotación y explicación de cada candidato |
| **Personalized PageRank** | Grafo heterogéneo completo y ponderado | Cercanía de cada nodo a las semillas | Ranking de canciones, artistas y álbumes, con el camino más fuerte como explicación |

La función `recomendar(canciones, artistas, tags, usuario, texto, modo)` acepta cualquier tipo de preferencia. El texto
libre se resuelve con el índice vectorial del punto 2. La lista final aplica diversidad: máximo 2 canciones por artista
y sin duplicados del MSD.

### Evaluación (ocultamiento de relaciones)

Canción → canciones similares ocultas (200 semillas, 770 relaciones ocultas):

| Método | recall@10 | recall@50 |
|---|---|---|
| Popularidad | 0,001 | 0,003 |
| Mismo artista | 0,010 | 0,018 |
| Solo Louvain (misma comunidad) | 0,029 | 0,099 |
| PPR | 0,032 | 0,168 |
| Louvain → PPR (modo escena) | 0,034 | 0,156 |
| **PPR, máx. 2 por artista (por defecto)** | **0,039** | **0,213** |

Otros resultados:
- **Usuario → próxima reseña:** hit@50 de 0,036 con PPR frente a 0,014 con popularidad.
- **Ampliar las semillas con la escena de Louvain:** no mejoró, ni con canciones ni con tags, así que quedó como opción
  desactivada.

### Resultados en Neo4j

- `Artist.community`: 4.747 artistas.
- `(:User)-[:RECOMMENDED {rank, score, community, method}]->(:Track)`: 3.870 relaciones, 10 por usuario.
- Totales del grafo: 137.446 nodos y 151.553 relaciones.
