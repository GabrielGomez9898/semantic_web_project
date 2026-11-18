"""Interfaz web del sistema de recomendación musical (Etapa 3 · Punto 5).

Ejecutar desde la raíz del repositorio:
    python entrega_3/app/app.py            # abre http://127.0.0.1:7860
    python entrega_3/app/app.py --share    # además genera un enlace público temporal (útil en Colab)

Requiere entrega_3/.env con las credenciales de Neo4j y el grafo cargado por los notebooks 01 a 04.
Cada recomendación se calcula en vivo con el mecanismo de los puntos 2 a 4 (no hay listas precalculadas).
"""
import argparse
import html
import sys
import traceback
from pathlib import Path

import gradio as gr_ui
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from sistema_recomendacion import SistemaRecomendacion  # noqa: E402

CSS = """
.rec-card {border: 1px solid var(--border-color-primary, #d0d4dc); border-radius: 12px; padding: 14px 16px; margin-bottom: 12px;
           background: var(--block-background-fill, transparent);}
.rec-head {display: flex; align-items: center; gap: 12px; flex-wrap: wrap;}
.rec-rank {font-weight: 700; font-size: 1.1em; min-width: 2em; height: 2em; border-radius: 50%; display: flex;
           align-items: center; justify-content: center; background: var(--color-accent, #e8590c); color: white;}
.rec-title {font-weight: 600; font-size: 1.05em; color: var(--body-text-color, inherit);}
.rec-artist {color: var(--body-text-color-subdued, #6b7280);}
.rec-chips {display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px;}
.rec-chip {font-size: 0.82em; padding: 2px 9px; border-radius: 999px; border: 1px solid var(--border-color-primary, #d0d4dc);
           color: var(--body-text-color, inherit);}
.rec-bar {height: 6px; border-radius: 3px; background: var(--border-color-primary, #d0d4dc); margin-top: 8px; overflow: hidden;}
.rec-bar > div {height: 100%; background: var(--color-accent, #e8590c);}
.rec-why {margin-top: 10px; color: var(--body-text-color, inherit);}
.rec-why ul {margin: 4px 0 0 18px; padding: 0;}
.rec-quote {margin-top: 10px; padding: 8px 12px; border-left: 3px solid var(--color-accent, #e8590c); font-style: italic;
            color: var(--body-text-color-subdued, #6b7280); font-size: 0.93em;}
.rec-path {margin-top: 8px; font-size: 0.85em; color: var(--body-text-color-subdued, #6b7280);}
"""


def tarjeta(it, score_max):
    e = html.escape
    chips = []
    if it['escena']:
        chips.append(f'🎧 {e(it["escena"])}' + (' · misma escena' if it['misma_escena'] else ''))
    if it['reseñas']:
        chips.append(f'★ {it["estrellas"]:.1f} · {it["reseñas"]} reseña{"s" * (it["reseñas"] > 1)}')
    chips_html = ''.join(f'<span class="rec-chip">{c}</span>' for c in chips)
    detalles = ''.join(f'<li>{e(d)}</li>' for d in it['explicacion']['detalles'])
    cita = ''
    if it['fragmento']:
        f = it['fragmento']
        enlace = f' · <a href="{e(f["url"])}" target="_blank">leer reseña</a>' if f.get('url') else ''
        cita = (f'<div class="rec-quote">“{e(f["texto"])}”<br><span style="font-style:normal">— {e(f["autor"] or "usuario")}, '
                f'CritiqueBrainz ({e(f["contexto"])}){enlace}</span></div>')
    ancho = 100 * it['score'] / score_max if score_max > 0 else 0
    return f"""
<div class="rec-card">
  <div class="rec-head"><div class="rec-rank">{it['rank']}</div>
    <div><div class="rec-title">{e(it['cancion'])}</div><div class="rec-artist">{e(it['artista'])}</div></div></div>
  <div class="rec-bar" title="puntaje final {it['score']:.3f}"><div style="width:{ancho:.0f}%"></div></div>
  <div class="rec-chips">{chips_html}</div>
  <div class="rec-why"><b>¿Por qué?</b> {e(it['explicacion']['motivo'])}<ul>{detalles}</ul></div>
  {cita}
  <details class="rec-path"><summary>Camino en el grafo de conocimiento</summary>{e(it['camino'])}</details>
</div>"""


def construir_interfaz(sistema):
    def recomendar(canciones, artistas, tags, usuario, texto, k, misma_escena):
        try:
            r = sistema.recomendar(canciones=canciones, artistas=artistas, tags=tags or [], usuario=usuario,
                                   texto=texto, k=int(k), misma_escena=bool(misma_escena))
        except Exception as exc:                         # la interfaz nunca debe quedar en blanco
            traceback.print_exc()
            return f'⚠️ Ocurrió un error al consultar el grafo: `{exc}`. Intenta de nuevo.', '', pd.DataFrame()
        lineas = []
        if r.get('entendido'):
            lineas.append('**Entendí tu preferencia como:** ' + '; '.join(f'{html.escape(a)} → {html.escape(b)}' if a != b else html.escape(b)
                                                                       for a, b in r['entendido']))
        if r.get('no_encontrado'):
            lineas.append('**No encontré:** ' + ', '.join(r['no_encontrado']) + ' (revisa la ortografía).')
        if 'error' in r:
            return '\n\n'.join(lineas + [f'⚠️ {r["error"]}']), '', pd.DataFrame()
        if r['escena']:
            lineas.append('**Escena musical de tu preferencia** (comunidades Louvain): ' +
                          ', '.join(f'«{e}» ({w:.0%})' for e, w in r['escena']))
        lineas.append(f'Se evaluaron **{r["n_candidatos"]} canciones candidatas** del grafo (Personalized PageRank) y se '
                      f'ordenaron combinando grafo, valoraciones y afinidad con las reseñas de usuarios'
                      + ('' if r['perfil_textual'] else ' (tu preferencia no tiene reseñas propias, así que la afinidad textual no aplica)') + '.')
        items = r['items']
        tarjetas = ''.join(tarjeta(it, items[0]['score'] if items else 1) for it in items)
        tabla = pd.DataFrame([{'#': it['rank'], 'canción': it['cancion'], 'artista': it['artista'],
                               'puntaje': round(it['score'], 3), **{s: round(v, 2) for s, v in it['senales'].items()},
                               'estrellas': round(it['estrellas'], 2), 'reseñas': it['reseñas'],
                               'puesto solo grafo': it['puesto_grafo']} for it in items])
        return '\n\n'.join(lineas), tarjetas, tabla

    ejemplo_usuario = next((v for lbl, v in sistema.usuarios if lbl.startswith('Jaime Gill')), None)
    pesos = sistema.ranking.pesos

    with gr_ui.Blocks(title='Recomendador musical', css=CSS, theme=gr_ui.themes.Soft()) as demo:
        gr_ui.Markdown('# 🎵 Recomendador musical sobre grafo de conocimiento\n'
                       'Cuéntame qué te gusta: una canción, un artista, un género, tu usuario de CritiqueBrainz o una '
                       'descripción libre (en español o inglés). Puedes combinar varias.')
        with gr_ui.Row():
            with gr_ui.Column(scale=2, min_width=300):
                canciones = gr_ui.Textbox(label='Canciones que te gustan', placeholder='Ej.: Crazy Train, Iron Man')
                artistas = gr_ui.Textbox(label='Artistas', placeholder='Ej.: Bukka White, Aerosmith')
                tags = gr_ui.Dropdown(choices=sistema.tags, multiselect=True, label='Géneros o etiquetas')
                usuario = gr_ui.Dropdown(choices=sistema.usuarios, value=None, label='Soy este usuario de CritiqueBrainz (opcional)')
                texto = gr_ui.Textbox(label='Describe lo que quieres escuchar', lines=2,
                                      placeholder='Ej.: guitarras acústicas melancólicas, folk íntimo con voz suave')
                with gr_ui.Accordion('Opciones', open=False):
                    k = gr_ui.Slider(3, 20, value=10, step=1, label='Número de recomendaciones (K)')
                    misma_escena = gr_ui.Checkbox(value=False, label='Solo de la misma escena musical (comunidad Louvain)')
                boton = gr_ui.Button('🎧 Recomendar', variant='primary')
                limpiar = gr_ui.ClearButton([canciones, artistas, tags, usuario, texto], value='Limpiar')
                gr_ui.Examples(label='Ejemplos (solo llenan el formulario; las recomendaciones se calculan al pulsar)',
                               examples=[['', 'Bukka White', [], None, '', 10, False],
                                         ['Crazy Train', '', [], None, '', 10, False],
                                         ['', '', ['blues'], None, '', 10, True],
                                         ['', '', [], ejemplo_usuario, '', 10, False],
                                         ['', '', [], None, 'guitarras acústicas melancólicas, folk íntimo con voz suave', 10, False]],
                               inputs=[canciones, artistas, tags, usuario, texto, k, misma_escena])
            with gr_ui.Column(scale=3, min_width=360):
                resumen = gr_ui.Markdown('Las recomendaciones aparecerán aquí.')
                tarjetas = gr_ui.HTML()
                with gr_ui.Accordion('Detalle técnico del puntaje', open=False):
                    gr_ui.Markdown(f'Puntaje = {pesos["G"]}·G (grafo, PPR) + {pesos["V"]}·V (valoración de usuarios) + '
                                   f'{pesos["A"]}·A (afinidad con reseñas) + {pesos["E"]}·E (misma escena). '
                                   'Cada señal está normalizada en [0, 1] entre los candidatos; los pesos se eligieron en '
                                   'el notebook 04 (validación por ocultamiento de relaciones).')
                    tabla = gr_ui.Dataframe(interactive=False, wrap=True)
        entradas = [canciones, artistas, tags, usuario, texto, k, misma_escena]
        boton.click(recomendar, entradas, [resumen, tarjetas, tabla])
        texto.submit(recomendar, entradas, [resumen, tarjetas, tabla])
    return demo


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--share', action='store_true', help='crear un enlace público temporal de Gradio')
    p.add_argument('--port', type=int, default=7860)
    args = p.parse_args()
    sistema = SistemaRecomendacion()
    construir_interfaz(sistema).launch(server_name='127.0.0.1', server_port=args.port, share=args.share,
                                       inbrowser=not args.share)


if __name__ == '__main__':
    main()
