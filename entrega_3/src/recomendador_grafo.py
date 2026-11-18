"""Núcleo del generador de candidatos del punto 3 (Louvain + Personalized PageRank), reutilizable.

Es la misma lógica que se explica paso a paso en notebooks/03_recomendacion_algoritmos_grafos.ipynb,
empaquetada en una clase para que los puntos siguientes (ranking, RAG) obtengan candidatos sin repetir código.

Uso:
    from recomendador_grafo import GrafoRecomendador
    gr = GrafoRecomendador(run_cypher)          # proyecta el grafo desde Neo4j y calcula comunidades
    sem = gr.resolver_preferencia(artistas=['Bukka White'])
    cands = gr.candidatos(sem, n=200)           # [(uri_cancion, score_ppr), ...]
"""
import itertools
import math
import re
from collections import Counter, defaultdict

import networkx as nx

PESOS = {'SUNG_BY': 1.0, 'SIMILAR_TO': 10.0, 'HAS_TAG': 1.0, 'APPEARS_ON': 1.0, 'RELEASED_BY': 1.0,
         'REVIEWED': 1.0, 'ORIGIN': 0.2, 'BONUS': 1.0}
ALPHA = 0.85
MAX_POR_ARTISTA = 2
SEMILLA = 42

CONSULTAS = {
    'SUNG_BY':     'MATCH (s:Track)-[:SUNG_BY]->(o:Artist) RETURN s.uri AS s, o.uri AS o',
    'SIMILAR_TO':  'MATCH (s:Track)-[r:SIMILAR_TO]->(o:Track) RETURN s.uri AS s, o.uri AS o, r.score AS score',
    'HAS_TAG':     'MATCH (s:Track)-[:HAS_TAG]->(o:Tag) RETURN s.uri AS s, o.uri AS o',
    'APPEARS_ON':  'MATCH (s:Track)-[:APPEARS_ON]->(o:Album) RETURN s.uri AS s, o.uri AS o',
    'RELEASED_BY': 'MATCH (s:Album)-[:RELEASED_BY]->(o:Artist) RETURN s.uri AS s, o.uri AS o',
    'REVIEWED':    '''MATCH (s:User)<-[:WRITTEN_BY]-(r:Review)-[:REVIEWS_RECORDING|REVIEWS_ALBUM|REVIEWS_ARTIST]->(o)
                      RETURN s.uri AS s, o.uri AS o, r.uri AS review, r.rating AS rating''',
    'ORIGIN':      'MATCH (s:Artist)-[:ORIGIN]->(o:Country) RETURN s.uri AS s, o.uri AS o',
    'BONUS':       '''MATCH (s:Artist)-[r:ASSOCIATED_WITH_GENRE|INFLUENCED_BY_GENRE|PLAYS_INSTRUMENT|PRODUCED_BY|COLLABORATED_WITH]->(o)
                      RETURN s.uri AS s, o.uri AS o, type(r) AS rel''',
}
TIPOS = ['Track', 'Artist', 'Album', 'User', 'Tag', 'Country', 'Genre', 'Instrument', 'Person']
CONSULTA_NODOS = '''
    MATCH (n) WHERE any(l IN labels(n) WHERE l IN $tipos)
    RETURN n.uri AS uri, [l IN $tipos WHERE l IN labels(n)][0] AS tipo, n.id AS id,
           coalesce(n.title, n.name, n.areas[0], n.id) AS nombre'''


def titulo_base(titulo):
    """Título sin paréntesis/corchetes, para detectar la misma canción con distinto ID en el MSD."""
    return re.sub(r'\s*[\(\[].*?[\)\]]', '', str(titulo)).strip().casefold()


class GrafoRecomendador:
    def __init__(self, run_cypher, pesos=PESOS, alpha=ALPHA, datos=None, nodos=None):
        self.run_cypher, self.pesos, self.alpha = run_cypher, pesos, alpha
        self.datos = datos or {rel: run_cypher(q) for rel, q in CONSULTAS.items()}
        nodos = nodos or run_cypher(CONSULTA_NODOS, tipos=TIPOS)
        self.tipo = {n['uri']: n['tipo'] for n in nodos}
        self.nombre = {n['uri']: n['nombre'] or '(sin nombre)' for n in nodos}
        self.track_uri = {n['id']: n['uri'] for n in nodos if n['tipo'] == 'Track'}
        self.artista_de = {f['s']: f['o'] for f in self.datos['SUNG_BY']}
        self.ctx = self.contexto()
        self._indice = defaultdict(list)
        for u, t in self.tipo.items():
            self._indice[(t, self._norm(self.nombre[u]))].append(u)
        self._modelo = None

    # ------------------------------------------------------------------ proyección
    def construir_grafo(self, pesos=None, excluir=frozenset()):
        pesos = pesos or self.pesos
        G = nx.Graph()
        G.add_nodes_from(self.tipo)
        for rel, filas in self.datos.items():
            if not pesos.get(rel):
                continue
            for f in filas:
                s, o = f['s'], f['o']
                if (s, o) in excluir:
                    continue
                w = pesos[rel] * (float(f['score'] or 0) if rel == 'SIMILAR_TO' else 1.0)
                if G.has_edge(s, o):
                    G[s][o]['weight'] += w
                else:
                    G.add_edge(s, o, weight=w, rel=f.get('rel', rel))
        return G

    def construir_cografo(self, excluir=frozenset()):
        A = nx.Graph()

        def sumar(a, b, w):
            if a and b and a != b:
                if A.has_edge(a, b):
                    A[a][b]['weight'] += w
                else:
                    A.add_edge(a, b, weight=w)
        album_artistas = defaultdict(set)
        for f in self.datos['RELEASED_BY']:
            album_artistas[f['s']].add(f['o'])

        def artistas(n):
            t = self.tipo.get(n)
            return {n} if t == 'Artist' else album_artistas[n] if t == 'Album' else \
                {self.artista_de[n]} if t == 'Track' else set()
        for f in self.datos['SIMILAR_TO']:
            if (f['s'], f['o']) not in excluir:
                sumar(self.artista_de[f['s']], self.artista_de[f['o']], float(f['score'] or 0))
        grupos = defaultdict(set)
        for f in self.datos['HAS_TAG']:
            if (f['s'], f['o']) not in excluir:
                grupos[f['o']].add(self.artista_de[f['s']])
        for f in self.datos['REVIEWED']:
            if (f['s'], f['o']) not in excluir:
                grupos[f['s']] |= artistas(f['o'])
        for f in self.datos['BONUS']:
            if self.tipo.get(f['o']) == 'Artist':
                sumar(f['s'], f['o'], 1.0)
            else:
                grupos[f['o']].add(f['s'])
        for miembros in grupos.values():
            if len(miembros) > 1:
                w = 1 / (len(miembros) - 1)
                for a, b in itertools.combinations(sorted(miembros), 2):
                    sumar(a, b, w)
        return A

    def contexto(self, excluir=frozenset(), pesos=None):
        """Grafo + comunidades Louvain (opcionalmente sin ciertas aristas, para evaluación sin fuga)."""
        A = self.construir_cografo(excluir)
        comms = sorted(nx.community.louvain_communities(A, weight='weight', resolution=1.0, seed=SEMILLA),
                       key=len, reverse=True)
        return {'G': self.construir_grafo(pesos, excluir), 'A': A, 'comms': comms,
                'com': {a: i for i, c in enumerate(comms) for a in c}, 'fuerza': dict(A.degree(weight='weight'))}

    # ------------------------------------------------------------------ algoritmos
    def ppr(self, semillas, ctx=None):
        ctx = ctx or self.ctx
        pers = {n: w for n, w in semillas.items() if n in ctx['G'] and w > 0}
        if not pers:
            raise ValueError('Ninguna semilla está en el grafo')
        return nx.pagerank(ctx['G'], alpha=self.alpha, personalization=pers, weight='weight')

    def artistas_de(self, n, ctx=None):
        ctx = ctx or self.ctx
        G, t = ctx['G'], self.tipo.get(n)
        if t == 'Artist':
            return [n]
        if t in ('Track', 'Album'):
            return [v for v in G[n] if self.tipo.get(v) == 'Artist']
        if t == 'User':
            return [a for v in G[n] for a in self.artistas_de(v, ctx)]
        if t in ('Tag', 'Genre', 'Instrument', 'Person'):
            return [a for v in G[n] for a in ([v] if self.tipo.get(v) == 'Artist'
                                              else self.artistas_de(v, ctx) if self.tipo.get(v) == 'Track' else [])]
        return []

    def escena(self, semillas, ctx=None):
        ctx = ctx or self.ctx
        c = Counter()
        for n, w in semillas.items():
            arts = [a for a in self.artistas_de(n, ctx) if a in ctx['com']]
            for a in arts:
                c[ctx['com'][a]] += w / len(arts)
        return c

    def canciones_conocidas(self, semillas, ctx=None):
        ctx = ctx or self.ctx
        G, conocidas = ctx['G'], set()
        for n in semillas:
            t = self.tipo.get(n)
            if t == 'Track':
                conocidas.add(n)
            elif t == 'User':
                for v in G[n]:
                    conocidas |= {v} if self.tipo.get(v) == 'Track' else {x for x in G[v] if self.tipo.get(x) == 'Track'}
        return conocidas

    def candidatos(self, semillas, n=200, ctx=None, conocidas=None, scores=None):
        """Top-n canciones por PPR, sin las conocidas ni duplicados del MSD (sin límite por artista)."""
        ctx = ctx or self.ctx
        scores = scores if scores is not None else self.ppr(semillas, ctx)
        conocidas = self.canciones_conocidas(semillas, ctx) if conocidas is None else conocidas
        orden = sorted(((t, s) for t, s in scores.items()
                        if s > 0 and self.tipo.get(t) == 'Track' and t not in conocidas), key=lambda x: -x[1])
        # además de las conocidas, se excluyen sus duplicados en el MSD (misma canción y artista, otro ID)
        vistas, salida = {(self.artista_de[t], titulo_base(self.nombre[t])) for t in conocidas if t in self.artista_de}, []
        for t, s in orden:
            clave = (self.artista_de[t], titulo_base(self.nombre[t]))
            if clave not in vistas:
                vistas.add(clave)
                salida.append((t, s))
                if len(salida) == n:
                    break
        return salida

    def camino(self, semillas, destino, ctx=None):
        """Camino más fuerte (Dijkstra con costo 1/peso) desde alguna semilla: [(nodo, relación_de_llegada), ...]."""
        ctx = ctx or self.ctx
        try:
            _, nodos = nx.multi_source_dijkstra(ctx['G'], set(semillas), target=destino,
                                                weight=lambda u, v, d: 1.0 / d['weight'])
        except nx.NetworkXNoPath:
            return []
        return [(nodos[0], None)] + [(v, ctx['G'][u][v]['rel']) for u, v in zip(nodos, nodos[1:])]

    def explicar(self, semillas, destino, ctx=None):
        pasos = self.camino(semillas, destino, ctx)
        if not pasos:
            return '(sin camino)'
        return ' '.join([self.etiqueta(pasos[0][0])] + [f'─{rel}─ {self.etiqueta(n)}' for n, rel in pasos[1:]])

    def etiquetas_comunidades(self, ctx=None, max_tags=3):
        """Nombre legible de cada comunidad Louvain: tags más compartidos entre sus artistas."""
        ctx = ctx or self.ctx
        tags_artista = defaultdict(set)
        for f in self.datos['HAS_TAG']:
            tags_artista[self.artista_de[f['s']]].add(self.nombre[f['o']].lower())
        for f in self.datos['BONUS']:
            if self.tipo.get(f['o']) == 'Genre':
                tags_artista[f['s']].add(self.nombre[f['o']].lower())
        etiquetas = {}
        for c, miembros in enumerate(ctx['comms']):
            cuenta = Counter(t for a in miembros for t in tags_artista[a] if len(t) <= 20)
            comunes = [t for t, n in cuenta.most_common() if n >= 2][:max_tags]
            if comunes:
                etiquetas[c] = ' · '.join(comunes)
            else:
                centrales = sorted(miembros, key=lambda a: -ctx['fuerza'].get(a, 0))[:2]
                etiquetas[c] = 'escena de ' + ' / '.join(self.nombre[a] for a in centrales)
        return etiquetas

    # ------------------------------------------------------------------ preferencias
    def etiqueta(self, n):
        t = self.tipo.get(n)
        if t == 'Track':
            return f'«{self.nombre[n]}» ({self.nombre[self.artista_de[n]]})'
        return {'Artist': '{}', 'Album': 'álbum «{}»', 'Tag': '#{}', 'Genre': 'género {}', 'User': 'usuario {}',
                'Country': 'país {}'}.get(t, '{} (' + str(t) + ')').format(self.nombre.get(n))

    @staticmethod
    def _norm(s):
        return re.sub(r'\s+', ' ', str(s)).strip().casefold()

    def buscar(self, nombre, tipos):
        cands = [u for t in tipos for u in self._indice.get((t, self._norm(nombre)), [])]
        if not cands:
            n = self._norm(nombre)
            cands = [u for (t, nm), us in self._indice.items() if t in tipos and n in nm for u in us]
        if not cands:
            raise ValueError(f'No se encontró «{nombre}» entre {"/".join(tipos)}')
        return max(cands, key=lambda u: self.ctx['G'].degree(u, weight='weight'))

    def modelo(self):
        if self._modelo is None:
            from sentence_transformers import SentenceTransformer
            self._modelo = SentenceTransformer('intfloat/multilingual-e5-small')
        return self._modelo

    def semillas_desde_texto(self, texto, k=10, temperatura=0.02):
        qv = self.modelo().encode(f'query: {texto}', normalize_embeddings=True).tolist()
        filas = self.run_cypher('''
            CALL db.index.vector.queryNodes('chunk_embedding', $k, $qv) YIELD node AS c, score
            MATCH (c)-[:PART_OF]->(:Review)-[:REVIEWS_RECORDING|REVIEWS_ALBUM|REVIEWS_ARTIST]->(e)
            RETURN e.uri AS uri, max(score) AS score ORDER BY score DESC''', k=k, qv=qv)
        tope = filas[0]['score']
        return {f['uri']: math.exp((f['score'] - tope) / temperatura) for f in filas if f['uri'] in self.tipo}

    def resolver_preferencia(self, canciones=(), artistas=(), tags=(), usuario=None, texto=None):
        semillas = Counter()
        for c in canciones:
            semillas[self.track_uri[c] if re.fullmatch(r'TR[A-Z0-9]{16}', c) else self.buscar(c, ['Track'])] += 1
        for a in artistas:
            semillas[self.buscar(a, ['Artist'])] += 1
        for t in tags:
            semillas[self.buscar(t, ['Tag', 'Genre'])] += 1
        if usuario:
            semillas[usuario if usuario in self.tipo else self.buscar(usuario, ['User'])] += 1
        if texto:
            for u, w in self.semillas_desde_texto(texto).items():
                semillas[u] += w
        if not semillas:
            raise ValueError('La preferencia está vacía')
        return dict(semillas)
