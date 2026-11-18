"""Ranking final del punto 4 (grafo + preferencias de usuarios), reutilizable.

Es la misma lógica que se explica y evalúa en notebooks/04_ranking_recomendaciones.ipynb. Los pesos y parámetros
se leen de data/ranking_config.json, que escribe ese notebook después de seleccionarlos.
Si el archivo no existe, se usan los valores por defecto documentados abajo.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from recomendador_grafo import MAX_POR_ARTISTA

ARCHIVO_CONFIG = Path(__file__).resolve().parents[1] / 'data' / 'ranking_config.json'
CONFIG_POR_DEFECTO = {'pesos': {'G': 0.2, 'V': 0.1, 'A': 0.7, 'E': 0.0},
                      'n_candidatos': 200, 'k_prior': 2.0, 'conf_estimada': 0.5}
SENALES = ['G', 'V', 'A', 'E']


def cargar_config(ruta=ARCHIVO_CONFIG):
    cfg = dict(CONFIG_POR_DEFECTO)
    if Path(ruta).exists():
        cfg.update(json.loads(Path(ruta).read_text(encoding='utf-8')))
    return cfg


def minmax(x):
    x = np.asarray(x, dtype=float)
    lo, hi = np.min(x), np.max(x)
    return np.zeros_like(x) if hi - lo < 1e-12 else (x - lo) / (hi - lo)


class Ranking:
    def __init__(self, gr, run_cypher, config=None):
        from sklearn.linear_model import RidgeCV
        self.gr, self.run_cypher = gr, run_cypher
        self.cfg = config or cargar_config()
        self.pesos = self.cfg['pesos']
        self.resenas = {f['review']: f for f in run_cypher('''
            MATCH (u:User)<-[:WRITTEN_BY]-(r:Review)-[:REVIEWS_RECORDING|REVIEWS_ALBUM|REVIEWS_ARTIST]->(e)
            RETURN r.uri AS review, u.uri AS usuario, e.uri AS entidad, labels(e)[0] AS tipo,
                   r.rating AS rating, r.url AS url''')}
        acum = defaultdict(list)
        for f in run_cypher('MATCH (c:Chunk)-[:PART_OF]->(r:Review) RETURN r.uri AS review, c.embedding AS e'):
            acum[f['review']].append(np.asarray(f['e'], dtype=np.float32))
        self.emb = {r: (lambda m: m / np.linalg.norm(m))(np.mean(v, axis=0)) for r, v in acum.items()}

        self.canciones_album, self.canciones_artista = defaultdict(set), defaultdict(set)
        for f in gr.datos['APPEARS_ON']:
            self.canciones_album[f['o']].add(f['s'])
        for f in gr.datos['SUNG_BY']:
            self.canciones_artista[f['o']].add(f['s'])
        self.resenas_cancion, self.resenas_usuario = defaultdict(set), defaultdict(set)
        for r, f in self.resenas.items():
            for t in self.canciones_de(f['entidad'], f['tipo']):
                self.resenas_cancion[t].add(r)
            self.resenas_usuario[f['usuario']].add(r)

        # Valoración: estrellas explícitas o estimadas desde el texto (ridge sobre el vector de la reseña)
        etiquetadas = sorted(r for r, f in self.resenas.items() if f['rating'] is not None and r in self.emb)
        modelo = RidgeCV(alphas=np.logspace(-2, 3, 12)).fit(
            np.array([self.emb[r] for r in etiquetadas]), [self.resenas[r]['rating'] for r in etiquetadas])
        self.valoracion_resena = {}
        for r, f in self.resenas.items():
            if f['rating'] is not None:
                self.valoracion_resena[r] = (float(f['rating']), 1.0)
            elif r in self.emb:
                est = float(np.clip(modelo.predict(self.emb[r][None])[0], 1, 5))
                self.valoracion_resena[r] = (est, self.cfg['conf_estimada'])
        vals = self.valoracion_resena.values()
        self.mu = sum(v * w for v, w in vals) / sum(w for _, w in vals)

    # ------------------------------------------------------------------ señales
    def canciones_de(self, entidad, tipo):
        return {entidad} if tipo == 'Track' else self.canciones_album[entidad] if tipo == 'Album' \
            else self.canciones_artista[entidad]

    def valoracion(self, t):
        num, den, n, explicitas = self.cfg['k_prior'] * self.mu, self.cfg['k_prior'], 0, 0
        for r in self.resenas_cancion.get(t, ()):
            if r in self.valoracion_resena:
                v, w = self.valoracion_resena[r]
                num, den, n, explicitas = num + w * v, den + w, n + 1, explicitas + (w == 1.0)
        return num / den, n, explicitas

    def vector_cancion(self, t, excluir=frozenset()):
        vs = [self.emb[r] for r in self.resenas_cancion.get(t, ()) if r in self.emb and r not in excluir]
        if not vs:
            return None
        m = np.mean(vs, axis=0)
        return m / np.linalg.norm(m)

    def perfil(self, semillas, texto=None):
        if texto:
            return self.gr.modelo().encode(f'query: {texto}', normalize_embeddings=True)
        vs = []
        for n in semillas:
            t = self.gr.tipo.get(n)
            if t == 'User':
                rs = self.resenas_usuario[n]
            elif t == 'Track':
                rs = self.resenas_cancion.get(n, set())
            elif t in ('Album', 'Artist'):
                rs = {r for r, f in self.resenas.items() if f['entidad'] == n}
                if t == 'Artist':
                    rs |= {r for c in self.canciones_artista[n] for r in self.resenas_cancion.get(c, ())}
            else:
                rs = set()
            vs += [self.emb[r] for r in rs if r in self.emb]
        if not vs:
            return None
        m = np.mean(vs, axis=0)
        return m / np.linalg.norm(m)

    def senales(self, semillas, cands, usuario=None, texto=None):
        prof = self.perfil(semillas, texto)
        esc = self.gr.escena(semillas)
        principal = esc.most_common(1)[0][0] if esc else None
        excluir = self.resenas_usuario[usuario] if usuario else set()
        estrellas, n_res, n_expl, afin, escena = [], [], [], [], []
        for t, _ in cands:
            v, n, e = self.valoracion(t)
            estrellas.append(v); n_res.append(n); n_expl.append(e)
            vt = self.vector_cancion(t, excluir) if prof is not None else None
            afin.append(np.nan if vt is None else float(prof @ vt))
            escena.append(1.0 if principal is not None and self.gr.ctx['com'].get(self.gr.artista_de[t]) == principal else 0.0)
        afin = np.array(afin)
        afin_rellena = np.zeros(len(afin)) if np.isnan(afin).all() else np.where(np.isnan(afin), np.nanmean(afin), afin)
        F = np.c_[minmax(np.log([s for _, s in cands])), minmax(estrellas), minmax(afin_rellena), escena]
        return F, {'estrellas': estrellas, 'reseñas': n_res, 'explícitas': n_expl, 'afinidad': afin,
                   'perfil': prof, 'escena': esc}

    # ------------------------------------------------------------------ Top-K
    def top_k(self, semillas, cands, k=10, usuario=None, texto=None, max_por_artista=MAX_POR_ARTISTA):
        F, extra = self.senales(semillas, cands, usuario, texto)
        w = np.array([self.pesos[s] for s in SENALES])
        score = F @ w
        puesto_grafo = {i: p for p, i in enumerate(np.argsort(-F[:, 0], kind='stable'), 1)}
        orden, elegidos, cuenta = np.argsort(-score, kind='stable'), [], Counter()
        for i in orden:
            a = self.gr.artista_de[cands[i][0]]
            if cuenta[a] < max_por_artista:
                elegidos.append(i); cuenta[a] += 1
            if len(elegidos) == k:
                break
        salida = []
        for p, i in enumerate(elegidos, 1):
            salida.append({'rank': p, 'uri': cands[i][0], 'score': float(score[i]),
                           'senales': {s: float(F[i, j]) for j, s in enumerate(SENALES)},
                           'estrellas': float(extra['estrellas'][i]), 'reseñas': int(extra['reseñas'][i]),
                           'explícitas': int(extra['explícitas'][i]),
                           'afinidad': None if np.isnan(extra['afinidad'][i]) else float(extra['afinidad'][i]),
                           'puesto_grafo': puesto_grafo[i]})
        return salida, extra
