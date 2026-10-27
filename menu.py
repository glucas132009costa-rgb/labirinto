from ursina import *
from screeninfo import get_monitors
from PIL import Image, ImageSequence
import os
import sys
import subprocess

# ============================================================
# CONFIGURAÇÕES (troque aqui)
# ============================================================
TITULO = "LABIRINTO"
ARQUIVO_FUNDO = "menu.gif"   # GIF de tela inteira do menu
ARQUIVO_JOGO = "game.py"

PASTA = os.path.dirname(os.path.abspath(__file__))

# ============================================================
# APP E JANELA
# ============================================================
app = Ursina()

monitor = get_monitors()[0]
window.fullscreen = False
window.borderless = True
window.size = (monitor.width, monitor.height)
window.position = (0, 0)
window.color = color.black
window.exit_button.visible = False

mouse.locked = False
mouse.visible = True

# ============================================================
# FUNDO (GIF ANIMADO)
# ============================================================
quadros_gif = []
indice_quadro = 0
tempo_quadro = 0


def carregar_gif(caminho):
    gif = Image.open(caminho)
    quadros = []

    for quadro in ImageSequence.Iterator(gif):
        duracao = quadro.info.get("duration", 100) / 1000  # ler ANTES do convert
        imagem = quadro.convert("RGBA")
        quadros.append((Texture(imagem), duracao))

    return quadros


caminho_fundo = os.path.join(PASTA, ARQUIVO_FUNDO)

fundo = Entity(
    parent=camera.ui,
    model="quad",
    scale=(camera.aspect_ratio, 1),
    position=(0, 0, 1),
    color=color.black
)

if os.path.exists(caminho_fundo):
    quadros_gif = carregar_gif(caminho_fundo)
    fundo.texture = quadros_gif[0][0]
    fundo.color = color.white
else:
    print(f"[menu] '{ARQUIVO_FUNDO}' não encontrado. Usando fundo preto.")

# ============================================================
# TÍTULO E BOTÃO START
# ============================================================
titulo = Text(
    text=TITULO,
    origin=(0, 0),
    position=(0, 0.25),
    scale=4,
    color=color.white
)


def iniciar_jogo():
    subprocess.Popen(
        [sys.executable, os.path.join(PASTA, ARQUIVO_JOGO)],
        cwd=PASTA
    )
    application.quit()


botao_start = Button(
    parent=camera.ui,
    text="START",
    scale=(0.3, 0.08),
    position=(0, -0.1),
    color=color.rgba(0, 0, 0, 160),
    highlight_color=color.rgba(120, 0, 0, 200),
    pressed_color=color.rgba(200, 0, 0, 220),
    on_click=iniciar_jogo
)


# ============================================================
# UPDATE E TECLAS
# ============================================================
def update():
    global indice_quadro, tempo_quadro

    if quadros_gif:
        tempo_quadro += time.dt
        duracao = quadros_gif[indice_quadro][1]

        if tempo_quadro >= max(duracao, 0.02):
            tempo_quadro = 0
            indice_quadro = (indice_quadro + 1) % len(quadros_gif)
            fundo.texture = quadros_gif[indice_quadro][0]


def input(key):
    if key in ("enter", "space"):
        iniciar_jogo()


app.run()