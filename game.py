from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
from screeninfo import get_monitors
import random
from collections import deque
from math import degrees, atan2, radians, sin, cos
from PIL import Image, ImageSequence
import os
import sys
import subprocess

#suporte gif
quadros_gif = []
indice_quadro = 0
tempo_quadro = 0

#app
app = Ursina()
som_ambiente = Audio(
    'respirar.wav',
    loop=True,
    autoplay=True,
    volume=0.35
)
monitor = get_monitors()[0]
window.fullscreen = False
window.borderless = True
window.size = (monitor.width, monitor.height)
window.position = (0, 0)

#céu
COR_CEU = color.rgb(2, 2, 6)
window.color = COR_CEU
camera.clear_color = COR_CEU
Sky(texture='céu.png', color=color.white)

#shader da laterna
lanterna_shader = Shader(
    language=Shader.GLSL,
    vertex='''
#version 140
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelMatrix;
uniform vec2 texture_scale;
uniform vec2 texture_offset;
in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;
in vec4 p3d_Color;
out vec2 uv;
out vec3 mundo;
out vec4 cor_vertice;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    uv = p3d_MultiTexCoord0 * texture_scale + texture_offset;
    mundo = (p3d_ModelMatrix * p3d_Vertex).xyz;
    cor_vertice = p3d_Color;
}
''',
    fragment='''
#version 140
uniform sampler2D p3d_Texture0;
uniform vec4 p3d_ColorScale;
uniform vec3 lanterna_pos;
uniform vec3 lanterna_dir;
uniform float lanterna_on;
in vec2 uv;
in vec3 mundo;
in vec4 cor_vertice;
out vec4 fragColor;
void main() {
    vec4 cor = texture(p3d_Texture0, uv) * p3d_ColorScale * cor_vertice;
    vec3 d = mundo - lanterna_pos;
    float dist = length(d);
    float angulo = dot(normalize(d), normalize(lanterna_dir));
    float cone = smoothstep(0.82, 0.95, angulo);
    float alcance = clamp(1.0 - dist / 30.0, 0.0, 1.0);
    float luz = 0.08 + lanterna_on * cone * alcance * 1.2;
    fragColor = vec4(cor.rgb * luz, cor.a);
}
'''
)
scene.set_shader_input('lanterna_pos', Vec3(0, 0, 0))
scene.set_shader_input('lanterna_dir', Vec3(0, 0, 1))
scene.set_shader_input('lanterna_on', 1.0)

#labirinto
N = 41
TAM_CELULA = 2.5
ALTURA_PAREDE = 5
RETICENCIA = 0.4
CHANCE_LACOS = 0.06

# Configuracoes do Tumulus
VELOCIDADE_TUMULUS = 2
DISTANCIA_TELEPORTE = 20
TEMPO_PROTECAO = 3.0
ALCANCE_LANTERNA = 30
DISTANCIA_DETECTAR = 20
DISTANCIA_PERDER = 40

# Configuracoes do cesar
VELOCIDADE_CARP = 0.3
alvo_carp = None
tempo_recalculo_carp = 0

# Configuracoes do Minotaurus
tempo_proximo_teleporte_minotaurus = 12.0

# Configurações do Chocolate
VELOCIDADE_CHOCOLATE = 1.0
VELOCIDADE_CHOCOLATE_PERSEGUINDO = 8.0
DISTANCIA_DETECTAR_CHOCOLATE = 25
TEMPO_OLHANDO_CHOCOLATE = 2.5
alvo_chocolate = None
tempo_recalculo_chocolate = 0
tempo_olhando_chocolate = 0
perseguindo_chocolate = False

# Configuracoes da Noiva
CHANCE_NOIVA = 0.5            # 50% de chance por partida
TEMPO_MIN_NOIVA = 61           # aparece entre 61s...
TEMPO_MAX_NOIVA = 480          # ...e 480s de jogo (meio da partida)
VELOCIDADE_NOIVA = 3.0         # um pouco mais lenta que o jogador (speed=4)
DISTANCIA_SEGUIR_NOIVA = 4.0   # não chega mais perto que isso
ALINHAMENTO_NOIVA = 0.8        # quão "no centro da tela" ela precisa estar para contar como vista
noiva = None
noiva_vai_aparecer = random.random() < CHANCE_NOIVA  # sorteio feito uma vez por partida
tempo_para_noiva = random.uniform(TEMPO_MIN_NOIVA, TEMPO_MAX_NOIVA)
noiva_vista = False
noiva_finalizada = False
alvo_noiva = None
tempo_recalculo_noiva = 0

# Configuracoes do Gingerbread
RAIO_GINGERBREAD = 1.0   # raio do bloqueio (o corredor tem meia largura de 1.25)
tempo_proximo_teleporte_gingerbread = random.uniform(15.0, 25.0)

# Bateria e Caveiras
BATERIA_MAXIMA = 1200.0  
bateria_lanterna = BATERIA_MAXIMA

TOTAL_CAVEIRAS = 25  
caveiras_coletadas = 0
lista_caveiras = []

# Estados de Jogo
morto = False
venceu = False
jogo_iniciado = True

# ATIVAÇÃO DOS MODELOS POR DISTÂNCIA
DISTANCIA_ATIVAR_MODELOS = 35
DISTANCIA_DESATIVAR_MODELOS = 45
INTERVALO_ATUALIZACAO_MODELOS = 0.25
tempo_atualizacao_modelos = 0
estado_modelos_monstros = {
    'tumulus': True,
    'carp': True,
    'minotaurus': True,
    'chocolate': True,
    'gingerbread': True
}

# GERACAO DO LABIRINTO
grade = [[1] * N for _ in range(N)]

def criar_tela_cheia(textura):
    return Entity(
        parent=camera.ui,
        model="quad",
        texture=textura,
        scale=(camera.aspect_ratio, 1),
        z=1   # fica atrás do botão
    )

def carregar_gif(caminho):
    gif = Image.open(caminho)
    quadros = []

    for quadro in ImageSequence.Iterator(gif):
        duracao = quadro.info.get("duration", 100) / 1000  # ler ANTES do convert
        imagem = quadro.convert("RGBA")
        quadros.append((Texture(imagem), duracao))

    return quadros

def gerar_labirinto():
    celulas = [(1, 1)]
    grade[1][1] = 0
    while celulas:
        if random.random() < RETICENCIA:
            idx = len(celulas) - 1
        else:
            idx = random.randrange(len(celulas))
        x, z = celulas[idx]
        vizinhos = []
        for dx, dz in ((2, 0), (-2, 0), (0, 2), (0, -2)):
            nx, nz = x + dx, z + dz
            if 0 < nx < N - 1 and 0 < nz < N - 1 and grade[nz][nx] == 1:
                vizinhos.append((nx, nz, dx, dz))
        if vizinhos:
            nx, nz, dx, dz = random.choice(vizinhos)
            grade[z + dz // 2][x + dx // 2] = 0
            grade[nz][nx] = 0
            celulas.append((nx, nz))
        else:
            celulas.pop(idx)

def abrir_lacos():
    for _ in range(int(N * N * CHANCE_LACOS)):
        x = random.randint(1, N - 2)
        z = random.randint(1, N - 2)
        if grade[z][x] == 1:
            horizontal = grade[z][x - 1] == 0 and grade[z][x + 1] == 0
            vertical = grade[z - 1][x] == 0 and grade[z + 1][x] == 0
            if horizontal or vertical:
                grade[z][x] = 0

gerar_labirinto()
abrir_lacos()

# CRIACAO DAS PAREDES
for z in range(N):
    for x in range(N):
        if grade[z][x] == 1:
            Entity(
                model='cube',
                shader=lanterna_shader,
                texture='parede.png',
                texture_scale=(1, ALTURA_PAREDE / TAM_CELULA),
                color=color.white,
                scale=(TAM_CELULA, ALTURA_PAREDE, TAM_CELULA),
                position=(x * TAM_CELULA, ALTURA_PAREDE / 2, z * TAM_CELULA),
                collider='box'
            )

# MONSTROS
tumulus = Entity(
    model='shadow.glb',
    scale=10,
    position=(TAM_CELULA, 1, TAM_CELULA),
    rotation=(0, 180, 0)
)

carp = Entity(
    model='macaco_assustador.glb',
    scale=8,
    position=(TAM_CELULA * 10, 1, TAM_CELULA * 10),
    rotation=(0, 180, 0)
)

minotaurus = Entity(
    model='minotaurus.glb',
    scale=10,
    position=(TAM_CELULA * 5, 1, TAM_CELULA * 5),
    rotation=(0, 180, 0)
)

chocolate = Entity(
    model='chocolate.glb',
    scale=15,
    position=(TAM_CELULA * 15, 1, TAM_CELULA * 15),
    rotation=(0, 180, 0)
)

biscoitos=[
    'biscoito.glb',
    'biscoito.glb',
    'biscoito.glb',
    'biscoito.glb',
    'biscoito.glb',
    'biscoito.glb',
    'biscoito mal.glb'
]

gingerbread = Entity(
    model=random.choice(biscoitos),
    scale = 8,
    position=(TAM_CELULA * 12, 1, TAM_CELULA * 12),
    rotation=(0, 180, 0)
)

perseguindo = False
alvo_tumulus = None
tempo_recalculo = 0
tempo_protecao = TEMPO_PROTECAO

# CHAO
centro = (N - 1) / 2 * TAM_CELULA
chao = Entity(
    model='plane',
    shader=lanterna_shader,
    scale=N * TAM_CELULA,
    position=(centro, 0, centro),
    texture='parede.png',
    texture_scale=(N, N),
    color=color.white,
    collider='box'
)

# JOGADOR
player = FirstPersonController(
    position=(TAM_CELULA, 2, TAM_CELULA),
    speed=4,
    jump_height=2,
    gravity=1
)
player.traverse_target = chao

def distancia_entre_jogador_e(entidade):
    dx = entidade.x - player.x
    dz = entidade.z - player.z
    return (dx * dx + dz * dz) ** 0.5


def atualizar_ativacao_monstro(nome, entidade):
    if entidade is None:
        return False

    ativo = estado_modelos_monstros[nome]
    distancia = distancia_entre_jogador_e(entidade)

    if not ativo and distancia <= DISTANCIA_ATIVAR_MODELOS:
        entidade.enabled = True
        estado_modelos_monstros[nome] = True
        return True

    elif ativo and distancia >= DISTANCIA_DESATIVAR_MODELOS:
        entidade.enabled = False
        estado_modelos_monstros[nome] = False
        return False
    return ativo


def atualizar_ativacao_todos_monstros():
    global tempo_atualizacao_modelos
    tempo_atualizacao_modelos -= time.dt
    if tempo_atualizacao_modelos > 0:
        return
    tempo_atualizacao_modelos = INTERVALO_ATUALIZACAO_MODELOS
    atualizar_ativacao_monstro('tumulus', tumulus)
    atualizar_ativacao_monstro('carp', carp)
    atualizar_ativacao_monstro('minotaurus', minotaurus)
    atualizar_ativacao_monstro('chocolate', chocolate)
    atualizar_ativacao_monstro('gingerbread', gingerbread)

# SONS
som_tumulus = Audio(
    'tumulus.mp3',
    loop=True,
    autoplay=True,
    volume=0
)
som_morte = Audio('boi_na_sala.wav', autoplay=False, volume=1)

# INTERFACE (UI)
lanterna_ligada = False
ctrl_antes = False

debug_tumulus = Text(
    text='Monstros: iniciando...',
    position=(-0.86, 0.46),
    scale=0.8,
    color=color.white,
    background=True
)

texto_bateria = Text(
    text='Bateria: 100%',
    position=(-0.86, 0.40),
    scale=0.8,
    color=color.yellow,
    background=True
)

texto_caveiras = Text(
    text=f'Caveiras: 0 / {TOTAL_CAVEIRAS}',
    position=(-0.86, 0.34),
    scale=0.8,
    color=color.cyan,
    background=True
)

texto_morte = Text(
    text='',
    position=(0, 0),
    origin=(0, 0),
    scale=2,
    color=color.red,
    background=True
)

texto_vitoria = Text(
    text='',
    position=(0, 0),
    origin=(0, 0),
    scale=2,
    color=color.green,
    background=True
)

# TELAS PERSONALIZADAS DE MORTE
tela_morte_imagem = None
texto_reiniciar = None
pode_reiniciar = False
IMAGENS_MORTE = {
    "tumulus": (
        "tumulus.gif",
        "0tumulus.png"
    ),
    "carp": (
        "carp.gif",
        "0carp.png"
    ),
    "minotaurus": (
        "minotaurus.gif",
        "0minotaurus.png"
    ),
    "chocolate": (
        "chocolate.gif",
        "0chocolate.png"
    )
}

def criar_tela_cheia(textura):
    return Entity(
        parent=camera.ui,
        model="quad",
        texture=textura,
        scale=(camera.aspect_ratio, 1),
        position=(0, 0, 1)  # atrás do botão
    )

def mostrar_tela_morte(monstro):
    global morto, tela_morte_imagem, pode_reiniciar
    global quadros_gif, indice_quadro, tempo_quadro

    if morto:
        return

    morto = True
    pode_reiniciar = False
    player.enabled = False

    # Esconde a interface
    texto_bateria.enabled = False
    texto_caveiras.enabled = False
    debug_tumulus.enabled = False
    minimapa.enabled = False

    som_tumulus.volume = 0
    som_ambiente.volume = 0

    # Som único de morte
    som_morte.play()

    caminho = IMAGENS_MORTE[monstro][0]

    if caminho.lower().endswith(".gif"):
        quadros_gif = carregar_gif(caminho)
        indice_quadro = 0
        tempo_quadro = 0
        tela_morte_imagem = criar_tela_cheia(quadros_gif[0][0])
    else:
        quadros_gif = []
        tela_morte_imagem = criar_tela_cheia(caminho)

    invoke(mostrar_segunda_tela_morte, monstro, delay=3)

def mostrar_segunda_tela_morte(monstro):
    global tela_morte_imagem, texto_reiniciar, quadros_gif, pode_reiniciar

    if not morto:   # se reiniciou antes, não faz nada
        return

    quadros_gif = []   # para a animação do GIF
    som_morte.stop()   # apague esta linha se quiser que o som termine sozinho

    if tela_morte_imagem:
        destroy(tela_morte_imagem)

    tela_morte_imagem = criar_tela_cheia(IMAGENS_MORTE[monstro][1])

    texto_reiniciar = Text(
        text='CTRL',
        origin=(0, 0),
        position=(0, -0.42),
        scale=1.5,
        color=color.white,
        background=True
    )

    pode_reiniciar = True

# MINI MAPA
TAM_MINIMAPA = 0.32   # tamanho na tela (1 = altura inteira da tela)

def criar_textura_minimapa():
    img = Image.new("RGBA", (N, N))
    pixels = img.load()

    for z in range(N):
        for x in range(N):
            if grade[z][x] == 1:
                cor = (15, 15, 20, 230)       # parede
            else:
                cor = (150, 150, 160, 230)    # corredor
            pixels[x, N - 1 - z] = cor        # +z fica para cima

    textura = Texture(img)
    textura.filtering = None                  # pixels nítidos, sem borrar
    return textura

minimapa = Entity(
    parent=camera.ui,
    model='quad',
    texture=criar_textura_minimapa(),
    scale=(TAM_MINIMAPA, TAM_MINIMAPA),
    position=(
        camera.aspect_ratio / 2 - TAM_MINIMAPA / 2 - 0.02,
        0.5 - TAM_MINIMAPA / 2 - 0.02,
        0
    )
)

moldura_minimapa = Entity(
    parent=minimapa,
    model='quad',
    color=color.gray,
    scale=1.03,
    z=0.01   # atrás do mapa
)

marcador_jogador = Entity(
    parent=minimapa,
    model='circle',
    color=color.red,
    scale=0.05,
    z=-0.01
)

marcador_frente = Entity(   # ponto amarelo que mostra para onde você olha
    parent=minimapa,
    model='circle',
    color=color.yellow,
    scale=0.025,
    z=-0.02
)

def atualizar_minimapa():
    u = (player.x / TAM_CELULA + 0.5) / N - 0.5
    v = (player.z / TAM_CELULA + 0.5) / N - 0.5

    marcador_jogador.position = (u, v, -0.01)

    ang = radians(player.rotation_y)
    marcador_frente.position = (
        u + sin(ang) * 0.03,
        v + cos(ang) * 0.03,
        -0.02
    )

def spawnar_caveiras():
    global lista_caveiras
    posicoes_livres = []
    for z in range(1, N - 1):
        for x in range(1, N - 1):
            if grade[z][x] == 0:
                px = x * TAM_CELULA
                pz = z * TAM_CELULA
                if ((px - 2) ** 2 + (pz - 2) ** 2) > 16:
                    posicoes_livres.append((px, pz))

    random.shuffle(posicoes_livres)
    quantidade = min(TOTAL_CAVEIRAS, len(posicoes_livres))

    for i in range(quantidade):
        px, pz = posicoes_livres[i]
        skull = Entity(
            model='skull.glb',
            scale=1.2,
            position=(px, 0.3, pz),
            rotation=(0, random.uniform(0, 360), 0)
        )
        lista_caveiras.append(skull)

spawnar_caveiras()
player.enabled = False
texto_bateria.enabled = False
texto_caveiras.enabled = False
debug_tumulus.enabled = False
minimapa.enabled = False
mouse.locked = False
mouse.visible = True

def teletransportar_tumulus():
    global alvo_tumulus, tempo_recalculo, tempo_protecao, perseguindo

    posicoes = []
    dist_atual = DISTANCIA_TELEPORTE

    while not posicoes and dist_atual > 5:
        for z in range(1, N - 1):
            for x in range(1, N - 1):
                if grade[z][x] != 0:
                    continue

                px = x * TAM_CELULA
                pz = z * TAM_CELULA
                distancia = ((px - player.x) ** 2 + (pz - player.z) ** 2) ** 0.5

                if distancia >= dist_atual:
                    posicoes.append((px, pz))
        if not posicoes:
            dist_atual -= 3

    if posicoes:
        px, pz = random.choice(posicoes)
        tumulus.position = (px, 1, pz)
    else:
        tumulus.position = ((N - 2) * TAM_CELULA, 1, (N - 2) * TAM_CELULA)

    alvo_tumulus = None
    tempo_recalculo = 1.0
    tempo_protecao = TEMPO_PROTECAO
    perseguindo = False

def teletransportar_carp():
    global alvo_carp
    posicoes = []
    dist_atual = 20

    while not posicoes and dist_atual > 5:
        for z in range(1, N - 1):
            for x in range(1, N - 1):
                if grade[z][x] != 0:
                    continue

                px = x * TAM_CELULA
                pz = z * TAM_CELULA
                distancia = ((px - player.x) ** 2 + (pz - player.z) ** 2) ** 0.5

                if distancia >= dist_atual:
                    posicoes.append((px, pz))
        if not posicoes:
            dist_atual -= 3

    if posicoes:
        px, pz = random.choice(posicoes)
        carp.position = (px, 1, pz)
    else:
        carp.position = (TAM_CELULA * 2, 1, TAM_CELULA * 2)

    alvo_carp = None


    posicoes = []
    dist_atual = 1

def teletransportar_gingerbread():
    posicoes = []
    dist_atual = 20

    while not posicoes and dist_atual > 5:
        for z in range(1, N - 1):
            for x in range(1, N - 1):
                if grade[z][x] != 0:
                    continue

                px = x * TAM_CELULA
                pz = z * TAM_CELULA

                distancia = (
                    (px - player.x) ** 2 +
                    (pz - player.z) ** 2
                ) ** 0.5

                if distancia >= dist_atual:
                    posicoes.append((px, pz))

        if not posicoes:
            dist_atual -= 3

    if posicoes:
        px, pz = random.choice(posicoes)
        gingerbread.position = (px, 1, pz)
    else:
        gingerbread.position = (
            TAM_CELULA * 3,
            1,
            TAM_CELULA * 3
        )

def teletransportar_minotaurus():
    posicoes = []
    dist_atual = 15

    while not posicoes and dist_atual > 5:
        for z in range(1, N - 1):
            for x in range(1, N - 1):
                if grade[z][x] != 0:
                    continue

                px = x * TAM_CELULA
                pz = z * TAM_CELULA
                distancia = ((px - player.x) ** 2 + (pz - player.z) ** 2) ** 0.5

                if distancia >= dist_atual:
                    posicoes.append((px, pz))
        if not posicoes:
            dist_atual -= 3

    if posicoes:
        px, pz = random.choice(posicoes)
        minotaurus.position = (px, 1, pz)
    else:
        minotaurus.position = (TAM_CELULA * 5, 1, TAM_CELULA * 5)

def teletransportar_chocolate():
    global alvo_chocolate

    posicoes = []

    for z in range(1, N - 1):
        for x in range(1, N - 1):
            if grade[z][x] == 0:
                px = x * TAM_CELULA
                pz = z * TAM_CELULA

                distancia = (
                    (px - player.x) ** 2 +
                    (pz - player.z) ** 2
                ) ** 0.5

                if distancia >= 25:
                    posicoes.append((px, pz))

    if posicoes:
        px, pz = random.choice(posicoes)
        chocolate.position = (px, 1, pz)
    else:
        chocolate.position = (
            TAM_CELULA * 2,
            1,
            TAM_CELULA * 2
        )

    alvo_chocolate = None

def celula_caminhavel_mais_proxima(celula):
    x, z = celula
    x = max(1, min(N - 2, x))
    z = max(1, min(N - 2, z))

    if grade[z][x] == 0:
        return (x, z)

    for raio in range(1, 8):
        for dz in range(-raio, raio + 1):
            for dx in range(-raio, raio + 1):
                nx, nz = x + dx, z + dz
                if 0 < nx < N - 1 and 0 < nz < N - 1 and grade[nz][nx] == 0:
                    return (nx, nz)

    return (1, 1)

def encontrar_caminho(inicio, destino):
    inicio = celula_caminhavel_mais_proxima(inicio)
    destino = celula_caminhavel_mais_proxima(destino)
    fila = deque([[inicio]])
    visitados = {inicio}

    while fila:
        caminho = fila.popleft()
        x, z = caminho[-1]

        if (x, z) == destino:
            return caminho

        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, nz = x + dx, z + dz

            if (
                0 <= nx < N
                and 0 <= nz < N
                and grade[nz][nx] == 0
                and (nx, nz) not in visitados
            ):
                visitados.add((nx, nz))
                fila.append(caminho + [(nx, nz)])

    return []

teletransportar_tumulus()
teletransportar_carp()
teletransportar_minotaurus()
teletransportar_chocolate()
teletransportar_gingerbread()

RAIO_JOGADOR = 0.45

def empurrar_para_fora_das_paredes():
    meio = TAM_CELULA / 2
    cx = round(player.x / TAM_CELULA)
    cz = round(player.z / TAM_CELULA)

    for gz in range(cz - 1, cz + 2):
        for gx in range(cx - 1, cx + 2):
            if not (0 <= gx < N and 0 <= gz < N) or grade[gz][gx] != 1:
                continue

            min_x = gx * TAM_CELULA - meio
            max_x = gx * TAM_CELULA + meio
            min_z = gz * TAM_CELULA - meio
            max_z = gz * TAM_CELULA + meio

            # ponto da parede mais próximo do jogador
            ponto_x = clamp(player.x, min_x, max_x)
            ponto_z = clamp(player.z, min_z, max_z)

            dx = player.x - ponto_x
            dz = player.z - ponto_z
            dist = (dx * dx + dz * dz) ** 0.5

            if dist >= RAIO_JOGADOR:
                continue

            if dist > 0.0001:
                empurrao = (RAIO_JOGADOR - dist) / dist
                player.x += dx * empurrao
                player.z += dz * empurrao
            else:
                # centro do jogador dentro da parede: sai pelo lado mais próximo
                opcoes = [
                    (player.x - min_x, min_x - RAIO_JOGADOR, player.z),
                    (max_x - player.x, max_x + RAIO_JOGADOR, player.z),
                    (player.z - min_z, player.x, min_z - RAIO_JOGADOR),
                    (max_z - player.z, player.x, max_z + RAIO_JOGADOR),
                ]
                _, player.x, player.z = min(opcoes, key=lambda o: o[0])

def aplicar_luz_lanterna(entidade, altura=1.5):
    ponto = entidade.world_position + Vec3(0, altura, 0)
    d = ponto - camera.world_position
    dist = d.length()

    luz = 0.08   # mesma luz ambiente do shader das paredes

    if lanterna_ligada and dist > 0.1:
        angulo = camera.forward.dot(d.normalized())

        # equivalente ao smoothstep(0.82, 0.95, angulo) do shader
        t = clamp((angulo - 0.82) / (0.95 - 0.82), 0, 1)
        cone = t * t * (3 - 2 * t)

        alcance = clamp(1 - dist / 30, 0, 1)
        luz += cone * alcance * 1.2

    luz = min(luz, 1)
    entidade.color = color.Color(luz, luz, luz, 1)

def spawnar_noiva():
    """Cria a Noiva atrás do jogador. Retorna False se não houver corredor livre atrás."""
    global noiva

    frente = Vec3(camera.forward.x, 0, camera.forward.z)
    if frente.length() < 0.01:
        frente = Vec3(0, 0, 1)
    atras = -frente.normalized()

    for dist in (6, 5, 4, 3):
        px = player.x + atras.x * dist
        pz = player.z + atras.z * dist
        cx = round(px / TAM_CELULA)
        cz = round(pz / TAM_CELULA)

        if 0 < cx < N - 1 and 0 < cz < N - 1 and grade[cz][cx] == 0:
            ALTURA_NOIVA = 3.5   # altura em unidades do mundo (a parede tem 5)

                # dentro de spawnar_noiva(), no lugar do Entity antigo:
            textura = load_texture('noiva.png')
            proporcao = textura.width / textura.height
            noiva = Entity(
                model='quad',
                texture=textura,
                scale=(ALTURA_NOIVA * proporcao, ALTURA_NOIVA),
                position=(px, ALTURA_NOIVA / 2, pz),   # pés no chão
                double_sided=True
            )
            return True
    return False

def noiva_esta_sendo_vista():
    vetor = noiva.world_position + Vec3(0, 1.5, 0) - camera.world_position
    dist = vetor.length()

    if dist < 0.1:
        return True

    direcao = vetor.normalized()

    if camera.forward.dot(direcao) < ALINHAMENTO_NOIVA:
        return False

    obstaculo = raycast(
        camera.world_position,
        direcao,
        distance=dist,
        ignore=[player, noiva],
        traverse_target=scene
    )

    return not obstaculo.hit

def atualizar_noiva():
    global noiva, noiva_vista, noiva_finalizada, tempo_para_noiva
    global alvo_noiva, tempo_recalculo_noiva

    if noiva_finalizada or not noiva_vai_aparecer:
        return

    # Ainda não apareceu: espera o tempo sorteado
    if noiva is None:
        tempo_para_noiva -= time.dt
        if tempo_para_noiva <= 0:
            spawnar_noiva()   # se falhar, tenta de novo no próximo frame
        return

    vista = noiva_esta_sendo_vista()

    if vista:
        noiva_vista = True
    elif noiva_vista:
        # já tinha visto e desviou o olhar: some para sempre
        destroy(noiva)
        noiva = None
        noiva_finalizada = True
        return

    # Sempre olha para o jogador
    angulo = degrees(atan2(player.x - noiva.x, player.z - noiva.z))
    noiva.rotation = (0, angulo + 180, 0)

    # Enquanto não foi vista, segue o jogador pelo labirinto
    if noiva_vista:
        return

    distancia = ((noiva.x - player.x) ** 2 + (noiva.z - player.z) ** 2) ** 0.5

    tempo_recalculo_noiva -= time.dt
    if tempo_recalculo_noiva <= 0:
        tempo_recalculo_noiva = 1.0

        caminho = encontrar_caminho(
            (round(noiva.x / TAM_CELULA), round(noiva.z / TAM_CELULA)),
            (round(player.x / TAM_CELULA), round(player.z / TAM_CELULA))
        )
        alvo_noiva = caminho[1] if len(caminho) > 1 else None

    if alvo_noiva is not None and distancia > DISTANCIA_SEGUIR_NOIVA:
        destino_x = alvo_noiva[0] * TAM_CELULA
        destino_z = alvo_noiva[1] * TAM_CELULA

        direcao = Vec3(destino_x - noiva.x, 0, destino_z - noiva.z)

        if direcao.length() > 0.15:
            noiva.position += direcao.normalized() * VELOCIDADE_NOIVA * time.dt
        else:
            noiva.x = destino_x
            noiva.z = destino_z
            alvo_noiva = None

def empurrar_jogador_para_fora_do_gingerbread():
    dx = player.x - gingerbread.x
    dz = player.z - gingerbread.z
    dist = (dx * dx + dz * dz) ** 0.5
    minimo = RAIO_JOGADOR + RAIO_GINGERBREAD

    if dist >= minimo:
        return

    if dist > 0.0001:
        fator = (minimo - dist) / dist
        player.x += dx * fator
        player.z += dz * fator
    else:
        player.x += minimo

def atualizar_gingerbread():
    global tempo_proximo_teleporte_gingerbread

    tempo_proximo_teleporte_gingerbread -= time.dt

    if tempo_proximo_teleporte_gingerbread <= 0:
        tempo_proximo_teleporte_gingerbread = random.uniform(15.0, 25.0)
        teletransportar_gingerbread()

reinicio_em_andamento = False

def reiniciar_partida():
    global reinicio_em_andamento

    if reinicio_em_andamento:
        return

    reinicio_em_andamento = True

    caminho_jogo = os.path.abspath(__file__)
    pasta_jogo = os.path.dirname(caminho_jogo)

    subprocess.Popen(
        [sys.executable, caminho_jogo],
        cwd=pasta_jogo
    )

    application.quit()

def update():
    global lanterna_ligada, ctrl_antes
    global tempo_recalculo, alvo_tumulus, tempo_protecao, perseguindo
    global bateria_lanterna, morto, venceu, caveiras_coletadas
    global alvo_carp, tempo_recalculo_carp
    global tempo_proximo_teleporte_minotaurus
    global alvo_chocolate, tempo_recalculo_chocolate
    global tempo_olhando_chocolate, perseguindo_chocolate
    global pode_reiniciar, texto_reiniciar, tela_morte_imagem
    global indice_quadro, tempo_quadro
    global quadros_gif
    global jogo_iniciado

    if not jogo_iniciado:
        return
    if morto or venceu:
        ctrl_reinicio = bool(
            held_keys['left control'] or held_keys['control']
        )
        if (venceu or pode_reiniciar) and ctrl_reinicio:
            reiniciar_partida()
        return

    empurrar_para_fora_das_paredes()
    atualizar_minimapa()
    atualizar_ativacao_todos_monstros()

    # BATERIA DA LANTERNA
    if lanterna_ligada:
        bateria_lanterna -= time.dt

        if bateria_lanterna <= 0:
            bateria_lanterna = 0
            lanterna_ligada = False

    porcentagem_bateria = int(
        (bateria_lanterna / BATERIA_MAXIMA) * 100
    )

    texto_bateria.text = f'Bateria: {porcentagem_bateria}%'

    texto_bateria.color = (
        color.yellow if porcentagem_bateria > 20
        else color.red
    )

    # Alternar lanterna com Ctrl
    ctrl_agora = bool(
        held_keys['left control'] or held_keys['control']
    )

    if ctrl_agora and not ctrl_antes:
        if bateria_lanterna > 0:
            lanterna_ligada = not lanterna_ligada

    ctrl_antes = ctrl_agora

    # Atualiza o shader da lanterna
    scene.set_shader_input(
        'lanterna_pos',
        camera.world_position
    )

    scene.set_shader_input(
        'lanterna_dir',
        camera.forward
    )

    scene.set_shader_input(
        'lanterna_on',
        1.0 if lanterna_ligada else 0.0
    )
    for nome, monstro in (
        ('tumulus', tumulus),
        ('carp', carp),
        ('minotaurus', minotaurus),
        ('chocolate', chocolate),
        ('gingerbread', gingerbread)
    ):
        if estado_modelos_monstros[nome]:
            aplicar_luz_lanterna(monstro)

        for caveira in lista_caveiras:
            if distancia_entre_jogador_e(caveira) <= DISTANCIA_ATIVAR_MODELOS:
                aplicar_luz_lanterna(caveira, altura=0)

    # ========================================================
    # TELETRANSPORTE PERIÓDICO DO MINOTAURUS
    # ========================================================
    tempo_proximo_teleporte_minotaurus -= time.dt

    if tempo_proximo_teleporte_minotaurus <= 0:
        tempo_proximo_teleporte_minotaurus = random.uniform(
            10.0, 15.0
        )

        teletransportar_minotaurus()

    atualizar_gingerbread()
    empurrar_jogador_para_fora_do_gingerbread()

    # ========================================================
    # COLETA DAS CAVEIRAS
    # ========================================================
    for caveira in lista_caveiras[:]:
        dist_sq = (
            (caveira.x - player.x) ** 2
            + (caveira.z - player.z) ** 2
        )

        if dist_sq < 2.25:
            destroy(caveira)
            lista_caveiras.remove(caveira)

            caveiras_coletadas += 1

            texto_caveiras.text = (
                f'Caveiras: {caveiras_coletadas} / '
                f'{TOTAL_CAVEIRAS}'
            )

            if caveiras_coletadas >= TOTAL_CAVEIRAS:
                venceu = True
                texto_bateria.enabled = False
                texto_caveiras.enabled = False

                texto_vitoria.text = (
                    "VOCÊ VENCEU!\n"
                    "Todas as caveiras foram coletadas!\n"
                    ""
                )

                som_tumulus.volume = 0
                som_ambiente.volume = 0
                player.enabled = False
                return

    # ========================================================
    # SOM DO TUMULUS
    # ========================================================
    dx_som = tumulus.x - player.x
    dz_som = tumulus.z - player.z

    distancia_som = (dx_som ** 2 + dz_som ** 2) ** 0.5

    volume_distancia = clamp(
        1 - distancia_som / 140,
        0,
        1
    )

    som_tumulus.volume = max(
        0.035,
        volume_distancia * 0.9
    )

    # Proteção inicial após o teletransporte do Tumulus
    tempo_protecao = max(
        0,
        tempo_protecao - time.dt
    )

    # ========================================================
    # LANterna TELETRANSPORTA O TUMULUS
    # ========================================================
    if lanterna_ligada and tempo_protecao <= 0:
        ponto_monstro = (
            tumulus.world_position + Vec3(0, 1.5, 0)
        )

        vetor = ponto_monstro - camera.world_position
        distancia_lanterna = vetor.length()

        if 0.1 < distancia_lanterna < ALCANCE_LANTERNA:
            alinhamento = camera.forward.dot(
                vetor.normalized()
            )

            if alinhamento > 0.90:
                obstaculo = raycast(
                    camera.world_position,
                    vetor.normalized(),
                    distance=distancia_lanterna,
                    ignore=[
                        player, tumulus, carp, minotaurus,
                        chocolate
                    ],
                    traverse_target=scene
                )

                if not obstaculo.hit:
                    teletransportar_tumulus()

    # ========================================================
    # DISTÂNCIAS DOS MONSTROS
    # ========================================================
    distancia_jogador_tumulus = (
        (tumulus.x - player.x) ** 2
        + (tumulus.z - player.z) ** 2
    ) ** 0.5

    distancia_jogador_carp = (
        (carp.x - player.x) ** 2
        + (carp.z - player.z) ** 2
    ) ** 0.5

    distancia_jogador_minotaurus = (
        (minotaurus.x - player.x) ** 2
        + (minotaurus.z - player.z) ** 2
    ) ** 0.5

    distancia_jogador_gingerbread = (
        (gingerbread.x - player.x) ** 2
        + (gingerbread.z - player.z) ** 2
    ) ** 0.5

    distancia_jogador_chocolate = (
        (chocolate.x - player.x) ** 2
        + (chocolate.z - player.z) ** 2
    ) ** 0.5

    atualizar_noiva()

    # ========================================================
    # IA E MOVIMENTO DO THE CARP
    # ========================================================
    tempo_recalculo_carp -= time.dt

    if tempo_recalculo_carp <= 0:
        tempo_recalculo_carp = 2

        inicio_carp = (
            round(carp.x / TAM_CELULA),
            round(carp.z / TAM_CELULA)
        )

        destino_carp = (
            round(player.x / TAM_CELULA),
            round(player.z / TAM_CELULA)
        )

        caminho_carp = encontrar_caminho(
            inicio_carp,
            destino_carp
        )

        if len(caminho_carp) > 1:
            alvo_carp = caminho_carp[1]

    if alvo_carp is not None:
        destino_x = alvo_carp[0] * TAM_CELULA
        destino_z = alvo_carp[1] * TAM_CELULA

        direcao_carp = Vec3(
            destino_x - carp.x,
            0,
            destino_z - carp.z
        )

        if direcao_carp.length() > 0.15:
            direcao_carp = direcao_carp.normalized()

            carp.position += (
                direcao_carp * VELOCIDADE_CARP * time.dt
            )

            angulo_carp = degrees(
                atan2(direcao_carp.x, direcao_carp.z)
            )

            carp.rotation = (
                0, angulo_carp + 180, 0
            )
        else:
            carp.x = destino_x
            carp.z = destino_z
            alvo_carp = None

       # ========================================================
    # IA DO CHOCOLATE
    # ========================================================

    # Verifica se o jogador está olhando diretamente para o Chocolate
    vetor_chocolate = (
        chocolate.world_position
        + Vec3(0, 1.5, 0)
        - camera.world_position
    )

    distancia_camera_chocolate = vetor_chocolate.length()
    olhando_chocolate = False

    if (
        distancia_camera_chocolate > 0.1
        and distancia_jogador_chocolate <= DISTANCIA_DETECTAR_CHOCOLATE
    ):
        direcao_visao_chocolate = vetor_chocolate.normalized()
        alinhamento_chocolate = camera.forward.dot(
            direcao_visao_chocolate
        )

        if alinhamento_chocolate > 0.94:
            obstaculo_chocolate = raycast(
                camera.world_position,
                direcao_visao_chocolate,
                distance=distancia_camera_chocolate,
                ignore=[
                    player,
                    chocolate,
                    tumulus,
                    carp,
                    minotaurus
                ],
                traverse_target=scene
            )

            if not obstaculo_chocolate.hit:
                olhando_chocolate = True

    # Acumula o tempo olhando para ele
    if not perseguindo_chocolate:
        if olhando_chocolate:
            tempo_olhando_chocolate += time.dt
        else:
            tempo_olhando_chocolate = 0

        # Depois de 2,5 segundos, ativa a perseguição rápida
        if tempo_olhando_chocolate >= TEMPO_OLHANDO_CHOCOLATE:
            perseguindo_chocolate = True
            tempo_recalculo_chocolate = 0

    # O Chocolate persegue devagar se estiver próximo.
    # Depois de ativado, persegue rápido mesmo se você parar de olhar.
    deve_perseguir = (
        perseguindo_chocolate
        or distancia_jogador_chocolate <= DISTANCIA_DETECTAR_CHOCOLATE
    )

    tempo_recalculo_chocolate -= time.dt

    # Calcula o caminho pelo labirinto
    if deve_perseguir and tempo_recalculo_chocolate <= 0:
        tempo_recalculo_chocolate = 1.0

        inicio_chocolate = (
            round(chocolate.x / TAM_CELULA),
            round(chocolate.z / TAM_CELULA)
        )

        destino_chocolate = (
            round(player.x / TAM_CELULA),
            round(player.z / TAM_CELULA)
        )

        caminho_chocolate = encontrar_caminho(
            inicio_chocolate,
            destino_chocolate
        )

        if len(caminho_chocolate) > 1:
            alvo_chocolate = caminho_chocolate[1]
        else:
            alvo_chocolate = None

    # Movimento do Chocolate
    if deve_perseguir and alvo_chocolate is not None:
        destino_x = alvo_chocolate[0] * TAM_CELULA
        destino_z = alvo_chocolate[1] * TAM_CELULA

        direcao_chocolate = Vec3(
            destino_x - chocolate.x,
            0,
            destino_z - chocolate.z
        )

        if direcao_chocolate.length() > 0.15:
            direcao_chocolate = direcao_chocolate.normalized()

            if perseguindo_chocolate:
                velocidade_atual = VELOCIDADE_CHOCOLATE_PERSEGUINDO
            else:
                velocidade_atual = VELOCIDADE_CHOCOLATE

            # Corrigido: usa direcao_chocolate
            chocolate.position += (
                direcao_chocolate
                * velocidade_atual
                * time.dt
            )

            angulo_chocolate = degrees(
                atan2(direcao_chocolate.x, direcao_chocolate.z)
            )

            chocolate.rotation = (
                0,
                angulo_chocolate + 180,
                0
            )
        else:
            chocolate.x = destino_x
            chocolate.z = destino_z
            alvo_chocolate = None

    # ========================================================
    # MORTE POR CONTATO COM O CHOCOLATE
    # ========================================================
    if distancia_jogador_chocolate < 1.8:
        mostrar_tela_morte("chocolate")
        return

    # ========================================================
    # MECÂNICA DO MINOTAURUS
    # ========================================================
    if (
        distancia_jogador_minotaurus < 2.5
        and tempo_protecao <= 0
    ):
        iluminando_minotaurus = False

        if lanterna_ligada:
            vetor_mino = (
                minotaurus.world_position
                + Vec3(0, 1.5, 0)
                - camera.world_position
            )

            dist_mino_cam = vetor_mino.length()

            if dist_mino_cam < 25:
                alinhamento_m = camera.forward.dot(
                    vetor_mino.normalized()
                )

                if alinhamento_m > 0.90:
                    obs_m = raycast(
                        camera.world_position,
                        vetor_mino.normalized(),
                        distance=dist_mino_cam,
                        ignore=[
                            player, minotaurus, tumulus,
                            carp, chocolate
                        ],
                        traverse_target=scene
                    )

                    if not obs_m.hit:
                        iluminando_minotaurus = True

        if iluminando_minotaurus:
            mostrar_tela_morte("minotaurus")
            return

        else:
            bateria_lanterna = max(
                0,
                bateria_lanterna - BATERIA_MAXIMA * 0.05
            )

            teletransportar_minotaurus()

    # ========================================================
    # MORTE POR CONTATO: TUMULUS OU CARP
    # ========================================================
    if (
        distancia_jogador_tumulus < 1.8
        or distancia_jogador_carp < 1.8
    ) and tempo_protecao <= 0:

        if distancia_jogador_tumulus < 1.8:
            mostrar_tela_morte("tumulus")
        else:
            mostrar_tela_morte("carp")

        return

    # ========================================================
    # IA DO TUMULUS
    # ========================================================
    if (
        not perseguindo
        and distancia_jogador_tumulus <= DISTANCIA_DETECTAR
    ):
        perseguindo = True
        tempo_recalculo = 0

    elif (
        perseguindo
        and distancia_jogador_tumulus >= DISTANCIA_PERDER
    ):
        perseguindo = False
        alvo_tumulus = None

    debug_tumulus.text = (
        ''
        #f'Tumulus: {"PERSEGUINDO" if perseguindo else "procurando"} | '
        #f'Carp dist: {distancia_jogador_carp:.1f} | '
        #f'Mino dist: {distancia_jogador_minotaurus:.1f} | '
        #f'Chocolate: {distancia_jogador_chocolate:.1f}'
    )

    if perseguindo:
        tempo_recalculo -= time.dt

        if tempo_recalculo <= 0:
            tempo_recalculo = 2.0

            inicio = (
                round(tumulus.x / TAM_CELULA),
                round(tumulus.z / TAM_CELULA)
            )

            destino = (
                round(player.x / TAM_CELULA),
                round(player.z / TAM_CELULA)
            )

            caminho = encontrar_caminho(
                inicio,
                destino
            )

            if len(caminho) > 1:
                alvo_tumulus = caminho[1]

        if alvo_tumulus is not None:
            destino_x = alvo_tumulus[0] * TAM_CELULA
            destino_z = alvo_tumulus[1] * TAM_CELULA

            direcao = Vec3(
                destino_x - tumulus.x,
                0,
                destino_z - tumulus.z
            )

            if direcao.length() > 0.15:
                direcao = direcao.normalized()

                tumulus.position += (
                    direcao * VELOCIDADE_TUMULUS * time.dt
                )

                angulo = degrees(
                    atan2(direcao.x, direcao.z)
                )

                tumulus.rotation = (
                    0, angulo + 180, 0
                )
            else:
                tumulus.x = destino_x
                tumulus.z = destino_z
                alvo_tumulus = None
    if morto and quadros_gif and tela_morte_imagem:
        tempo_quadro += time.dt

        duracao = quadros_gif[indice_quadro][1]

        if tempo_quadro >= max(duracao, 0.02):
            tempo_quadro = 0
            indice_quadro = (indice_quadro + 1) % len(quadros_gif)

            tela_morte_imagem.texture = quadros_gif[indice_quadro][0]

def input(key):
    if key == 'm' and not morto and not venceu:
        minimapa.enabled = not minimapa.enabled

app.run()