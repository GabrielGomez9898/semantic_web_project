// =====================================================================
// Etapa 3 · Punto 1 — Consultas de verificación del grafo en Neo4j
// Para ejecutar en Neo4j Browser / Aura Query (una consulta a la vez).
// Requiere haber ejecutado notebooks/01_carga_grafo_neo4j.ipynb
// =====================================================================

// Parámetros de ejemplo (en Neo4j Browser)
:param track_id => 'TRAABJV128F1460C49';
:param artista => 'Lionel Richie';

// ---------------------------------------------------------------------
// 1. Inventario del grafo
// ---------------------------------------------------------------------

// 1.1 Nodos por etiqueta
MATCH (n) UNWIND labels(n) AS etiqueta
RETURN etiqueta, count(*) AS nodos ORDER BY nodos DESC;

// 1.2 Relaciones por tipo
MATCH ()-[r]->() RETURN type(r) AS relacion, count(*) AS total ORDER BY total DESC;

// 1.3 Esquema visual (patrones etiqueta-relación-etiqueta)
CALL db.schema.visualization();

// ---------------------------------------------------------------------
// 2. Ontología (meta-grafo)
// ---------------------------------------------------------------------

// 2.1 Jerarquía de clases
MATCH (c:OntologyClass)-[r:SUBCLASS_OF]->(p:OntologyClass)
RETURN c.name AS subclase, p.name AS superclase, r.via AS axioma;

// 2.2 Propiedades con dominio, rango y su representación en Neo4j
MATCH (p:OntologyProperty)
OPTIONAL MATCH (p)-[:DOMAIN]->(d)
OPTIONAL MATCH (p)-[:RANGE]->(r)
RETURN p.name AS propiedad, p.kind AS tipo, d.name AS dominio, r.name AS rango, p.neo4j_mapping AS en_neo4j
ORDER BY tipo, propiedad;

// 2.3 Restricciones OWL
MATCH (c:OntologyClass)-[:SUBCLASS_OF]->(r:Restriction)-[:ON_PROPERTY]->(p:OntologyProperty)
OPTIONAL MATCH (r)-[:ON_CLASS]->(oc)
RETURN c.name AS clase, p.name AS propiedad, r.kind AS restriccion, r.value AS valor, oc.name AS sobre_clase;

// 2.4 Visualizar la ontología completa
MATCH path = (:OntologyProperty|OntologyClass)-[*1..1]-() RETURN path;

// ---------------------------------------------------------------------
// 3. Integridad respecto a la ontología
// ---------------------------------------------------------------------

// 3.1 Tracks sin artista (minQualifiedCardinality 1 sobre sungBy) — esperado: 0
MATCH (t:Track) WHERE NOT (t)-[:SUNG_BY]->(:Artist) RETURN count(t) AS tracks_sin_artista;

// 3.2 Tracks sin título (cardinality 1 sobre title)
MATCH (t:Track) WHERE t.title IS NULL RETURN t.id, t.released;

// 3.3 Artistas sin canciones — esperado: 0
MATCH (a:Artist) WHERE NOT ()-[:SUNG_BY]->(a) RETURN count(a) AS artistas_sin_canciones;

// ---------------------------------------------------------------------
// 4. Entidades y relaciones principales
// ---------------------------------------------------------------------

// 4.1 Ficha de una canción (Track -> Artist -> Country, Track -> Tag)
MATCH (t:Track {id: $track_id})-[:SUNG_BY]->(a:Artist)
OPTIONAL MATCH (a)-[:ORIGIN]->(c:Country)
OPTIONAL MATCH (t)-[:HAS_TAG]->(tag:Tag)
RETURN t.title, t.released, t.year, t.duration, a.name, c.id, tag.name;

// 4.2 Vecindario visual de una canción
MATCH path = (t:Track {id: $track_id})-[:SUNG_BY|HAS_TAG|SIMILAR_TO]-()
OPTIONAL MATCH path2 = (t)-[:SUNG_BY]->(:Artist)-[:ORIGIN]->(:Country)
RETURN path, path2;

// 4.3 Canciones similares (Last.fm) ordenadas por score
MATCH (t:Track {id: $track_id})-[s:SIMILAR_TO]->(o:Track)-[:SUNG_BY]->(a:Artist)
RETURN o.title AS titulo, a.name AS artista, s.score AS score ORDER BY score DESC;

// 4.4 Canciones de un artista
MATCH (t:Track)-[:SUNG_BY]->(a:Artist {name: $artista})
RETURN t.title, t.released, t.year ORDER BY t.year DESC;

// 4.5 Artistas con más canciones
MATCH (t:Track)-[:SUNG_BY]->(a:Artist)
RETURN a.name AS artista, count(t) AS canciones ORDER BY canciones DESC LIMIT 10;

// 4.6 Países con más artistas
MATCH (a:Artist)-[:ORIGIN]->(c:Country)
RETURN c.id AS pais, count(a) AS artistas ORDER BY artistas DESC LIMIT 10;

// 4.7 Tags más frecuentes
MATCH (t:Track)-[:HAS_TAG]->(tag:Tag)
RETURN tag.name AS tag, count(t) AS canciones ORDER BY canciones DESC LIMIT 10;

// 4.8 Cadena de propiedades sungInCountry = sungBy ∘ origin
MATCH (t:Track)-[:SUNG_BY]->(:Artist)-[:ORIGIN]->(c:Country)
RETURN c.id AS pais, count(t) AS canciones ORDER BY canciones DESC LIMIT 10;

// 4.9 Jerarquía materializada como etiquetas
MATCH (n:CreativeWork) RETURN 'CreativeWork' AS etiqueta, count(n) AS nodos
UNION ALL MATCH (n:Person) RETURN 'Person' AS etiqueta, count(n) AS nodos
UNION ALL MATCH (n:GeographicalEntity) RETURN 'GeographicalEntity' AS etiqueta, count(n) AS nodos;

// 4.10 Bonus: hechos extraídos de textos con evidencia
MATCH (a:Artist)-[r:ASSOCIATED_WITH_GENRE|INFLUENCED_BY_GENRE|PLAYS_INSTRUMENT|PRODUCED_BY|COLLABORATED_WITH]->(x)
RETURN a.name AS artista, type(r) AS relacion, x.name AS objeto, r.evidence AS evidencia, r.sources AS fuentes
ORDER BY artista;
