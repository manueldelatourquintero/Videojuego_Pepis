import pygame
import sys
import os
import math
import random
import json
import numpy as np

from tilemap import make_tilemap

# ══════════════════════════════════════════════
#  SISTEMA DE COLISIONES CENTRALIZADO
#  Usado por Player Y Enemy — misma función, mismas reglas.
# ══════════════════════════════════════════════
def move_and_collide(entity, vx, vy, solid_tiles):
    """
    Mueve 'entity' por (vx, vy) resolviendo colisiones AABB con solid_tiles.
    Separa ejes X e Y para evitar clipping diagonal.

    Hitbox = sprite contraído MX píxeles a cada lado y MY desde arriba.
    La resolución coloca la entidad exactamente en el borde del tile,
    sin offset residual → sin efecto pegajoso ni jitter.

    Devuelve (hit_wall_x, hit_wall_y).
    """
    MX = 4   # margen lateral (px a cada lado)
    MY = 2   # margen superior (px desde arriba)

    hit_wall_x = False
    hit_wall_y = False

    # ── Eje X ────────────────────────────────────────────────────
    # Aplica movimiento horizontal y resuelve contra cada tile.
    # El hitbox horizontal ocupa [wx+MX .. wx+W-MX] × [wy+MY .. wy+H].
    entity.wx += vx
    if vx != 0 and solid_tiles:
        hb = pygame.Rect(int(entity.wx) + MX, int(entity.wy) + MY,
                         entity.W - MX * 2,   entity.H - MY)
        for tile in solid_tiles:
            if not hb.colliderect(tile):
                continue
            if vx > 0:
                # Borde derecho del hitbox = tile.left
                # wx + (W - MX) = tile.left  →  wx = tile.left - W + MX
                entity.wx = float(tile.left - entity.W + MX)
            else:
                # Borde izquierdo del hitbox = tile.right
                # wx + MX = tile.right  →  wx = tile.right - MX
                entity.wx = float(tile.right - MX)
            hit_wall_x = True
            break   # un solo tile resuelto por eje evita jitter

    # ── Eje Y ────────────────────────────────────────────────────
    # Aplica movimiento vertical y resuelve contra cada tile.
    # El hitbox vertical ocupa [wx+MX .. wx+W-MX] × [wy+MY .. wy+H].
    entity.wy += vy
    if vy != 0 and solid_tiles:
        hb = pygame.Rect(int(entity.wx) + MX, int(entity.wy) + MY,
                         entity.W - MX * 2,   entity.H - MY)
        for tile in solid_tiles:
            if not hb.colliderect(tile):
                continue
            if vy > 0:
                # Pie sobre la superficie del tile
                # wy + H = tile.top  →  wy = tile.top - H
                entity.wy        = float(tile.top - entity.H)
                entity.vy        = 0.0
                entity.on_ground = True
            else:
                # Cabeza contra la cara inferior del tile
                # wy + MY = tile.bottom  →  wy = tile.bottom - MY
                entity.wy = float(tile.bottom - MY)
                entity.vy = 0.0
            hit_wall_y = True
            break

    return hit_wall_x, hit_wall_y

# ══════════════════════════════════════════════
#  CONSTANTES GLOBALES
# ══════════════════════════════════════════════
SW, SH          = 1000, 600
FPS             = 60
TITLE           = "El Pepis v3 — Ingeniería de Sistemas"

GRAVITY         = 0.55
JUMP_V          = -15.0
DJUMP_V         = -12.0
JUMP_HOLD_BOOST = 0.45
JUMP_HOLD_MAX   = 18
MOVE_SPD        = 5.2
TILE            = 48

PLAYER_H        = 72
PLAYER_MAX_HP   = 100
HIT_DAMAGE      = 10
IFRAMES         = 90

FB_SPEED        = 5.5
FB_COOLDOWN     = 70    # era 130 — reducido para que el enemigo dispare más rápido

ENEMY_H         = 54
ENEMY_W         = 52

SAVE_FILE       = "pepis_save.json"

# ── Paleta ─────────────────────────────────────────────────────────
C_SKY      = (18,  20,  50)
C_SKY2     = (35,  40,  90)
C_GROUND   = (55,  60,  90)
C_GLINE    = (80,  85, 125)
C_TILE     = (70,  80, 120)
C_TILE_T   = (95, 110, 160)
C_TILE_S   = (50,  58,  95)
C_PLATFORM = (80,  95, 140)
C_PLAT_T   = (110, 130, 175)
C_ENEMY    = (200,  40,  40)
C_EATT     = (255,  80,  20)
C_EEYE     = (255, 220,  80)
C_FIRE     = (255, 140,  20)
C_FIRE2    = (255, 220,  60)
C_TEXT     = (230, 230, 255)
C_ACC      = (120, 200, 255)
C_RED      = (255,  70,  70)
C_GREEN    = ( 80, 220, 120)
C_GOLD     = (255, 210,  50)
C_HP_BG    = ( 40,  20,  20)
C_HP_FG    = (220,  50,  50)
C_HP_FG2   = (255, 160,  50)
C_FLAG     = ( 50, 220, 100)
C_FLAGP    = (200, 200, 200)
C_SKULL    = (220, 200, 180)
C_SKULL_D  = ( 60,  55,  75)


# ══════════════════════════════════════════════
#  SONIDO — con música distinta por nivel
# ══════════════════════════════════════════════
def _synth_sound(freq, duration, shape="sine", volume=0.4,
                 decay=1.0, sample_rate=22050):
    n  = int(sample_rate * duration)
    t  = np.linspace(0, duration, n, endpoint=False)
    if shape == "sine":
        wave = np.sin(2 * np.pi * freq * t)
    elif shape == "square":
        wave = np.sign(np.sin(2 * np.pi * freq * t))
    elif shape == "saw":
        wave = 2 * (t * freq - np.floor(t * freq + 0.5))
    elif shape == "noise":
        wave = np.random.uniform(-1, 1, n)
    else:
        wave = np.sin(2 * np.pi * freq * t)
    env  = np.exp(-decay * t / duration * 5)
    wave = wave * env * volume
    wi   = (wave * 32767).astype(np.int16)
    st   = np.column_stack([wi, wi])
    return pygame.sndarray.make_sound(np.ascontiguousarray(st))


def _synth_music(pattern, bpm=120, sample_rate=22050):
    """
    Genera música sintetizada distinta por patrón.
    Patrones disponibles: "menu", "level_1", "level_2", "level_3", "level_4", "level_5"
    Cada nivel tiene notas base, BPM y timbre propios.
    """
    beat = 60.0 / bpm

    # ── Configuración por patrón ──────────────────────────────────
    configs = {
        "menu": {
            "notes": [220, 261, 329, 392, 440, 392, 329, 261],
            "bpm": 100, "dur_mult": 0.4, "vol": 0.18, "dec": 0.8,
            "harmonics": [(1.0, 0.6), (2.0, 0.25), (0.5, 0.15)],
        },
        "level_1": {
            # Aventura animada — mayor, tempo medio
            "notes": [330, 392, 494, 392, 330, 262, 294, 330],
            "bpm": 128, "dur_mult": 0.25, "vol": 0.22, "dec": 1.2,
            "harmonics": [(1.0, 0.5), (2.0, 0.3), (3.0, 0.1), (0.5, 0.1)],
        },
        "level_2": {
            # Misterioso — escala menor, tempo lento
            "notes": [220, 261, 311, 370, 311, 261, 233, 220],
            "bpm": 108, "dur_mult": 0.35, "vol": 0.20, "dec": 0.9,
            "harmonics": [(1.0, 0.55), (1.5, 0.25), (0.5, 0.20)],
        },
        "level_3": {
            # Urgente — tempo rápido, notas agudas
            "notes": [440, 494, 587, 659, 587, 494, 440, 392],
            "bpm": 148, "dur_mult": 0.20, "vol": 0.24, "dec": 1.5,
            "harmonics": [(1.0, 0.45), (2.0, 0.35), (3.0, 0.15), (4.0, 0.05)],
        },
        "level_4": {
            # Oscuro y pesado — bajo, notas graves
            "notes": [110, 130, 155, 175, 155, 130, 117, 110],
            "bpm": 116, "dur_mult": 0.30, "vol": 0.28, "dec": 0.7,
            "harmonics": [(1.0, 0.6), (2.0, 0.2), (0.5, 0.2)],
        },
        "level_5": {
            # Épico final — mezcla alto-bajo, tempo intenso
            "notes": [523, 392, 659, 494, 784, 587, 523, 440],
            "bpm": 160, "dur_mult": 0.18, "vol": 0.26, "dec": 1.8,
            "harmonics": [(1.0, 0.4), (2.0, 0.3), (3.0, 0.2), (0.5, 0.1)],
        },
    }

    cfg   = configs.get(pattern, configs["menu"])
    notes = cfg["notes"]
    bpm_  = cfg["bpm"]
    beat_ = 60.0 / bpm_
    dur   = beat_ * cfg["dur_mult"]
    vol   = cfg["vol"]
    dec   = cfg["dec"]
    harms = cfg["harmonics"]

    total = int(sample_rate * dur * len(notes))
    buf   = np.zeros(total, dtype=np.float32)

    for i, freq in enumerate(notes):
        s = int(i * dur * sample_rate)
        n = int(dur * sample_rate)
        t = np.linspace(0, dur, n, endpoint=False)
        w = np.zeros(n, dtype=np.float32)
        for mult, amp in harms:
            w += np.sin(2 * np.pi * freq * mult * t) * amp
        e   = np.exp(-dec * t / dur * 5)
        seg = w * e * vol
        end = min(s + n, total)
        buf[s:end] += seg[:end - s]

    mx  = np.max(np.abs(buf)) or 1
    buf = buf / mx * 0.9
    wi  = (buf * 32767).astype(np.int16)
    st  = np.column_stack([wi, wi])
    return pygame.sndarray.make_sound(np.ascontiguousarray(st))


class SoundManager:
    SFX_PATHS = {
        "stomp":    "assets/sounds/stomp.wav",
        "hit":      "assets/sounds/hit.wav",
        "shoot":    "assets/sounds/shoot.wav",
        "select":   "assets/sounds/select.wav",
        "correct":  "assets/sounds/correct.wav",
        "gameover": "assets/sounds/gameover.wav",
        "levelwin": "assets/sounds/levelwin.wav",
    }
    # Rutas de música por pista — nivel_N primero, fallback a gameplay genérico
    MUSIC_PATHS = {
        "menu":    "assets/music/menu.ogg",
        "level_1": "assets/music/level1.ogg",
        "level_2": "assets/music/level2.ogg",
        "level_3": "assets/music/level3.ogg",
        "level_4": "assets/music/level4.ogg",
        "level_5": "assets/music/level5.ogg",
        # fallback genérico si no existe el archivo específico del nivel
        "gameplay": "assets/music/gameplay.ogg",
    }
    # Nombres de pista por índice de nivel (0-based)
    LEVEL_TRACKS = ["level_1", "level_2", "level_3", "level_4", "level_5"]

    def __init__(self, base_dir):
        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
        pygame.mixer.set_num_channels(16)
        self._base   = base_dir
        self._sounds = {}
        self._music_synth = {}
        self._current_music = ""
        self._music_channel = None
        self.sfx_volume   = 0.7
        self.music_volume = 0.35
        self._load_sfx()
        self._load_music_synth()

    def _load_sfx(self):
        fallbacks = {
            "stomp":    (180, 0.12, "square", 0.55, 3.5),
            "hit":      (120, 0.25, "noise",  0.60, 2.0),
            "shoot":    (440, 0.18, "saw",    0.35, 2.5),
            "select":   (660, 0.10, "sine",   0.45, 2.0),
            "correct":  (523, 0.40, "sine",   0.50, 1.2),
            "gameover": ( 80, 0.80, "square", 0.45, 0.6),
            "levelwin": (660, 0.60, "sine",   0.50, 0.8),
        }
        for name, rel in self.SFX_PATHS.items():
            abs_p = os.path.join(self._base, rel)
            if os.path.exists(abs_p):
                try:
                    s = pygame.mixer.Sound(abs_p)
                    s.set_volume(self.sfx_volume)
                    self._sounds[name] = s
                    continue
                except Exception:
                    pass
            f, d, sh, v, dc = fallbacks[name]
            self._sounds[name] = _synth_sound(f, d, sh, v * self.sfx_volume, dc)

    def _load_music_synth(self):
        """Pre-genera música sintetizada para menú y cada nivel."""
        patterns = ["menu", "level_1", "level_2", "level_3", "level_4", "level_5"]
        for key in patterns:
            s = _synth_music(key)
            s.set_volume(self.music_volume)
            self._music_synth[key] = s

    def play(self, name):
        s = self._sounds.get(name)
        if s:
            s.play()

    def play_music(self, track):
        """
        Reproduce la pista indicada.
        Si ya está sonando esa pista, no hace nada (evita reiniciar).
        Prioridad: archivo .ogg del nivel → synth generado.
        """
        if self._current_music == track:
            return
        self._current_music = track

        # Detener lo que suena
        pygame.mixer.music.stop()
        if self._music_channel:
            self._music_channel.stop()
            self._music_channel = None

        # Intentar cargar archivo real (específico del nivel primero,
        # luego fallback "gameplay" genérico)
        candidates = [track]
        if track.startswith("level_"):
            candidates.append("gameplay")

        for candidate in candidates:
            rel  = self.MUSIC_PATHS.get(candidate, "")
            absp = os.path.join(self._base, rel)
            if rel and os.path.exists(absp):
                try:
                    pygame.mixer.music.load(absp)
                    pygame.mixer.music.set_volume(self.music_volume)
                    pygame.mixer.music.play(-1)
                    return
                except Exception:
                    pass

        # Fallback: synth generado
        synth = self._music_synth.get(track)
        if synth:
            self._music_channel = synth.play(loops=-1)

    def play_level_music(self, level_idx: int):
        """Atajo: reproduce la música del nivel dado (0-based)."""
        track = self.LEVEL_TRACKS[level_idx] if level_idx < len(self.LEVEL_TRACKS) else "level_1"
        self.play_music(track)

    def stop_music(self):
        pygame.mixer.music.stop()
        if self._music_channel:
            self._music_channel.stop()
            self._music_channel = None
        self._current_music = ""

    def set_sfx_volume(self, v):
        self.sfx_volume = max(0.0, min(1.0, v))
        for s in self._sounds.values():
            s.set_volume(self.sfx_volume)

    def set_music_volume(self, v):
        self.music_volume = max(0.0, min(1.0, v))
        pygame.mixer.music.set_volume(self.music_volume)
        for s in self._music_synth.values():
            s.set_volume(self.music_volume)


# ══════════════════════════════════════════════
#  UTILIDADES
# ══════════════════════════════════════════════
def load_img(path, height):
    if os.path.exists(path):
        img   = pygame.image.load(path).convert_alpha()
        ratio = height / img.get_height()
        return pygame.transform.scale(img,
               (max(1, int(img.get_width() * ratio)), height))
    return None


def make_placeholder(w, h, color, label="?"):
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(s, color, (0, 0, w, h), border_radius=6)
    pygame.draw.rect(s, (255, 255, 255, 60), (0, 0, w, h), 2, border_radius=6)
    f = pygame.font.SysFont("consolas", 14, bold=True)
    t = f.render(label, True, (255, 255, 255))
    s.blit(t, (w // 2 - t.get_width() // 2, h // 2 - t.get_height() // 2))
    return s


def draw_grad_bg(surface, rect, c1, c2):
    x, y, w, h = rect
    for i in range(h):
        t = i / max(h - 1, 1)
        r = int(c1[0] + (c2[0] - c1[0]) * t)
        g = int(c1[1] + (c2[1] - c1[1]) * t)
        b = int(c1[2] + (c2[2] - c1[2]) * t)
        pygame.draw.line(surface, (r, g, b), (x, y + i), (x + w, y + i))


def shadow_text(surf, txt, font, col, x, y, sh_col=(0, 0, 0), off=2):
    surf.blit(font.render(txt, True, sh_col), (x + off, y + off))
    surf.blit(font.render(txt, True, col),    (x,        y))


# ══════════════════════════════════════════════
#  SCREEN SHAKE
# ══════════════════════════════════════════════
class ScreenShake:
    def __init__(self):
        self.trauma     = 0.0
        self.decay      = 0.08
        self.max_offset = 10

    def add(self, amount=0.4):
        self.trauma = min(1.0, self.trauma + amount)

    def update(self):
        self.trauma = max(0.0, self.trauma - self.decay)

    def offset(self):
        if self.trauma <= 0:
            return 0, 0
        s  = self.trauma ** 2
        ox = random.uniform(-1, 1) * self.max_offset * s
        oy = random.uniform(-1, 1) * self.max_offset * s
        return int(ox), int(oy)


# ══════════════════════════════════════════════
#  PARTICLE POOL
# ══════════════════════════════════════════════
class Particle:
    __slots__ = ("x","y","vx","vy","life","max_life","color","size","alive")

    def __init__(self):
        self.alive = False

    def spawn(self, x, y, color):
        self.x        = float(x)
        self.y        = float(y)
        self.vx       = random.uniform(-4.5, 4.5)
        self.vy       = random.uniform(-6.5, -0.5)
        self.life     = random.randint(18, 36)
        self.max_life = self.life
        self.color    = color
        self.size     = random.randint(3, 7)
        self.alive    = True

    def update(self):
        if not self.alive:
            return
        self.x    += self.vx
        self.y    += self.vy
        self.vy   += 0.32
        self.life -= 1
        if self.life <= 0:
            self.alive = False

    def draw(self, surface, cam_x):
        if not self.alive:
            return
        a = self.life / self.max_life
        s = max(1, int(self.size * a))
        pygame.draw.circle(surface, self.color,
                           (int(self.x - cam_x), int(self.y)), s)


class ParticlePool:
    def __init__(self, max_count=300):
        self._pool = [Particle() for _ in range(max_count)]

    def spawn(self, x, y, color, count=1):
        spawned = 0
        for p in self._pool:
            if not p.alive:
                p.spawn(x, y, color)
                spawned += 1
                if spawned >= count:
                    return

    def update(self):
        for p in self._pool:
            if p.alive:
                p.update()

    def draw(self, surface, cam_x):
        for p in self._pool:
            if p.alive:
                p.draw(surface, cam_x)


# ══════════════════════════════════════════════
#  CAMERA
# ══════════════════════════════════════════════
class Camera:
    DEAD_LEFT  = SW * 0.30
    DEAD_RIGHT = SW * 0.65

    def __init__(self, world_w):
        self.x        = 0.0
        self.target_x = 0.0
        self.world_w  = world_w
        self.smooth   = 0.10

    def follow(self, target_cx):
        screen_x = target_cx - self.x
        if screen_x < self.DEAD_LEFT:
            self.target_x = target_cx - self.DEAD_LEFT
        elif screen_x > self.DEAD_RIGHT:
            self.target_x = target_cx - self.DEAD_RIGHT
        self.x += (self.target_x - self.x) * self.smooth
        self.x  = max(0, min(self.x, self.world_w - SW))

    def apply(self, wx):
        return int(wx - self.x)

    def in_view(self, wx, margin=80):
        sx = wx - self.x
        return -margin < sx < SW + margin


# ══════════════════════════════════════════════
#  FIREBALL
# ══════════════════════════════════════════════
class Fireball:
    RADIUS = 9

    def __init__(self, wx, wy, target_wx, target_wy):
        self.wx    = float(wx)
        self.wy    = float(wy)
        dx = target_wx - wx
        dy = target_wy - wy
        d  = math.hypot(dx, dy) or 1
        self.vx    = FB_SPEED * dx / d
        self.vy    = FB_SPEED * dy / d
        self.alive = True
        self.tick  = 0

    def update(self, world_w):
        self.wx   += self.vx
        self.wy   += self.vy
        self.tick += 1
        if self.wx < 0 or self.wx > world_w or self.wy > SH + 100:
            self.alive = False

    def draw(self, surface, cam):
        if not self.alive:
            return
        sx   = cam.apply(self.wx)
        sy   = int(self.wy)
        R    = self.RADIUS
        glow = pygame.Surface((R * 4, R * 4), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*C_FIRE, 55), (R * 2, R * 2), R * 2)
        surface.blit(glow, (sx - R * 2, sy - R * 2))
        flicker = int(math.sin(self.tick * 0.5) * 2)
        pygame.draw.circle(surface, C_FIRE,  (sx, sy), R + flicker)
        pygame.draw.circle(surface, C_FIRE2, (sx, sy), max(3, R - 3))

    def get_rect(self):
        r = self.RADIUS
        return pygame.Rect(int(self.wx) - r, int(self.wy) - r, r * 2, r * 2)


# ══════════════════════════════════════════════
#  ENEMY
# ══════════════════════════════════════════════
class Enemy:
    W, H = ENEMY_W, ENEMY_H
    VISION_RANGE  = 500
    CHASE_RANGE   = 480
    ATTACK_RANGE  = 340
    EVADE_RANGE   = 70
    BURST_SIZE_MIN = 2
    BURST_SIZE_MAX = 3
    BURST_INTERVAL = 22
    BURST_COOLDOWN = FB_COOLDOWN
    JUMP_SPEED  = -13.0
    JUMP_WINDOW = 2 * TILE
    AI_INTERVAL = 6

    def __init__(self, wx, wy, img_idle=None, img_attack=None):
        self.wx  = float(wx)
        self.wy  = float(wy)
        self.vy  = 0.0
        self.base_speed = random.uniform(1.2, 2.2)
        self.direction  = random.choice([-1, 1])
        self.alive     = True
        self.die_timer = 0
        self.img_idle      = img_idle   or make_placeholder(self.W, self.H, C_ENEMY, "E")
        self.img_attack    = img_attack or make_placeholder(self.W, self.H, C_EATT,  "E!")
        self.img_idle_fl   = pygame.transform.flip(self.img_idle,   True, False)
        self.img_attack_fl = pygame.transform.flip(self.img_attack, True, False)
        self.just_fired = False
        self.on_ground = False
        self.tick      = 0
        self.patrol_left  = wx - random.randint(60, 180)
        self.patrol_right = wx + random.randint(60, 180)
        self.state       = "patrol"
        self.state_timer = 0
        self.burst_shots_left = 0
        self.burst_timer      = 0
        self.cooldown_timer   = random.randint(20, FB_COOLDOWN // 2)
        self.attack_flash = 0
        self.aggressive_timer = 0
        self._ai_tick          = random.randint(0, self.AI_INTERVAL)
        self._cached_dist      = 999.0
        self._cached_dx        = 0.0
        self._cached_can_see   = False
        self._prev_player_wx = wx
        self._prev_player_wy = wy

    def update(self, solid_tiles, platforms, ground_y, player_wx, player_wy,
               fireballs, world_w):
        """
        solid_tiles — misma lista que usa el jugador (un solo origen de verdad)
        platforms   — plataformas one-way
        """
        if not self.alive:
            self.die_timer -= 1
            return

        self.tick      += 1
        self.just_fired = False

        # ── Actualizar caché de IA ────────────────────────────────
        # Se fuerza en el primer frame (tick==1) para que el estado
        # inicial sea correcto y el enemigo no quede quieto al spawn.
        self._ai_tick += 1
        if self._ai_tick >= self.AI_INTERVAL or self.tick == 1:
            self._ai_tick = 0
            self._update_ai_cache(player_wx, player_wy)

        # ── Física vertical ───────────────────────────────────────
        self.vy       += GRAVITY
        self.on_ground = False
        vy_before = self.vy   # capturar antes de move_and_collide

        # ── Velocidad horizontal deseada según FSM ────────────────
        vx_intended = self._calc_vx(player_wx, player_wy, fireballs, world_w)

        # ── Colisión con tiles (X e Y separados, misma función que Player) ─
        hit_x, _ = move_and_collide(self, vx_intended, self.vy, solid_tiles)

        # Chocó con pared lateral → invertir dirección inmediatamente
        if hit_x:
            self.direction    *= -1
            self.patrol_left   = self.wx - random.randint(40, 120)
            self.patrol_right  = self.wx + random.randint(40, 120)

        # ── Suelo base absoluto (safety net) ──────────────────────
        if self.wy + self.H >= ground_y:
            self.wy        = float(ground_y - self.H)
            self.vy        = 0.0
            self.on_ground = True

        # ── Plataformas one-way ────────────────────────────────────
        if vy_before > 0 and not self.on_ground:
            foot_y      = self.wy + self.H
            prev_foot_y = foot_y - vy_before
            for p in platforms:
                foot_rect = pygame.Rect(int(self.wx) + 6, int(foot_y) - 6,
                                        self.W - 12, 8)
                if foot_rect.colliderect(p) and prev_foot_y <= p.top + 6:
                    self.wy        = float(p.top - self.H)
                    self.vy        = 0.0
                    self.on_ground = True
                    break

        # ── Clamp horizontal ──────────────────────────────────────
        margin  = 20
        self.wx = max(float(margin), min(self.wx, float(world_w - self.W - margin)))

        # ── Transiciones de estado FSM ────────────────────────────
        self._run_fsm_transitions(player_wx, player_wy, fireballs, world_w)

        if self.attack_flash     > 0: self.attack_flash     -= 1
        if self.aggressive_timer > 0: self.aggressive_timer -= 1

        self._prev_player_wx = player_wx
        self._prev_player_wy = player_wy

    def _calc_vx(self, player_wx, player_wy, fireballs, world_w):
        """
        Calcula la velocidad horizontal deseada según el estado actual.
        No modifica self.wx — eso lo hace move_and_collide.
        """
        dist = self._cached_dist
        dx   = self._cached_dx
        spd_patrol = self.base_speed
        spd_chase  = self.base_speed * (2.2 if self.aggressive_timer > 0 else 1.7)
        spd_evade  = self.base_speed * 2.0
        spd_attack = self.base_speed * 0.5

        if self.state == "patrol":
            # Invertir en límites de patrulla
            if self.wx <= self.patrol_left:
                self.direction = 1
            elif self.wx >= self.patrol_right:
                self.direction = -1
            return spd_patrol * self.direction

        elif self.state == "chase":
            if dx != 0:
                self.direction = 1 if dx > 0 else -1
            if self.on_ground:
                dy = player_wy - self.wy
                if dy < -self.JUMP_WINDOW and abs(dx) < 250:
                    self._try_jump()
            return spd_chase * self.direction

        elif self.state == "attack":
            self._handle_burst(player_wx, player_wy, fireballs)
            if dist > self.ATTACK_RANGE * 0.6 and self.on_ground:
                return spd_attack * self.direction
            elif dist < self.EVADE_RANGE * 1.5 and self.on_ground:
                return -spd_attack * self.direction
            return 0.0

        elif self.state == "evade":
            if dx != 0:
                self.direction = -1 if dx > 0 else 1
            return spd_evade * self.direction

        return 0.0  # cooldown → quieto

    def _run_fsm_transitions(self, player_wx, player_wy, fireballs, world_w):
        """Gestiona transiciones de estado. El movimiento lo maneja _calc_vx."""
        dist = self._cached_dist

        if self.state == "patrol":
            if self._cached_can_see and dist < self.CHASE_RANGE:
                self.state = "chase"

        elif self.state == "chase":
            if dist < self.EVADE_RANGE:
                self.state = "evade"
            elif dist < self.ATTACK_RANGE and self.on_ground:
                self.state = "attack"
            elif not self._cached_can_see and dist > self.CHASE_RANGE + 80:
                self.state        = "patrol"
                self.patrol_left  = self.wx - random.randint(60, 160)
                self.patrol_right = self.wx + random.randint(60, 160)

        elif self.state == "attack":
            if dist < self.EVADE_RANGE:
                self.state = "evade"
            elif dist > self.ATTACK_RANGE + 80:
                self.state = "chase"

        elif self.state == "evade":
            if dist > self.EVADE_RANGE * 2.5:
                self.state = "chase"

        elif self.state == "cooldown":
            self.state_timer -= 1
            if self.state_timer <= 0:
                if self._cached_can_see and dist < self.CHASE_RANGE:
                    self.state = "chase"
                else:
                    self.state        = "patrol"
                    self.patrol_left  = self.wx - random.randint(60, 160)
                    self.patrol_right = self.wx + random.randint(60, 160)

    def _update_ai_cache(self, player_wx, player_wy):
        dx   = player_wx - self.wx
        dy   = player_wy - self.wy
        dist = math.hypot(dx, dy)
        self._cached_dx   = dx
        self._cached_dist = dist

        # Visión frontal: rango completo si el jugador está del lado que mira.
        # Visión trasera: reducida al 55% (puede "oír" al jugador cercano).
        # — Se eliminó el umbral del 40% que era demasiado restrictivo y
        #   hacía que los enemigos spawneados lejos nunca detectaran al jugador.
        in_front = (dx * self.direction) > 0
        if in_front:
            self._cached_can_see = dist < self.VISION_RANGE
        else:
            self._cached_can_see = dist < self.VISION_RANGE * 0.55

    def _handle_burst(self, player_wx, player_wy, fireballs):
        if self.burst_shots_left == 0:
            # Esperar cooldown entre ráfagas.
            # Se eliminó el requisito on_ground: el enemigo puede disparar
            # aunque esté en el aire (el bug era que on_ground = False al
            # entrar aquí en muchos frames, bloqueando el disparo para siempre).
            self.cooldown_timer -= 1
            if self.cooldown_timer <= 0:
                self.burst_shots_left = random.randint(self.BURST_SIZE_MIN,
                                                       self.BURST_SIZE_MAX)
                self.burst_timer = 0
                jitter = random.uniform(0.8, 1.2)
                self.cooldown_timer = int(self.BURST_COOLDOWN * jitter)
        else:
            self.burst_timer -= 1
            if self.burst_timer <= 0:
                self._shoot(player_wx, player_wy, fireballs)
                self.burst_shots_left -= 1
                self.burst_timer       = self.BURST_INTERVAL
                if self.burst_shots_left == 0:
                    self.state       = "cooldown"
                    self.state_timer = random.randint(30, 60)

    def _shoot(self, player_wx, player_wy, fireballs):
        cx = self.wx + self.W / 2
        cy = self.wy + self.H / 2
        pvx = player_wx - self._prev_player_wx
        pvy = player_wy - self._prev_player_wy
        dx   = player_wx - cx
        dy   = player_wy - cy
        dist = math.hypot(dx, dy) or 1
        t_flight = dist / max(FB_SPEED, 1)
        pred_wx = player_wx + pvx * t_flight * 0.55 + self.W / 2
        pred_wy = player_wy + pvy * t_flight * 0.55 + self.H / 2
        fireballs.append(Fireball(cx, cy, pred_wx, pred_wy))
        self.attack_flash = 22
        self.just_fired   = True

    def _try_jump(self):
        """Salta si está en el suelo. El enemigo salta ciegamente hacia arriba
        cuando persigue al jugador que está en una plataforma superior."""
        if self.on_ground:
            self.vy        = self.JUMP_SPEED
            self.on_ground = False

    def notify_stomped(self):
        self.aggressive_timer = 180

    def kill(self):
        self.alive     = False
        self.die_timer = 20

    def draw(self, surface, cam):
        if not self.alive:
            if self.die_timer > 0:
                t = self.die_timer / 20.0
                w = max(2, int(self.W * t))
                h = max(2, int(self.H * t))
                r = pygame.Rect(int(self.wx + self.W / 2 - w / 2),
                                int(self.wy + self.H - h), w, h)
                r.x = cam.apply(r.x)
                pygame.draw.rect(surface, (120, 20, 20), r, border_radius=4)
            return
        sx = cam.apply(int(self.wx))
        sy = int(self.wy)
        attacking = self.attack_flash > 0
        img     = self.img_attack if attacking else self.img_idle
        flipped = self.img_attack_fl if attacking else self.img_idle_fl
        frame   = flipped if self.direction < 0 else img
        if attacking:
            scaled = pygame.transform.scale(frame, (int(self.W * 1.1), int(self.H * 0.92)))
            surface.blit(scaled, (sx - 2, sy + 4))
        else:
            bob = int(math.sin(self.tick * 0.07) * 2)
            if self.aggressive_timer > 0:
                bob += random.randint(-1, 1)
            surface.blit(frame, (sx, sy + bob))
        if not os.path.exists("enemy_idle.png"):
            ey = sy + 10
            for ex in [sx + 10, sx + 32]:
                pygame.draw.rect(surface, C_EEYE, (ex, ey, 8, 8), border_radius=3)
        sw   = self.W - 8
        shad = pygame.Surface((sw, 7), pygame.SRCALPHA)
        pygame.draw.ellipse(shad, (0, 0, 0, 50), (0, 0, sw, 7))
        surface.blit(shad, (sx + 4, sy + self.H - 4))
        self._draw_state_indicator(surface, sx, sy)

    def _draw_state_indicator(self, surface, sx, sy):
        colors = {
            "patrol":   ( 70, 110,  70),
            "chase":    (220, 160,  20),
            "attack":   (220,  40,  20),
            "evade":    ( 60, 180, 220),
            "cooldown": ( 60,  60,  90),
        }
        col = colors.get(self.state, (80, 80, 120))
        if self.aggressive_timer > 0:
            col = (255, 80, 20)
        bw = self.W - 8
        pygame.draw.rect(surface, (20, 20, 30), (sx + 4, sy - 8, bw, 4), border_radius=2)
        pygame.draw.rect(surface, col,          (sx + 4, sy - 8, bw, 4), border_radius=2)

    def get_rect(self):
        return pygame.Rect(int(self.wx) + 6, int(self.wy) + 6,
                           self.W - 12, self.H - 6)

    @property
    def done(self):
        return not self.alive and self.die_timer <= 0


# ══════════════════════════════════════════════
#  PLAYER
# ══════════════════════════════════════════════
class Player:
    ANIM_SPEED = 8

    def __init__(self, wx, wy, img=None):
        h = PLAYER_H
        if img:
            self.img_r = img
        else:
            self.img_r = make_placeholder(int(h * 0.7), h, (80, 110, 160), "P")
        self.img_l = pygame.transform.flip(self.img_r, True, False)
        self.W     = self.img_r.get_width()
        self.H     = h
        self.wx  = float(wx)
        self.wy  = float(wy)
        self.vx  = 0.0
        self.vy  = 0.0
        self.on_ground    = False
        self.jumps_left   = 2
        self.jump_held    = False
        self.jump_hold_t  = 0
        self.facing_right = True
        self.hp      = PLAYER_MAX_HP
        self.iframes = 0
        self.dead    = False
        self.win     = False
        self.bob_tick = 0
        self.scale_y  = 1.0
        self.scale_x  = 1.0
        self.anim_state = "idle"
        self.anim_frame = 0
        self.anim_tick  = 0

    def handle_input(self, keys):
        self.vx = 0
        if keys[pygame.K_LEFT]  or keys[pygame.K_a]:
            self.vx = -MOVE_SPD
            self.facing_right = False
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.vx =  MOVE_SPD
            self.facing_right = True
        if (keys[pygame.K_SPACE] or keys[pygame.K_UP] or keys[pygame.K_w]):
            if self.jump_held and self.jump_hold_t > 0 and self.vy < 0:
                self.vy          -= JUMP_HOLD_BOOST
                self.jump_hold_t -= 1
        else:
            self.jump_held   = False
            self.jump_hold_t = 0

    def try_jump(self):
        if self.jumps_left > 0:
            self.vy          = JUMP_V if self.jumps_left == 2 else DJUMP_V
            self.jumps_left -= 1
            self.jump_held   = True
            self.jump_hold_t = JUMP_HOLD_MAX
            self.scale_y     = 1.35
            self.scale_x     = 0.72

    def update(self, solid_tiles, platforms, ground_y, world_w, flag_rect):
        """
        solid_tiles — pygame.Rect[] de tiles SOLID (paredes/suelo)
        platforms   — pygame.Rect[] de tiles PLATFORM (one-way, solo desde arriba)
        ground_y    — Y del suelo base del mundo (safety net absoluto)
        """
        if self.dead or self.win:
            return

        self.vy       += GRAVITY
        self.on_ground = False

        # Capturar vy ANTES de move_and_collide — la función puede
        # setear self.vy = 0 si aterriza en un tile sólido, y
        # necesitamos el valor original para las plataformas one-way.
        vy_before = self.vy

        # ── Colisión con tiles sólidos (X e Y separados) ──────────
        move_and_collide(self, self.vx, self.vy, solid_tiles)

        # ── Clamp horizontal dentro del mundo ─────────────────────
        self.wx = max(0.0, min(self.wx, float(world_w - self.W)))

        # ── Suelo base absoluto (safety net) ──────────────────────
        # ground_y es el TOP del suelo base, no su fila en la grid
        if self.wy + self.H >= ground_y:
            self.wy        = float(ground_y - self.H)
            self.vy        = 0.0
            self.on_ground = True

        # ── Plataformas one-way (solo aterrizaje desde arriba) ─────
        # Usa vy_before: si move_and_collide ya resolvió un tile sólido
        # (vy = 0), on_ground ya es True y no entramos aquí.
        if vy_before > 0 and not self.on_ground:
            foot_y      = self.wy + self.H
            prev_foot_y = foot_y - vy_before
            for p in platforms:
                foot_rect = pygame.Rect(int(self.wx) + 6, int(foot_y) - 6,
                                        self.W - 12, 8)
                if foot_rect.colliderect(p) and prev_foot_y <= p.top + 6:
                    self.wy        = float(p.top - self.H)
                    self.vy        = 0.0
                    self.on_ground = True
                    break

        if self.on_ground:
            self.jumps_left = 2
            self.jump_held  = False

        # ── Muerte por caída al vacío ──────────────────────────────
        if self.wy > ground_y + 300:
            self.hp   = 0
            self.dead = True

        if self.iframes > 0:
            self.iframes -= 1

        self.scale_y  += (1.0 - self.scale_y) * 0.18
        self.scale_x  += (1.0 - self.scale_x) * 0.18
        self.bob_tick += 1
        self._update_anim()

        if flag_rect and self.get_rect().colliderect(flag_rect):
            self.win = True

    def _update_anim(self):
        if not self.on_ground:
            self.anim_state = "jump" if self.vy < 0 else "fall"
        elif abs(self.vx) > 0.5:
            self.anim_state = "run"
        else:
            self.anim_state = "idle"
        self.anim_tick += 1
        if self.anim_tick >= self.ANIM_SPEED:
            self.anim_tick  = 0
            self.anim_frame += 1

    def take_damage(self, dmg):
        if self.iframes > 0:
            return
        self.hp      = max(0, self.hp - dmg)
        self.iframes = IFRAMES
        if self.hp <= 0:
            self.dead = True

    def draw(self, surface, cam):
        img   = self.img_r if self.facing_right else self.img_l
        w     = max(1, int(self.W * self.scale_x))
        h     = max(1, int(self.H * self.scale_y))
        frame = pygame.transform.scale(img, (w, h))
        if self.iframes > 0 and (self.iframes // 5) % 2 == 0:
            tint = pygame.Surface((w, h), pygame.SRCALPHA)
            tint.fill((255, 80, 80, 110))
            frame.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
        sx  = cam.apply(int(self.wx))
        sy  = int(self.wy)
        bob = int(math.sin(self.bob_tick * 0.1) * 2) if self.on_ground else 0
        shw  = max(20, w - 6)
        shad = pygame.Surface((shw, 8), pygame.SRCALPHA)
        pygame.draw.ellipse(shad, (0, 0, 0, 55), (0, 0, shw, 8))
        surface.blit(shad, (sx + (self.W - shw) // 2, int(self.wy + self.H) - 4))
        surface.blit(frame, (sx + (self.W - w) // 2, sy + (self.H - h) + bob))

    def get_rect(self):
        sh = 8
        return pygame.Rect(int(self.wx) + sh, int(self.wy) + sh,
                           self.W - sh * 2, self.H - sh)

    def get_stomp_rect(self):
        sh   = 12
        foot = 12
        return pygame.Rect(int(self.wx) + sh,
                           int(self.wy) + self.H - foot,
                           self.W - sh * 2, foot + 4)

    def center(self):
        return self.wx + self.W / 2, self.wy + self.H / 2


# ══════════════════════════════════════════════
#  DATOS DE NIVELES
# ══════════════════════════════════════════════
QUIZZES = [
    {
        "q":    "¿Qué significa 'PEPIS' en el contexto del juego?",
        "opts": [
            "Programa Educativo Para Ingenieros de Sistemas",
            "Personaje Épico Pixelado de Ingeniería de Sistemas",
            "Proyecto Estudiantil de Programación e Ingeniería",
            "Pepis no significa nada, es solo un nombre",
        ],
        "ans": 1,
        "tip": "Pepis es la mascota pixel-art de Ingeniería de Sistemas.",
    },
    {
        "q":    "¿Qué tecnología usa el juego El Pepis?",
        "opts": [
            "Unity + C#",
            "Godot + GDScript",
            "Python + Pygame",
            "JavaScript + Phaser",
        ],
        "ans": 2,
        "tip": "El juego está construido 100% en Python usando Pygame.",
    },
    {
        "q":    "¿Cuántos saltos puede hacer Pepis?",
        "opts": [
            "Solo 1 salto",
            "3 saltos (triple jump)",
            "2 saltos (doble salto)",
            "Salto infinito",
        ],
        "ans": 2,
        "tip": "Pepis tiene doble salto: el segundo es algo menos potente.",
    },
    {
        "q":    "¿Qué hace el jugador al saltar sobre un enemigo?",
        "opts": [
            "Nada, rebota",
            "Pierde HP",
            "Elimina al enemigo y rebota",
            "Teletransporta al inicio",
        ],
        "ans": 2,
        "tip": "Como en Mario: pisar enemigos los elimina y otorga puntos.",
    },
    {
        "q":    "¿Cuánto daño hace cada bola de fuego?",
        "opts": ["5 HP", "10 HP", "25 HP", "50 HP"],
        "ans": 1,
        "tip": "Cada proyectil quita 10 HP al jugador.",
    },
]

LEVEL_DEFS = [
    {"name": "Nivel 1", "enemy_count": 4,
     "colors": (C_SKY, C_SKY2, C_TILE, C_PLATFORM)},
    {"name": "Nivel 2", "enemy_count": 6,
     "colors": ((10,25,15),(20,50,30),(30,70,45),(50,100,70))},
    {"name": "Nivel 3", "enemy_count": 8,
     "colors": ((25,10,35),(50,20,70),(70,40,100),(90,60,130))},
    {"name": "Nivel 4", "enemy_count": 10,
     "colors": ((30,15,10),(65,30,20),(90,50,30),(120,75,45))},
    {"name": "Nivel 5", "enemy_count": 14,
     "colors": ((5,5,30),(10,10,60),(20,20,90),(40,40,120))},
]


# ══════════════════════════════════════════════
#  HEALTH PICKUP — batería pixel-art
# ══════════════════════════════════════════════
class HealthPickup:
    """
    Potenciador de vida en forma de batería pixel-art.
    Aparece encima de un tile sólido del mapa.
    Al colisionar con el jugador: +10 HP, desaparece, partículas verdes.
    """
    W, H   = 20, 30    # tamaño del sprite
    HP_ADD = 10

    def __init__(self, wx: float, wy: float):
        self.wx      = wx
        self.wy      = wy          # Y base (encima del tile)
        self.alive   = True
        self._tick   = random.randint(0, 62)   # desfase para que no bobeen sincronizadas
        self._surf   = self._build_surf()
        self._surf_glow = self._build_glow()

    # ── Sprite ────────────────────────────────────────────────────
    @staticmethod
    def _build_surf() -> pygame.Surface:
        """Dibuja una batería pixel-art de 20×30 px."""
        W, H = 20, 30
        s = pygame.Surface((W, H), pygame.SRCALPHA)

        # Terminal positivo (tope de la batería)
        terminal_col = (180, 255, 130)
        pygame.draw.rect(s, terminal_col, (7, 0, 6, 4))

        # Cuerpo exterior
        body_col     = (40,  60,  40)
        border_col   = (100, 220, 80)
        pygame.draw.rect(s, body_col,   (1, 4, W - 2, H - 4), border_radius=3)
        pygame.draw.rect(s, border_col, (1, 4, W - 2, H - 4), 2, border_radius=3)

        # Relleno interior verde (nivel de carga)
        fill_col = (80, 220, 90)
        pygame.draw.rect(s, fill_col, (4, 7, W - 8, H - 11), border_radius=2)

        # Líneas de "segmentos" de carga
        seg_col = (30, 50, 30)
        for yy in [13, 18, 23]:
            pygame.draw.line(s, seg_col, (4, yy), (W - 5, yy), 1)

        # Cruz "+10" en blanco pequeño
        cx, cy = W // 2, H // 2 + 2
        pygame.draw.rect(s, (220, 255, 220), (cx - 1, cy - 4, 2, 8))
        pygame.draw.rect(s, (220, 255, 220), (cx - 4, cy - 1, 8, 2))

        return s

    @staticmethod
    def _build_glow() -> pygame.Surface:
        """Halo verde semitransparente de 44×44 px."""
        size = 44
        g = pygame.Surface((size, size), pygame.SRCALPHA)
        for r in range(size // 2, 0, -1):
            alpha = int(55 * (1 - r / (size // 2)))
            pygame.draw.circle(g, (60, 220, 80, alpha), (size // 2, size // 2), r)
        return g

    # ── Colisión ──────────────────────────────────────────────────
    def get_rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.wx), int(self.wy), self.W, self.H)

    # ── Update ────────────────────────────────────────────────────
    def update(self, player, particles: ParticlePool, sounds) -> None:
        if not self.alive:
            return
        self._tick += 1
        # Colisión con el jugador
        if self.get_rect().colliderect(player.get_rect()):
            player.hp = min(PLAYER_MAX_HP, player.hp + self.HP_ADD)
            self.alive = False
            # Partículas verdes de recogida
            cx = self.wx + self.W / 2
            cy = self.wy + self.H / 2
            particles.spawn(cx, cy, (80, 220, 90),  12)
            particles.spawn(cx, cy, (180, 255, 130), 6)
            if sounds:
                sounds.play("correct")   # sonido de éxito existente

    # ── Draw ──────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface, cam) -> None:
        if not self.alive:
            return
        sx = cam.apply(int(self.wx))
        # Bob suave arriba-abajo
        bob = int(math.sin(self._tick * 0.07) * 4)
        sy  = int(self.wy) + bob

        # Glow pulsante
        pulse = 0.7 + 0.3 * math.sin(self._tick * 0.10)
        gw    = self._surf_glow.get_width()
        glow  = pygame.transform.scale(
            self._surf_glow,
            (int(gw * pulse), int(gw * pulse))
        )
        gx = sx + self.W // 2 - glow.get_width() // 2
        gy = sy + self.H // 2 - glow.get_height() // 2
        surface.blit(glow, (gx, gy))

        # Sprite de la batería
        surface.blit(self._surf, (sx, sy))


# ══════════════════════════════════════════════
#  LEVEL — integrado con TileMap
# ══════════════════════════════════════════════
class Level:
    def __init__(self, idx, img_idle=None, img_attack=None,
                 player_img=None, sounds=None):
        self.idx    = idx
        self.sounds = sounds
        defn = LEVEL_DEFS[idx]
        self.name = defn["name"]
        self.c_sky1, self.c_sky2, self.c_tile, self.c_plat = defn["colors"]
        self.quiz = QUIZZES[idx]

        # ── TileMap ───────────────────────────────────────────────
        base_dir = os.path.dirname(os.path.abspath(__file__))
        ts_path  = os.path.join(base_dir, "Tiles.png")
        self.tilemap   = make_tilemap(idx, ts_path)
        self.platforms = self.tilemap.get_platform_rects()   # one-way
        self.ground_y  = self.tilemap.ground_y
        self.world_w   = self.tilemap.world_w

        # ── Flag ─────────────────────────────────────────────────
        self.flag_x    = self.world_w - 150
        self.flag_rect = pygame.Rect(self.flag_x,
                                     self.ground_y - TILE * 5,
                                     TILE // 2, TILE * 5)

        # ── Jugador ───────────────────────────────────────────────
        self.player = Player(80, self.ground_y - PLAYER_H, player_img)

        # ── Enemigos con posicionamiento estratégico por nivel ────────
        self.total_enemies  = defn["enemy_count"]
        self.killed_enemies = 0

        # Posiciones X fijas por nivel (en píxeles).
        # Diseñadas para que cada enemigo esté en una zona de decisión.
        ENEMY_SPAWNS = {
            0: [600, 1150, 1900, 3700],                                   # Nivel 1: 4
            1: [400,  900, 1550, 2300, 3100, 4300],                       # Nivel 2: 6
            2: [350,  900, 1500, 2100, 2800, 3400, 4000, 4700],           # Nivel 3: 8
            3: [300,  750, 1200, 1800, 2400, 2900, 3500, 4100,4700,5500], # Nivel 4: 10
            4: [400,  800, 1200, 1700, 2200, 2700, 3200,                  # Nivel 5: 14
                3700, 4200, 4700, 5200, 5700, 6200, 6800],
        }
        spawn_xs = ENEMY_SPAWNS.get(idx, [])

        # Fallback: distribución uniforme si no hay spawns definidos
        if not spawn_xs:
            section = self.world_w // (self.total_enemies + 1)
            spawn_xs = [section * (i + 1) + random.randint(-40, 40)
                        for i in range(self.total_enemies)]

        self.enemies = []
        for i in range(self.total_enemies):
            ex = float(spawn_xs[i]) if i < len(spawn_xs) else float(
                self.world_w * (i + 1) // (self.total_enemies + 1))
            ex = max(200.0, min(ex, float(self.world_w - 200)))
            # Spawn encima del suelo base
            self.enemies.append(Enemy(ex, float(self.ground_y - ENEMY_H),
                                      img_idle, img_attack))

        # ── Resto ────────────────────────────────────────────────
        self.fireballs = []
        self.particles = ParticlePool(300)
        self.camera    = Camera(self.world_w)
        self.shake     = ScreenShake()
        self.timer     = 0
        self.show_enemies_warning = 0
        self.bg_surf   = self._build_bg()

        # ── Health pickups (baterías) ─────────────────────────────
        self.pickups: list[HealthPickup] = self._spawn_pickups(max_count=2)

    def _build_bg(self):
        surf = pygame.Surface((SW, SH))
        draw_grad_bg(surf, (0, 0, SW, self.ground_y), self.c_sky1, self.c_sky2)
        pygame.draw.rect(surf, C_GROUND, (0, self.ground_y, SW, SH - self.ground_y))
        pygame.draw.line(surf, C_GLINE,  (0, self.ground_y), (SW, self.ground_y), 3)
        return surf

    def _spawn_pickups(self, max_count: int = 2) -> list:
        """
        Coloca hasta max_count baterías encima de tiles sólidos del mapa.
        Estrategia:
          1. Obtiene todos los rects sólidos.
          2. Filtra los que tienen AIR justo encima (superficie libre).
          3. Divide el mundo en zonas y elige uno al azar por zona,
             evitando el inicio (<300px) y el final (>world_w-300px).
        """
        solid = self.tilemap.get_solid_rects()
        if not solid:
            return []

        # Conjunto de tops de tiles sólidos indexado por (col, row)
        # Para saber si hay espacio libre arriba usamos el tilemap directamente
        T   = TILE
        grid = self.tilemap.grid

        candidates: list[pygame.Rect] = []
        for tile in solid:
            col = tile.x // T
            row = tile.y // T
            # El tile de arriba debe ser AIR (fila anterior)
            if row > 0 and self.tilemap._get(row - 1, col) == 0:   # 0 = AIR
                # Excluir zona de spawn del jugador y zona de flag
                if 300 < tile.x < self.world_w - 300:
                    candidates.append(tile)

        if not candidates:
            return []

        pickups: list[HealthPickup] = []
        # Dividir en max_count zonas y elegir uno al azar por zona
        zone_w = (self.world_w - 600) // max_count
        for i in range(max_count):
            zone_start = 300 + i * zone_w
            zone_end   = zone_start + zone_w
            zone_tiles = [t for t in candidates
                          if zone_start <= t.x < zone_end]
            if not zone_tiles:
                # fallback: cualquier candidato
                zone_tiles = candidates
            tile = random.choice(zone_tiles)
            # Centrar la batería encima del tile
            px = tile.x + (T - HealthPickup.W) // 2
            py = tile.y - HealthPickup.H          # justo encima
            pickups.append(HealthPickup(float(px), float(py)))

        return pickups

    def update(self, keys):
        p   = self.player
        snd = self.sounds

        p_stomp_pre = p.get_stomp_rect()
        prev_bottom = p_stomp_pre.bottom

        p.handle_input(keys)

        # ── Tiles visibles por la cámara (para el jugador) ────────
        # Solo los tiles que la cámara ve + margen generoso.
        vis_solid = self.tilemap.get_visible_solid_rects(self.camera.x,
                                                         margin=200)
        vis_plat  = self.tilemap.get_visible_platform_rects(self.camera.x,
                                                            margin=200)

        # ── Jugador ───────────────────────────────────────────────
        p.update(vis_solid, vis_plat, self.ground_y, self.world_w, self.flag_rect)

        self.camera.follow(p.wx + p.W / 2)
        self.shake.update()
        self.timer += 1

        if self.show_enemies_warning > 0:
            self.show_enemies_warning -= 1

        # ── Enemigos — cada uno usa los tiles de SU posición ──────
        # Un enemigo fuera de pantalla todavía necesita colisionar
        # con los tiles a su alrededor, no con los de la cámara.
        for e in self.enemies:
            e_solid = self.tilemap.get_visible_solid_rects(e.wx - SW * 0.5,
                                                           margin=200)
            e_plat  = self.tilemap.get_visible_platform_rects(e.wx - SW * 0.5,
                                                              margin=200)
            e.update(e_solid, e_plat, self.ground_y,
                     p.wx, p.wy, self.fireballs, self.world_w)
            if e.just_fired and snd:
                snd.play("shoot")

        p_rect  = p.get_rect()
        p_stomp = p.get_stomp_rect()

        for e in self.enemies:
            if not e.alive:
                continue
            e_rect = e.get_rect()
            if not p_rect.colliderect(e_rect):
                continue
            e_head = pygame.Rect(e_rect.left + 4, e_rect.top,
                                 e_rect.width - 8, int(e_rect.height * 0.35))
            e_body = pygame.Rect(e_rect.left + 2,
                                 e_rect.top + int(e_rect.height * 0.2),
                                 e_rect.width - 4, int(e_rect.height * 0.8))
            is_falling     = p.vy > 0
            foot_hits_head = p_stomp.colliderect(e_head)
            was_above      = prev_bottom <= e_rect.top + 12
            center_inside  = e_rect.left < p_stomp.centerx < e_rect.right
            if is_falling and foot_hits_head and was_above and center_inside:
                e.kill()
                self.killed_enemies += 1
                p.vy         = -8.5
                p.jumps_left = 2
                p.scale_y    = 0.75
                p.scale_x    = 1.30
                self.particles.spawn(e.wx + e.W / 2, e.wy + e.H / 2, C_ENEMY, 16)
                self.particles.spawn(e.wx + e.W / 2, e.wy + e.H / 2, C_GOLD,   8)
                self.shake.add(0.3)
                if snd:
                    snd.play("stomp")
                continue
            if p_rect.colliderect(e_body):
                p.take_damage(HIT_DAMAGE)
                if p.iframes == IFRAMES:
                    self.particles.spawn(p.wx + p.W / 2, p.wy + p.H / 2, C_RED, 10)
                    p.wx += -12 if p.wx < e.wx else 12
                    if snd:
                        snd.play("hit")

        for fb in self.fireballs:
            fb.update(self.world_w)
            if fb.alive and fb.get_rect().colliderect(p.get_rect()):
                p.take_damage(HIT_DAMAGE)
                if p.iframes == IFRAMES:
                    fb.alive = False
                    self.particles.spawn(fb.wx, fb.wy, C_FIRE, 10)
                    if snd:
                        snd.play("hit")

        alive_count    = sum(1 for e in self.enemies if e.alive)
        self.enemies   = [e for e in self.enemies   if not e.done]
        self.fireballs = [f for f in self.fireballs if f.alive]
        self.particles.update()

        # ── Pickups (baterías) ────────────────────────────────────
        for pk in self.pickups:
            pk.update(p, self.particles, snd)
        self.pickups = [pk for pk in self.pickups if pk.alive]

        if p.dead:
            return "dead"
        if p.win:
            if alive_count > 0:
                p.win = False
                self.show_enemies_warning = 90
                return "playing"
            return "win"
        return "playing"

    def draw(self, surface):
        cam    = self.camera
        ox, oy = self.shake.offset()
        if ox != 0 or oy != 0:
            tmp = pygame.Surface((SW, SH))
            self._draw_scene(tmp, cam)
            surface.blit(tmp, (ox, oy))
        else:
            self._draw_scene(surface, cam)

    def _draw_scene(self, surface, cam):
        # 1. Fondo de gradiente
        surface.blit(self.bg_surf, (0, 0))

        # 2. TileMap — suelo y plataformas con sprites del tileset
        self.tilemap.draw(surface, cam.x, view_w=SW, view_h=SH)

        # 3. Flag
        fx = cam.apply(self.flag_x)
        if -50 < fx < SW + 50:
            ph = TILE * 5
            fy = self.ground_y - ph
            pygame.draw.rect(surface, C_FLAGP, (fx + 10, fy, 4, ph))
            pts = [(fx + 14, fy), (fx + 14, fy + 20), (fx + 36, fy + 10)]
            alive_now = sum(1 for e in self.enemies if e.alive)
            flag_col  = C_FLAG if alive_now == 0 else (90, 90, 90)
            pygame.draw.polygon(surface, flag_col, pts)
            pygame.draw.rect(surface, C_FLAGP,
                             (fx + 6, self.ground_y - 4, 12, 10), border_radius=3)
            if alive_now > 0:
                lf = pygame.font.SysFont("consolas", 14, bold=True)
                lt = lf.render("🔒", True, (200, 200, 100))
                surface.blit(lt, (fx + 2, fy - 20))

        # 4. Enemigos, partículas, fireballs, pickups, jugador
        for e in self.enemies:
            if cam.in_view(e.wx):
                e.draw(surface, cam)
        self.particles.draw(surface, cam.x)
        for fb in self.fireballs:
            if cam.in_view(fb.wx):
                fb.draw(surface, cam)
        for pk in self.pickups:
            if cam.in_view(pk.wx):
                pk.draw(surface, cam)
        self.player.draw(surface, cam)

        # 5. Aviso de enemigos pendientes
        if self.show_enemies_warning > 0:
            alive_n = sum(1 for e in self.enemies if e.alive)
            wf  = pygame.font.SysFont("consolas", 22, bold=True)
            msg = f"¡Elimina todos los enemigos!  ({alive_n} restantes)"
            tw  = wf.size(msg)[0]
            ws  = wf.render(msg, True, C_GOLD)
            bg  = pygame.Surface((tw + 20, 36), pygame.SRCALPHA)
            bg.fill((0, 0, 0, 140))
            surface.blit(bg, (SW // 2 - tw // 2 - 10, SH // 2 - 18))
            surface.blit(ws, (SW // 2 - tw // 2, SH // 2 - 11))


# ══════════════════════════════════════════════
#  HUD
# ══════════════════════════════════════════════
def _draw_skull(surface, cx, cy, size, filled):
    col = C_SKULL if filled else C_SKULL_D
    pygame.draw.circle(surface, col, (cx, cy), size)
    jaw_w = max(2, (size - 2) * 2)
    jaw_h = max(2, size - 1)
    jaw_x = cx - jaw_w // 2
    jaw_y = cy + size - 2
    pygame.draw.rect(surface, col, (jaw_x, jaw_y, jaw_w, jaw_h), border_radius=2)
    if filled and size >= 6:
        eye_r = max(1, size // 3)
        pygame.draw.circle(surface, (20, 20, 30), (cx - size // 3, cy - 1), eye_r)
        pygame.draw.circle(surface, (20, 20, 30), (cx + size // 3, cy - 1), eye_r)


def draw_enemy_hud(surface, killed, total, fonts):
    MARGIN_RIGHT  = 20
    MARGIN_TOP    = 20
    PAD_H         = 10
    PAD_V         = 6
    ROW_GAP       = 4
    SKULL_SIZE    = 7
    SKULL_SPACING = 18
    MAX_SKULLS_ROW = 14
    font_label   = fonts["tiny"]
    font_counter = fonts["med"]
    label_txt   = "ENEMIGOS"
    counter_txt = f"{killed} / {total}"
    label_w,   label_h   = font_label.size(label_txt)
    counter_w, counter_h = font_counter.size(counter_txt)
    text_row_h = max(label_h, counter_h)
    if total <= MAX_SKULLS_ROW:
        skulls_row_w = total * SKULL_SPACING
        skulls_row_h = (SKULL_SIZE + 3) * 2
    else:
        skulls_row_w = 0
        skulls_row_h = 0
    content_w = max(label_w + counter_w + 12, skulls_row_w)
    content_w = max(content_w, 110)
    panel_w = content_w + PAD_H * 2
    panel_h = PAD_V + text_row_h + ROW_GAP + skulls_row_h + PAD_V
    panel_x = surface.get_width() - panel_w - MARGIN_RIGHT
    panel_y = MARGIN_TOP
    panel_surf = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    panel_surf.fill((0, 0, 0, 145))
    pygame.draw.rect(panel_surf, C_ACC, (0, 0, panel_w, panel_h), 1, border_radius=7)
    surface.blit(panel_surf, (panel_x, panel_y))
    lbl_x = panel_x + PAD_H
    lbl_y = panel_y + PAD_V + (text_row_h - label_h) // 2
    shadow_text(surface, label_txt, font_label, C_ACC, lbl_x, lbl_y)
    cnt_x = panel_x + panel_w - PAD_H - counter_w
    cnt_y = panel_y + PAD_V + (text_row_h - counter_h) // 2
    alive = total - killed
    cnt_col = C_GREEN if alive == 0 else C_GOLD if alive <= 2 else C_TEXT
    shadow_text(surface, counter_txt, font_counter, cnt_col, cnt_x, cnt_y)
    if total <= MAX_SKULLS_ROW:
        skulls_y  = panel_y + PAD_V + text_row_h + ROW_GAP + SKULL_SIZE + 3
        total_skulls_w = total * SKULL_SPACING
        skulls_start_x = panel_x + PAD_H + (content_w - total_skulls_w) // 2 + SKULL_SIZE
        for i in range(total):
            cx = skulls_start_x + i * SKULL_SPACING
            _draw_skull(surface, cx, skulls_y, SKULL_SIZE, i < killed)


def draw_hud(surface, player, level, fonts, level_idx):
    bar_w, bar_h = 220, 20
    bx, by = 12, 12
    ratio  = player.hp / PLAYER_MAX_HP
    pygame.draw.rect(surface, C_HP_BG, (bx, by, bar_w, bar_h), border_radius=6)
    fg_col = C_HP_FG if ratio < 0.4 else C_HP_FG2 if ratio < 0.7 else C_GREEN
    pygame.draw.rect(surface, fg_col,
                     (bx, by, int(bar_w * ratio), bar_h), border_radius=6)
    pygame.draw.rect(surface, C_ACC, (bx, by, bar_w, bar_h), 2, border_radius=6)
    shadow_text(surface, f"HP {player.hp}", fonts["small"], C_TEXT, bx + 4, by + 2)
    secs = level.timer // FPS
    shadow_text(surface, level.name, fonts["med"], C_GOLD,
                SW // 2 - fonts["med"].size(level.name)[0] // 2, 10)
    timer_txt = f"{secs // 60:02d}:{secs % 60:02d}"
    timer_w   = fonts["small"].size(timer_txt)[0]
    shadow_text(surface, timer_txt, fonts["small"], C_ACC,
                SW - timer_w - 22, 6)
    for i in range(2):
        col = C_ACC if i < player.jumps_left else (40, 50, 80)
        pygame.draw.circle(surface, col, (bx + 8 + i * 20, by + 34), 7)
        pygame.draw.circle(surface, C_TEXT, (bx + 8 + i * 20, by + 34), 7, 1)
    draw_enemy_hud(surface, level.killed_enemies, level.total_enemies, fonts)


# ══════════════════════════════════════════════
#  PANTALLAS
# ══════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════
#  MENU SCREEN — Sistema Cyberpunk AAA
#  Arquitectura modular en clases. Instanciar una vez en Game.
#
#  Assets opcionales (carpeta raíz del juego):
#    bg_menu.png        — 1000×600 px, ciudad cyberpunk nocturna oscura
#    hud_menu.png       — 1000×600 px, overlay HUD sci-fi semitransparente
#    card_frame.png     — 220×280 px, marco HUD para cada tarjeta de nivel
#    pepis_card.png     — 160×200 px, sprite de Pepis para las tarjetas
#    logo_title.png     — 700×160 px, logo "ESCAPANDO CON PEPIS" en neón
#    icon_move.png      — 40×40 px, icono flecha para controles
#    icon_jump.png      — 40×40 px, icono salto para controles
#    icon_enemy.png     — 40×40 px, icono calavera para controles
# ══════════════════════════════════════════════════════════════════

class MenuScreen:
    """
    Pantalla de menú principal cyberpunk AAA.
    Instanciar una vez en Game.__init__ y llamar .draw() cada frame.
    """
    N_PARTICLES = 55
    CARD_W      = 172     # un poco más anchas
    CARD_H      = 295     # más altas para que Pepis respire
    CARD_GAP    = 14      # gap reducido para que quepan bien
    CARDS_Y     = 212     # más arriba

    # Paleta
    NEON  = (0,  230, 180)
    CYAN  = (0,  210, 255)
    MAG   = (220,  40, 180)
    GOLD  = (255, 210,  50)
    GREEN = ( 60, 255, 120)
    DIM   = (  3,   6,  14)
    PANEL = (  0,  14,  24)

    def __init__(self, sw: int, sh: int, base_dir: str):
        self.sw      = sw
        self.sh      = sh
        self.base    = base_dir
        self._t      = 0.0

        # Partículas
        self._parts  = [_Particle(sw, sh) for _ in range(self.N_PARTICLES)]

        # Capas estáticas pre-renderizadas
        self._bg_static  = self._make_bg()
        self._scanlines  = self._make_scanlines()
        self._grid_surf  = self._make_grid()

        # Assets externos
        self._bg_img     = self._load("bg_menu.png",    sw,  sh)
        self._hud_img    = self._load("hud_menu.png",   sw,  sh)
        self._card_frame = self._load("card_frame.png", self.CARD_W, self.CARD_H)
        self._pepis_card = self._load("pepis_card.png", 148, 190)  # más grande
        self._logo_img   = self._load("logo_title.png", 700, 160)
        self._icon_move  = self._load("icon_move.png",  36, 36)
        self._icon_jump  = self._load("icon_jump.png",  36, 36)
        self._icon_enemy = self._load("icon_enemy.png", 36, 36)

    # ── Asset loader ──────────────────────────────────────────────
    def _load(self, name, w, h):
        p = os.path.join(self.base, name)
        if not os.path.exists(p):
            return None
        try:
            img = pygame.image.load(p).convert_alpha()
            return pygame.transform.scale(img, (w, h))
        except Exception:
            return None

    # ── Capas estáticas ───────────────────────────────────────────
    def _make_bg(self):
        sw, sh = self.sw, self.sh
        s = pygame.Surface((sw, sh))
        for y in range(sh):
            t  = y / sh
            r  = int(3  + 6  * t)
            g  = int(5  + 8  * t)
            b  = int(14 + 20 * t)
            pygame.draw.line(s, (r, g, b), (0, y), (sw, y))
        # Bokeh fijo
        random.seed(99)
        for _ in range(60):
            bx  = random.randint(0, sw)
            by  = random.randint(0, sh)
            br  = random.randint(4, 22)
            col = random.choice([(0,50,70),(0,40,25),(55,0,55),(35,35,0),(0,30,60)])
            b_s = pygame.Surface((br*2, br*2), pygame.SRCALPHA)
            pygame.draw.circle(b_s, (*col, 80), (br, br), br)
            s.blit(b_s, (bx-br, by-br))
        random.seed()
        return s

    def _make_scanlines(self):
        s = pygame.Surface((self.sw, self.sh), pygame.SRCALPHA)
        for y in range(0, self.sh, 4):
            pygame.draw.line(s, (0, 0, 0, 40), (0, y), (self.sw, y))
        return s

    def _make_grid(self):
        s = pygame.Surface((self.sw, self.sh), pygame.SRCALPHA)
        for x in range(0, self.sw, 44):
            pygame.draw.line(s, (0, 40, 28, 30), (x, 0), (x, self.sh))
        for y in range(0, self.sh, 44):
            pygame.draw.line(s, (0, 40, 28, 30), (0, y), (self.sw, y))
        return s

    # ── Helpers ───────────────────────────────────────────────────
    @staticmethod
    def _glow(surf, text, font, col, x, y, r=6):
        gc = (col[0]//3, col[1]//3, col[2]//3)
        for dx, dy in [(-r,0),(r,0),(0,-r),(0,r),(-r,-r),(r,-r),(-r,r),(r,r)]:
            surf.blit(font.render(text, True, gc), (x+dx, y+dy))
        surf.blit(font.render(text, True, col), (x, y))

    @staticmethod
    def _hex_corner(surf, x, y, size, col, fx=False, fy=False):
        pts = [(0, size), (0, 0), (size, 0)]
        if fx: pts = [(size-p[0], p[1]) for p in pts]
        if fy: pts = [(p[0], size-p[1]) for p in pts]
        pygame.draw.lines(surf, col, False,
                          [(x+p[0], y+p[1]) for p in pts], 2)

    # ── Capas de dibujo ───────────────────────────────────────────
    def _layer_bg(self, surf):
        surf.blit(self._bg_static, (0, 0))
        if self._bg_img:
            dark = self._bg_img.copy()
            mask = pygame.Surface(dark.get_size(), pygame.SRCALPHA)
            mask.fill((0, 0, 0, 100))
            dark.blit(mask, (0, 0))
            surf.blit(dark, (0, 0))
        surf.blit(self._grid_surf, (0, 0))

    def _layer_particles(self, surf):
        for p in self._parts:
            p.update(self.sw, self.sh)
            p.draw(surf)

    def _layer_overlay(self, surf):
        if self._hud_img:
            surf.blit(self._hud_img, (0, 0))
        surf.blit(self._scanlines, (0, 0))

        # Barra superior
        tb = pygame.Surface((self.sw, 30), pygame.SRCALPHA)
        tb.fill((0, 18, 30, 210))
        pygame.draw.line(tb, self.CYAN, (0, 29), (self.sw, 29), 2)
        surf.blit(tb, (0, 0))

        # Barra inferior
        bb = pygame.Surface((self.sw, 32), pygame.SRCALPHA)
        bb.fill((0, 18, 30, 210))
        pygame.draw.line(bb, self.CYAN, (0, 0), (self.sw, 0), 2)
        surf.blit(bb, (0, self.sh - 32))

    def _layer_title(self, surf, fonts):
        if self._logo_img:
            lw, lh = self._logo_img.get_size()
            surf.blit(self._logo_img, (self.sw//2 - lw//2, 22))
        else:
            # Título construido: dos líneas como la referencia
            f_big  = fonts["big"]
            f_med  = fonts["med"]
            sub_txt = "ESCAPANDO CON"
            main_txt = "PEPIS"
            pulse = abs(math.sin(self._t * 1.8))

            sw_ = f_med.size(sub_txt)[0]
            self._glow(surf, sub_txt, f_med,
                       (int(80+175*pulse), 255, int(80+80*pulse)),
                       self.sw//2 - sw_//2, 30, r=5)

            f_huge = pygame.font.SysFont("consolas", 88, bold=True)
            mw     = f_huge.size(main_txt)[0]
            col_m  = (int(0+50*pulse), int(200+55*pulse), int(220+35*pulse))
            self._glow(surf, main_txt, f_huge, col_m,
                       self.sw//2 - mw//2, 68, r=10)

        # Subtítulo "GRUPO X PEPIS"
        sub2  = "GRUPO 1 PEPIS"
        f_sm  = fonts["small"]
        sw2   = f_sm.size(sub2)[0]
        lpad  = 30
        ly    = 192     # justo encima de las tarjetas con margen
        mx    = self.sw//2 - sw2//2
        pygame.draw.line(surf, (*self.CYAN, 120),
                         (mx - lpad - 80, ly+10), (mx - lpad, ly+10), 1)
        pygame.draw.line(surf, (*self.CYAN, 120),
                         (mx + sw2 + lpad, ly+10),
                         (mx + sw2 + lpad + 80, ly+10), 1)
        self._glow(surf, sub2, f_sm, self.CYAN, mx, ly, r=3)

    def _layer_cards(self, surf, fonts, unlocked, level_stars):
        """5 tarjetas de nivel estilo cyberpunk con Pepis, barra de progreso."""
        CW  = self.CARD_W
        CH  = self.CARD_H
        gap = self.CARD_GAP
        total_w = CW * 5 + gap * 4
        start_x = self.sw // 2 - total_w // 2
        cy      = self.CARDS_Y
        rects   = []

        f_sm   = fonts["small"]
        f_tiny = pygame.font.SysFont("consolas", 13, bold=True)
        f_pct  = pygame.font.SysFont("consolas", 16, bold=True)

        for i in range(5):
            cx      = start_x + i * (CW + gap)
            locked  = i > unlocked
            is_next = i == unlocked and not locked
            stars   = level_stars[i] if i < len(level_stars) else 0
            pct     = int(stars / 3 * 100)

            # ── Fondo de la tarjeta ───────────────────────────────
            card_s = pygame.Surface((CW, CH), pygame.SRCALPHA)
            card_s.fill((0, 12, 20, 220))
            surf.blit(card_s, (cx, cy))

            # ── Marco: frame externo si existe, si no líneas ──────
            if self._card_frame:
                # colorkey negro
                cf = self._card_frame.copy().convert_alpha()
                arr3 = pygame.surfarray.pixels3d(cf)
                arra = pygame.surfarray.pixels_alpha(cf)
                dark = (arr3[:,:,0].astype(int) +
                        arr3[:,:,1].astype(int) +
                        arr3[:,:,2].astype(int)) < 55
                arra[dark] = 0
                del arr3, arra
                surf.blit(cf, (cx, cy))
            else:
                # Marco dibujado
                if locked:
                    bcol = (40, 50, 80)
                elif is_next:
                    pa   = int(180 + 75*abs(math.sin(self._t*2.5)))
                    bcol = (0, pa, int(pa*0.5))
                else:
                    bcol = self.CYAN
                pygame.draw.rect(surf, bcol, (cx, cy, CW, CH), 2, border_radius=6)
                pygame.draw.rect(surf, (*bcol, 40),
                                 (cx+3, cy+3, CW-6, CH-6), 1, border_radius=5)
                # Esquinas hex
                csz = 14
                for fx, fy, ox_, oy_ in [(False,False,cx,cy),(True,False,cx+CW-csz,cy),
                                          (False,True,cx,cy+CH-csz),(True,True,cx+CW-csz,cy+CH-csz)]:
                    self._hex_corner(surf, ox_, oy_, csz, bcol, fx, fy)

            # ── Título del nivel ──────────────────────────────────
            lbl   = f"NIVEL {i+1}"
            tcol  = (80, 90, 120) if locked else self.GREEN
            tw_   = f_tiny.size(lbl)[0]
            self._glow(surf, lbl, f_tiny, tcol,
                       cx + CW//2 - tw_//2, cy + 10, r=3)

            # ── Sprite Pepis ──────────────────────────────────────
            if self._pepis_card:
                pw_, ph_ = self._pepis_card.get_size()
                bob      = int(math.sin(self._t * 1.8 + i * 0.7) * 4)
                # Glow plataforma holográfica bajo los pies
                pg_s = pygame.Surface((pw_ + 24, 18), pygame.SRCALPHA)
                pg_a = int(55 + 35*abs(math.sin(self._t*1.2+i)))
                pygame.draw.ellipse(pg_s, (*self.CYAN, pg_a),
                                    (0, 0, pw_+24, 18))
                # Centro del sprite en la tarjeta, con espacio arriba para el título
                sprite_top = cy + 36
                surf.blit(pg_s, (cx + CW//2 - (pw_+24)//2,
                                 sprite_top + ph_ - 4))
                if locked:
                    dim_s = self._pepis_card.copy()
                    dim_s.set_alpha(60)
                    surf.blit(dim_s, (cx + CW//2 - pw_//2, sprite_top + bob))
                else:
                    surf.blit(self._pepis_card,
                              (cx + CW//2 - pw_//2, sprite_top + bob))
            else:
                # Placeholder Pepis más grande
                ph_w, ph_h = 110, 150
                bob        = int(math.sin(self._t * 1.8 + i * 0.7) * 4)
                sprite_top = cy + 36
                ph_col     = (30, 50, 40) if locked else (40, 80, 60)
                ph_s       = make_placeholder(ph_w, ph_h, ph_col, "P")
                if locked: ph_s.set_alpha(60)
                surf.blit(ph_s, (cx + CW//2 - ph_w//2, sprite_top + bob))

            # ── Barra de progreso (anclada al fondo de la tarjeta) ──
            bar_y  = cy + CH - 52
            bar_x  = cx + 14
            bar_w  = CW - 28
            bar_h  = 11
            filled = int(bar_w * pct / 100)

            # Fondo barra
            pygame.draw.rect(surf, (10, 25, 18),
                             (bar_x, bar_y, bar_w, bar_h), border_radius=5)
            pygame.draw.rect(surf, (20, 50, 35),
                             (bar_x, bar_y, bar_w, bar_h), 1, border_radius=5)

            if not locked and filled > 0:
                bar_col = self.GREEN if pct >= 100 else self.GOLD
                pygame.draw.rect(surf, bar_col,
                                 (bar_x, bar_y, filled, bar_h), border_radius=5)
                shine = pygame.Surface((10, bar_h), pygame.SRCALPHA)
                shine.fill((*bar_col, 110))
                surf.blit(shine, (bar_x + filled - 10, bar_y))

            # Porcentaje debajo de la barra
            pct_str = f"{pct}%" if not locked else "—"
            pct_col = (60, 70, 90) if locked else (self.GREEN if pct>=100 else self.GOLD)
            f_pct2  = pygame.font.SysFont("consolas", 15, bold=True)
            pw_txt  = f_pct2.size(pct_str)[0]
            self._glow(surf, pct_str, f_pct2, pct_col,
                       cx + CW//2 - pw_txt//2, bar_y + 14, r=3)

            # Candado si está bloqueado
            if locked:
                f_lock = pygame.font.SysFont("consolas", 28)
                lt     = f_lock.render("🔒", True, (60, 70, 100))
                surf.blit(lt, (cx + CW//2 - lt.get_width()//2,
                               cy + CH//2 - lt.get_height()//2))

            # Pulso verde en la siguiente tarjeta disponible
            if is_next and not self._card_frame:
                pa2  = int(180 + 75*abs(math.sin(self._t*2.5)))
                pygame.draw.rect(surf, (0, pa2, int(pa2*0.5)),
                                 (cx, cy, CW, CH), 3, border_radius=6)

            rects.append((cx, cy, CW, CH))

        return rects

    def _layer_buttons(self, surf, fonts):
        """Barra inferior de controles estilo HUD."""
        BY  = self.sh - 28
        f_t = pygame.font.SysFont("consolas", 13, bold=True)

        # Botón guía central
        guide_txt = "CLIC EN NIVEL  |  ESC PARA SALIR"
        btn_w, btn_h = 420, 28
        btn_x = self.sw//2 - btn_w//2
        btn_s = pygame.Surface((btn_w, btn_h), pygame.SRCALPHA)
        btn_s.fill((0, 18, 28, 200))
        pa  = int(160 + 95*abs(math.sin(self._t*1.5)))
        pygame.draw.rect(btn_s, (*self.CYAN, pa), (0, 0, btn_w, btn_h), 1, border_radius=4)
        surf.blit(btn_s, (btn_x, self.sh - 70))
        gw_ = f_t.size(guide_txt)[0]
        self._glow(surf, guide_txt, f_t, self.CYAN,
                   self.sw//2 - gw_//2, self.sh - 65, r=2)

        # Controles
        ctrl_items = [
            (self._icon_move,  "← →",     "MOVERSE"),
            (self._icon_jump,  "ESPACIO",  "SALTAR (MANTENER=MÁS ALTO)"),
            (self._icon_enemy, "☠",        "PISA ENEMIGOS"),
        ]
        total_ctrl_w = 700
        cx_  = self.sw//2 - total_ctrl_w//2
        cy_  = self.sh - 28

        for icon, key_txt, act_txt in ctrl_items:
            # Marco tecla
            kw   = f_t.size(key_txt)[0] + 16
            km_s = pygame.Surface((kw, 20), pygame.SRCALPHA)
            km_s.fill((0, 18, 28, 180))
            pygame.draw.rect(km_s, (*self.CYAN, 180), (0, 0, kw, 20), 1, border_radius=3)
            surf.blit(km_s, (cx_, cy_ - 16))
            kw2 = f_t.size(key_txt)[0]
            self._glow(surf, key_txt, f_t, self.CYAN, cx_ + (kw-kw2)//2, cy_ - 14, r=2)
            cx_ += kw + 6

            # Texto acción
            aw_ = f_t.size(act_txt)[0]
            shadow_text(surf, act_txt, f_t, self._CY_WHITE_DIM,
                        cx_, cy_ - 14)
            cx_ += aw_ + 22

    _CY_WHITE_DIM = (160, 200, 190)

    # ── Entry point ───────────────────────────────────────────────
    def draw(self, surface: pygame.Surface, fonts: dict,
             unlocked: int, level_stars: list) -> list:
        """
        Dibuja la pantalla de menú. Devuelve lista de rects clickeables
        en el mismo formato que antes: [(x, y, w, h), ...] × 5
        """
        self._t = pygame.time.get_ticks() / 1000.0

        self._layer_bg(surface)
        self._layer_particles(surface)
        self._layer_overlay(surface)
        self._layer_title(surface, fonts)
        rects = self._layer_cards(surface, fonts, unlocked, level_stars)
        self._layer_buttons(surface, fonts)

        return rects


def screen_menu(surface, fonts, unlocked, level_stars):
    """
    Stub de compatibilidad. En Game se usa MenuScreen.draw() directamente.
    Esta función no se llama — el game loop llama a self.menu_screen.draw().
    """
    return []


def draw_star_simple(surface, cx, cy, size, filled):
    col = C_GOLD if filled else (55, 60, 95)
    pts = []
    for i in range(10):
        angle = math.pi / 2 + i * 2 * math.pi / 10
        r = size if i % 2 == 0 else size * 0.45
        pts.append((cx + r * math.cos(angle), cy - r * math.sin(angle)))
    pygame.draw.polygon(surface, col, pts)
    pygame.draw.polygon(surface, (0, 0, 0), pts, 1)


def wrap_text(text, font, max_width):
    words = text.split()
    lines, line = [], ""
    for w in words:
        test = (line + " " + w).strip()
        if font.size(test)[0] <= max_width:
            line = test
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines


def screen_quiz(surface, fonts, quiz, answered, correct, stars_earned):
    draw_grad_bg(surface, (0, 0, SW, SH), (5, 10, 30), (15, 25, 55))
    shadow_text(surface, "¡NIVEL COMPLETADO!", fonts["big"], C_GOLD,
                SW // 2 - fonts["big"].size("¡NIVEL COMPLETADO!")[0] // 2, 30)
    for i in range(3):
        draw_star_simple(surface, SW // 2 - 60 + i * 60, 100, 22, i < stars_earned)
    q_lines = wrap_text(quiz["q"], fonts["small"], SW - 80)
    q_y     = 145
    for ln in q_lines:
        shadow_text(surface, ln, fonts["small"], C_TEXT,
                    SW // 2 - fonts["small"].size(ln)[0] // 2, q_y)
        q_y += fonts["small"].get_height() + 4
    q_y += 8
    opt_rects = []
    for i, opt in enumerate(quiz["opts"]):
        oy = q_y + i * 68
        ox = SW // 2 - 340
        ow, oh = 680, 52
        col_bg = (25, 30, 60)
        col_bd = (60, 70, 110)
        if answered >= 0:
            if i == quiz["ans"]:
                col_bg, col_bd = (10, 50, 20), (50, 200, 80)
            elif i == answered and i != quiz["ans"]:
                col_bg, col_bd = (50, 10, 10), (200, 50, 50)
        pygame.draw.rect(surface, col_bg, (ox, oy, ow, oh), border_radius=8)
        pygame.draw.rect(surface, col_bd, (ox, oy, ow, oh), 2, border_radius=8)
        txt = chr(65 + i) + ") " + opt
        shadow_text(surface, txt, fonts["small"], C_TEXT,
                    ox + 16, oy + oh // 2 - fonts["small"].get_height() // 2)
        opt_rects.append(pygame.Rect(ox, oy, ow, oh))
    if answered >= 0 and correct is not None:
        msg = "¡Correcto! +3 estrellas" if correct else f"Incorrecto. {quiz['tip']}"
        col = C_GREEN if correct else C_RED
        shadow_text(surface, msg[:80], fonts["small"], col,
                    SW // 2 - fonts["small"].size(msg[:80])[0] // 2,
                    q_y + 4 * 68 + 5)
        shadow_text(surface, "[ ENTER ] Continuar", fonts["small"], C_ACC,
                    SW // 2 - fonts["small"].size("[ ENTER ] Continuar")[0] // 2,
                    q_y + 4 * 68 + 38)
    return opt_rects


def screen_gameover(surface, fonts):
    draw_grad_bg(surface, (0, 0, SW, SH), (20, 5, 5), (50, 10, 10))
    shadow_text(surface, "GAME OVER", fonts["big"], C_RED,
                SW // 2 - fonts["big"].size("GAME OVER")[0] // 2, 220)
    msg = "[ R ] Reintentar   [ ESC ] Menú"
    shadow_text(surface, msg, fonts["small"], C_ACC,
                SW // 2 - fonts["small"].size(msg)[0] // 2, 340)


# ══════════════════════════════════════════════
#  SISTEMA DE GUARDADO
# ══════════════════════════════════════════════
class SaveSystem:
    STATS_FILE = "pepis_stats.json"   # archivo independiente para tiempos

    def __init__(self, base_dir):
        self.path       = os.path.join(base_dir, SAVE_FILE)
        self.stats_path = os.path.join(base_dir, self.STATS_FILE)

    # ── Progreso (unlock + estrellas) ─────────────────────────────
    def save(self, unlocked, level_stars):
        data = {"unlocked": unlocked, "stars": level_stars}
        try:
            with open(self.path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[SAVE] Error guardando: {e}")

    def load(self):
        if not os.path.exists(self.path):
            return 0, [0, 0, 0, 0, 0]
        try:
            with open(self.path) as f:
                data = json.load(f)
            return data.get("unlocked", 0), data.get("stars", [0, 0, 0, 0, 0])
        except Exception as e:
            print(f"[SAVE] Error cargando: {e}")
            return 0, [0, 0, 0, 0, 0]

    # ── Tiempos por nivel ──────────────────────────────────────────
    def save_times(self, level_times: list[int]) -> None:
        """
        Guarda la lista de tiempos (segundos) de cada nivel completado.
        Genera también el total acumulado.

        Formato JSON:
        {
          "nivel_1": 35,
          "nivel_2": 42,
          ...
          "total": 128,
          "niveles_completados": 3
        }
        """
        data: dict = {}
        for i, t in enumerate(level_times):
            if t > 0:
                data[f"nivel_{i + 1}"] = t
        data["total"]               = sum(level_times)
        data["niveles_completados"] = sum(1 for t in level_times if t > 0)
        try:
            with open(self.stats_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[SAVE] Error guardando tiempos: {e}")

    def load_times(self) -> list[int]:
        """Carga los tiempos guardados. Devuelve lista de 5 enteros."""
        times = [0] * 5
        if not os.path.exists(self.stats_path):
            return times
        try:
            with open(self.stats_path) as f:
                data = json.load(f)
            for i in range(5):
                times[i] = int(data.get(f"nivel_{i + 1}", 0))
        except Exception as e:
            print(f"[SAVE] Error cargando tiempos: {e}")
        return times


# ══════════════════════════════════════════════
#  PANTALLA VICTORIA FINAL
# ══════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════
#  VICTORY SCREEN — Sistema Cyberpunk AAA
#  Arquitectura modular en clases para expansión y mantenimiento.
#
#  Assets opcionales (carpeta raíz del juego):
#    pepis_final.png   — personaje grande izquierda (ver guía abajo)
#    heart.png         — icono por nivel en panel de tiempos
#    bg_city.png       — ciudad cyberpunk de fondo
#    hud_overlay.png   — overlay HUD sci-fi semitransparente
#    scanline.png      — textura de scanlines (tile vertical)
#    panel_frame.png   — marco del panel de tiempos
#    glow_circle.png   — halo de luz para el personaje
#
#  GUÍA DE ASSETS:
#    pepis_final.png  → 300×500 px, PNG transparente, personaje de frente
#    heart.png        → 32×32 px, PNG transparente, corazón neón
#    bg_city.png      → 1000×600 px, ciudad cyberpunk nocturna oscura
#    hud_overlay.png  → 1000×600 px, PNG semitransparente, HUD sci-fi
#    scanline.png     → 1000×4 px, franja negra 50% alpha (se tilea)
#    panel_frame.png  → 660×420 px, PNG con marco holográfico cyan
#    glow_circle.png  → 400×400 px, círculo de luz verde/cyan difuso
# ══════════════════════════════════════════════════════════════════

# ── Paleta cyberpunk ───────────────────────────────────────────────
_CY_NEON   = (0,  255, 180)     # verde-cyan principal
_CY_CYAN   = (0,  220, 255)     # cyan puro acento
_CY_MAG    = (220,  40, 180)    # magenta neón
_CY_GOLD   = (255, 210,  50)    # dorado
_CY_WHITE  = (200, 240, 255)    # blanco frío
_CY_DIM    = (  4,   8,  16)    # fondo oscuro azul-negro
_CY_PANEL  = (  0,  18,  30)    # fondo panel
_CY_GREEN  = ( 60, 255, 120)    # verde brillante


class _Particle:
    """Partícula flotante simple para el fondo de la pantalla de victoria."""
    __slots__ = ("x", "y", "vx", "vy", "size", "alpha", "col", "life", "max_life")

    def __init__(self, sw, sh):
        self.reset(sw, sh)

    def reset(self, sw, sh):
        self.x       = random.uniform(0, sw)
        self.y       = random.uniform(0, sh)
        self.vx      = random.uniform(-0.3, 0.3)
        self.vy      = random.uniform(-0.6, -0.1)
        self.size    = random.randint(1, 3)
        self.max_life = random.randint(120, 300)
        self.life    = self.max_life
        col_choices  = [_CY_NEON, _CY_CYAN, _CY_MAG, (255, 255, 180)]
        self.col     = random.choice(col_choices)

    def update(self, sw, sh):
        self.x    += self.vx
        self.y    += self.vy
        self.life -= 1
        if self.life <= 0 or self.y < -10:
            self.reset(sw, sh)
            self.y = sh + 5

    def draw(self, surf):
        a = int(200 * (self.life / self.max_life))
        s = pygame.Surface((self.size * 2, self.size * 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*self.col, a), (self.size, self.size), self.size)
        surf.blit(s, (int(self.x) - self.size, int(self.y) - self.size))


class VictoryScreen:
    """
    Pantalla de victoria cyberpunk AAA.
    Instanciada una sola vez en Game y reutilizada cada frame.
    Uso:
        self.victory_screen = VictoryScreen(SW, SH, base_dir)
        # en el loop:
        self.victory_screen.draw(surface, fonts, level_times,
                                  pepis_img, icon_img)
    """
    N_PARTICLES = 60

    def __init__(self, sw: int, sh: int, base_dir: str):
        self.sw      = sw
        self.sh      = sh
        self.base    = base_dir
        self._t      = 0.0

        # Partículas flotantes
        self._particles = [_Particle(sw, sh) for _ in range(self.N_PARTICLES)]

        # Superficies pre-renderizadas que no cambian cada frame
        self._bg_layer    = self._make_bg_layer()
        self._scanlines   = self._make_scanlines()
        self._panel_cache: pygame.Surface | None = None   # regenerada si cambia tamaño

        # Assets externos (cargados si existen)
        self._bg_img      = self._load("bg_city.png",    sw,  sh)
        self._hud_img     = self._load("hud_overlay.png", sw, sh)
        self._glow_img    = self._load("glow_circle.png", 380, 380)
        self._frame_img   = self._load("panel_frame.png", 660, 420)

    # ── Carga de assets externos ──────────────────────────────────
    def _load(self, name: str, w: int, h: int) -> pygame.Surface | None:
        path = os.path.join(self.base, name)
        if not os.path.exists(path):
            return None
        try:
            img = pygame.image.load(path).convert_alpha()
            return pygame.transform.scale(img, (w, h))
        except Exception:
            return None

    # ── Capas estáticas ───────────────────────────────────────────
    def _make_bg_layer(self) -> pygame.Surface:
        """Fondo degradado oscuro azul-negro + puntos de luz bokeh."""
        sw, sh = self.sw, self.sh
        s = pygame.Surface((sw, sh))
        # Degradado vertical
        for y in range(sh):
            t  = y / sh
            r  = int(4  + 8  * t)
            g  = int(6  + 10 * t)
            b  = int(16 + 22 * t)
            pygame.draw.line(s, (r, g, b), (0, y), (sw, y))
        # Bokeh: puntos de luz de colores difusos en el fondo
        random.seed(42)   # seed fijo para que sean siempre los mismos
        for _ in range(55):
            bx  = random.randint(0, sw)
            by  = random.randint(0, sh)
            br  = random.randint(6, 28)
            col = random.choice([
                (0, 60, 80), (0, 50, 30), (60, 0, 60), (40, 40, 0)])
            b_s = pygame.Surface((br * 2, br * 2), pygame.SRCALPHA)
            pygame.draw.circle(b_s, (*col, 90), (br, br), br)
            s.blit(b_s, (bx - br, by - br))
        random.seed()   # restaurar aleatoriedad
        return s

    def _make_scanlines(self) -> pygame.Surface:
        """Overlay de scanlines horizontales semitransparentes."""
        sw, sh = self.sw, self.sh
        s = pygame.Surface((sw, sh), pygame.SRCALPHA)
        for y in range(0, sh, 4):
            pygame.draw.line(s, (0, 0, 0, 45), (0, y), (sw, y))
        return s

    # ── Helpers de dibujo ─────────────────────────────────────────
    @staticmethod
    def _glow_text(surf, text, font, col, x, y, radius=6, steps=6):
        """Texto con halo de glow usando múltiples blits desplazados."""
        glow_col = (min(255, col[0] // 2),
                    min(255, col[1] // 2),
                    min(255, col[2] // 2))
        for i in range(steps, 0, -1):
            r = radius * i // steps
            for dx, dy in [(-r,0),(r,0),(0,-r),(0,r),
                           (-r,-r),(r,-r),(-r,r),(r,r)]:
                surf.blit(font.render(text, True, glow_col), (x + dx, y + dy))
        surf.blit(font.render(text, True, col), (x, y))

    @staticmethod
    def _draw_hex_corner(surf, x, y, size, col, flip_x=False, flip_y=False):
        """Esquina tipo hexágono/bracket para decorar bordes de panel."""
        pts = [(0, size), (0, 0), (size, 0)]
        if flip_x:
            pts = [(size - p[0], p[1]) for p in pts]
        if flip_y:
            pts = [(p[0], size - p[1]) for p in pts]
        shifted = [(x + p[0], y + p[1]) for p in pts]
        pygame.draw.lines(surf, col, False, shifted, 2)

    @staticmethod
    def _draw_heart(surf, cx, cy, size=12):
        """Corazón neón magenta/rojo pixel-art."""
        c1 = (220, 40, 100)
        c2 = (255, 130, 160)
        r  = size // 2
        pygame.draw.circle(surf, c1, (cx - r + 1, cy - r + 3), r)
        pygame.draw.circle(surf, c1, (cx + r - 1, cy - r + 3), r)
        pts = [(cx - size + 2, cy - r + 5),
               (cx,            cy + size - 3),
               (cx + size - 2, cy - r + 5)]
        pygame.draw.polygon(surf, c1, pts)
        pygame.draw.circle(surf, c2, (cx - r + 2, cy - r + 2), max(1, r // 3))

    def _draw_hud_line(self, surf, x1, y1, x2, y2, col, animated=True):
        """Línea HUD con pulso de opacidad."""
        if animated:
            a   = int(160 + 95 * abs(math.sin(self._t * 1.2)))
            tmp = pygame.Surface((abs(x2 - x1) + 2, abs(y2 - y1) + 2), pygame.SRCALPHA)
            pygame.draw.line(tmp, (*col, a),
                             (0, 0) if x1 <= x2 else (abs(x2-x1), 0),
                             (abs(x2-x1), 0) if y1 == y2 else (0, abs(y2-y1)), 2)
            surf.blit(tmp, (min(x1,x2), min(y1,y2)))
        else:
            pygame.draw.line(surf, col, (x1, y1), (x2, y2), 2)

    # ── Capas de la pantalla ──────────────────────────────────────
    def _draw_background(self, surf):
        """Capa 1: fondo + imagen de ciudad si existe."""
        surf.blit(self._bg_layer, (0, 0))
        if self._bg_img:
            # Oscurecer un poco para que no tape los elementos
            dark = self._bg_img.copy()
            mask = pygame.Surface(dark.get_size(), pygame.SRCALPHA)
            mask.fill((0, 0, 0, 110))
            dark.blit(mask, (0, 0))
            surf.blit(dark, (0, 0))

    def _draw_particles(self, surf):
        """Capa 2: partículas flotantes."""
        for p in self._particles:
            p.update(self.sw, self.sh)
            p.draw(surf)

    def _draw_hud_overlay(self, surf):
        """Capa 3: overlay HUD externo + scanlines + decoraciones estáticas."""
        if self._hud_img:
            surf.blit(self._hud_img, (0, 0))
        surf.blit(self._scanlines, (0, 0))

        # Barras superior e inferior
        bar_h = 30
        for bar_y in [0, self.sh - bar_h]:
            b = pygame.Surface((self.sw, bar_h), pygame.SRCALPHA)
            b.fill((0, 20, 35, 200))
            pygame.draw.line(b, _CY_CYAN,
                             (0, bar_h - 1 if bar_y == 0 else 0),
                             (self.sw, bar_h - 1 if bar_y == 0 else 0), 2)
            surf.blit(b, (0, bar_y))

        # Texto barra inferior
        f_tiny = pygame.font.SysFont("consolas", 13)
        pulse_a = int(180 + 75 * abs(math.sin(self._t * 0.8)))
        left_txt  = "DATA SYNC: OK  ■  PEPIS CORE: STABLE"
        right_txt = "// FIN DEL SISTEMA //"
        _tl = f_tiny.render(left_txt,  True, (0, int(140 * pulse_a / 255), 70))
        _tr = f_tiny.render(right_txt, True, _CY_NEON)
        surf.blit(_tl, (12, self.sh - 20))
        surf.blit(_tr, (self.sw - _tr.get_width() - 12, self.sh - 20))

    def _draw_title(self, surf, fonts):
        """Capa 4: título ¡FELICIDADES! con glow verde neón."""
        title = "¡FELICIDADES!"
        pulse = abs(math.sin(self._t * 2.2))
        col   = (int(40 + 215 * pulse), 255, int(100 + 80 * pulse))
        tw    = fonts["big"].size(title)[0]
        cx    = self.sw // 2 - tw // 2
        self._glow_text(surf, title, fonts["big"], col, cx, 34, radius=8)

        # Estrellas a los lados
        for side in [-1, 1]:
            sx = self.sw // 2 + side * (tw // 2 + 24)
            draw_star_simple(surf, sx, 60, 15, True)

        # Subtítulo
        sub  = "Has completado El Pepis — Ingeniería de Sistemas"
        f_sm = fonts["small"]
        sw_  = f_sm.size(sub)[0]
        self._glow_text(surf, sub, f_sm, _CY_CYAN,
                        self.sw // 2 - sw_ // 2, 100, radius=3)

    def _draw_pepis(self, surf, pepis_img):
        """Capa 5: personaje Pepis izquierda con plataforma holográfica."""
        LEFT_W  = 305
        FOOT_Y  = self.sh - 34      # base de los pies

        bob = int(math.sin(self._t * 1.6) * 4)

        # ── Plataforma holográfica (anillos elípticos animados) ────
        plat_cx = LEFT_W // 2
        plat_cy = FOOT_Y - 4
        for i, (ring_rx, ring_ry, base_a) in enumerate(
                [(110, 18, 60), (80, 13, 45), (55, 9, 30)]):
            phase = self._t * 1.1 + i * 0.8
            a     = int(base_a + 30 * abs(math.sin(phase)))
            col   = _CY_CYAN if i % 2 == 0 else _CY_NEON
            ring  = pygame.Surface((ring_rx * 2 + 4, ring_ry * 2 + 4),
                                   pygame.SRCALPHA)
            pygame.draw.ellipse(ring, (*col, a),
                                (0, 0, ring_rx * 2 + 4, ring_ry * 2 + 4), 2)
            surf.blit(ring, (plat_cx - ring_rx - 2, plat_cy - ring_ry - 2))

        # Sombra elipse bajo personaje
        shad = pygame.Surface((160, 22), pygame.SRCALPHA)
        pygame.draw.ellipse(shad, (0, 200, 160, 50), (0, 0, 160, 22))
        surf.blit(shad, (plat_cx - 80, FOOT_Y - 10))

        # ── Sprite del personaje ───────────────────────────────────
        if pepis_img:
            pw, ph = pepis_img.get_size()
            sx     = plat_cx - pw // 2
            sy     = FOOT_Y  - ph + bob
            surf.blit(pepis_img, (sx, sy))
        else:
            # Placeholder cinemático si no hay imagen
            pw, ph = 130, 240
            sx     = plat_cx - pw // 2
            sy     = FOOT_Y - ph + bob
            ph_s   = make_placeholder(pw, ph, (20, 50, 40), "PEPIS")
            surf.blit(ph_s, (sx, sy))

        # ── Etiqueta "EL PEPIS" ────────────────────────────────────
        f_sm  = pygame.font.SysFont("consolas", 16, bold=True)
        label = "EL PEPIS"
        lw    = f_sm.size(label)[0]
        self._glow_text(surf, label, f_sm, _CY_NEON,
                        plat_cx - lw // 2, FOOT_Y + 4, radius=4)

    def _draw_panel(self, surf, fonts, level_times, icon_img):
        """Capa 6: panel de tiempos holográfico con marco sci-fi."""
        PX, PY  = 318, 122
        PW, PH  = self.sw - PX - 14, 390
        RH      = 46

        # ── Fondo del panel ───────────────────────────────────────
        panel_s = pygame.Surface((PW, PH), pygame.SRCALPHA)
        panel_s.fill((0, 14, 22, 210))
        surf.blit(panel_s, (PX, PY))

        # ── Marco del panel ───────────────────────────────────────
        # El frame_img se dibuja AL FINAL (encima) como overlay puro.
        # Si tiene fondo negro, lo hacemos transparente con colorkey
        # para que solo los bordes brillantes tapen el contenido.
        # Guardamos la referencia para blit al terminar las filas.
        use_frame = False
        frame_surf: pygame.Surface | None = None
        if self._frame_img:
            frame_surf = pygame.transform.scale(self._frame_img, (PW, PH))
            # Hacer transparente el negro del fondo de la imagen
            frame_surf = frame_surf.convert_alpha()
            # Reemplazar píxeles oscuros (< umbral) con transparente
            frame_arr = pygame.surfarray.pixels3d(frame_surf)
            alpha_arr = pygame.surfarray.pixels_alpha(frame_surf)
            # Umbral: píxeles con R+G+B < 60 → transparentes
            dark_mask = (frame_arr[:,:,0].astype(int) +
                         frame_arr[:,:,1].astype(int) +
                         frame_arr[:,:,2].astype(int)) < 60
            alpha_arr[dark_mask] = 0
            del frame_arr, alpha_arr   # liberar locks
            use_frame = True
        else:
            # Marco construido con líneas cyan
            pygame.draw.rect(surf, _CY_CYAN, (PX, PY, PW, PH), 2, border_radius=3)
            pygame.draw.rect(surf, _CY_NEON, (PX+3, PY+3, PW-6, PH-6), 1, border_radius=2)
            top_bar = pygame.Surface((PW - 6, 4), pygame.SRCALPHA)
            top_bar.fill((*_CY_NEON, 180))
            surf.blit(top_bar, (PX + 3, PY + 3))

        # Esquinas decorativas solo si NO hay frame externo
        if not use_frame:
            csz = 18
            for fx, fy, bx, by in [(False,False,PX,PY),(True,False,PX+PW-csz,PY),
                                     (False,True, PX,PY+PH-csz),(True,True,PX+PW-csz,PY+PH-csz)]:
                self._draw_hex_corner(surf, bx, by, csz, _CY_CYAN, fx, fy)
            for k in range(6):
                a = 160 - k * 22
                pygame.draw.line(surf, (*_CY_CYAN, max(0, a)),
                                 (PX + PW - 28 + k * 4, PY + 2),
                                 (PX + PW - 2,           PY + 28 - k * 4), 2)

        # ── Encabezado (solo si no hay frame — el frame ya lo trae) ──
        f_sm  = fonts["small"]
        f_med = fonts["med"]
        f_tiny = pygame.font.SysFont("consolas", 13)

        if not use_frame:
            shadow_text(surf, "TIEMPOS POR NIVEL", f_sm, _CY_GOLD, PX + 18, PY + 14)
        self._draw_hud_line(surf, PX + 10, PY + 42, PX + PW - 10, PY + 42,
                            _CY_CYAN, animated=True)

        # ── Filas ─────────────────────────────────────────────────
        total = sum(level_times)
        ry    = PY + 50

        for i, secs in enumerate(level_times):
            mins_, s_ = divmod(secs, 60)
            tstr      = f"{mins_:02d}:{s_:02d}" if mins_ else f"{secs}s"
            done      = secs > 0
            row_col   = _CY_NEON if done else (40, 70, 55)

            # Fondo alterno de fila
            if i % 2 == 0:
                rb = pygame.Surface((PW - 6, RH - 2), pygame.SRCALPHA)
                rb.fill((0, 255, 140, 10))
                surf.blit(rb, (PX + 3, ry + 1))

            # Icono izquierda
            icx, icy = PX + 30, ry + RH // 2
            if icon_img:
                isz     = 22
                iw_, ih_ = icon_img.get_size()
                iscaled  = pygame.transform.scale(
                    icon_img, (isz, int(isz * ih_ / max(iw_, 1))))
                surf.blit(iscaled, (icx - isz // 2,
                                    icy - iscaled.get_height() // 2))
            else:
                self._draw_heart(surf, icx, icy, size=13)

            # Nombre del nivel
            shadow_text(surf, f"Nivel {i + 1}", f_sm, row_col,
                        PX + 56, ry + (RH - f_sm.get_height()) // 2)

            # Tiempo (derecha, fuente med)
            tw_ = f_med.size(tstr)[0]
            self._glow_text(surf, tstr, f_med, row_col,
                            PX + PW - tw_ - 20,
                            ry + (RH - f_med.get_height()) // 2,
                            radius=3)

            # Separador de fila
            pygame.draw.line(surf, (0, 55, 45),
                             (PX + 10, ry + RH - 1),
                             (PX + PW - 10, ry + RH - 1), 1)
            ry += RH

        # ── Fila total ────────────────────────────────────────────
        pygame.draw.line(surf, _CY_GOLD,
                         (PX + 8, ry + 3), (PX + PW - 8, ry + 3), 2)

        mins_t, s_t = divmod(total, 60)
        tstr_t      = f"{mins_t:02d}:{s_t:02d}" if mins_t else f"{total}s"
        tw_t        = f_med.size(tstr_t)[0]
        self._glow_text(surf, "TIEMPO TOTAL", f_med, _CY_GOLD,
                        PX + 18, ry + 10, radius=4)
        self._glow_text(surf, tstr_t, f_med, _CY_GOLD,
                        PX + PW - tw_t - 18, ry + 10, radius=4)

        # Frame encima de todo el contenido (solo los bordes brillantes)
        if use_frame and frame_surf is not None:
            surf.blit(frame_surf, (PX, PY))

    def _draw_buttons(self, surf, fonts):
        """Capa 7: botones inferiores tipo HUD."""
        PX = 318
        PW = self.sw - PX - 14
        BY = 530

        btn_data = [
            (PX + PW // 4,       "[ ENTER ]", "Volver al menú",  _CY_CYAN),
            (PX + PW * 3 // 4,   "[ R ]",     "Reiniciar juego", (170, 170, 200)),
        ]
        f_sm   = fonts["small"]
        f_tiny = pygame.font.SysFont("consolas", 13)

        for bx, key_txt, lbl_txt, bcol in btn_data:
            BW, BH = 200, 52
            btn_s = pygame.Surface((BW, BH), pygame.SRCALPHA)
            btn_s.fill((0, 18, 28, 200))
            # Borde pulsante
            pa   = int(180 + 75 * abs(math.sin(self._t * 1.8)))
            pygame.draw.rect(btn_s, (*bcol, pa), (0, 0, BW, BH), 2, border_radius=5)
            pygame.draw.rect(btn_s, (*bcol, 40), (2, 2, BW-4, BH-4), 1, border_radius=4)
            surf.blit(btn_s, (bx - BW // 2, BY))

            kw = f_sm.size(key_txt)[0]
            lw = f_tiny.size(lbl_txt)[0]
            self._glow_text(surf, key_txt,  f_sm,   bcol,
                            bx - kw // 2, BY + 8,  radius=3)
            shadow_text(surf, lbl_txt, f_tiny, bcol,
                        bx - lw // 2, BY + 32)

    # ── Entry point principal ─────────────────────────────────────
    def draw(self, surface: pygame.Surface, fonts: dict,
             level_times: list[int],
             pepis_img:   pygame.Surface | None,
             icon_img:    pygame.Surface | None) -> None:
        """Dibuja la pantalla completa. Llamar cada frame desde el game loop."""
        self._t = pygame.time.get_ticks() / 1000.0

        self._draw_background(surface)
        self._draw_particles(surface)
        self._draw_hud_overlay(surface)
        self._draw_title(surface, fonts)
        self._draw_pepis(surface, pepis_img)
        self._draw_panel(surface, fonts, level_times, icon_img)
        self._draw_buttons(surface, fonts)


# Helper global mantenido por compatibilidad (usado en screen_gameover etc.)
def _draw_cyber_heart(surface, cx, cy, size=11):
    c1 = (220, 50, 80)
    c2 = (255, 120, 140)
    r  = size // 2
    pygame.draw.circle(surface, c1, (cx - r + 1, cy - r + 3), r)
    pygame.draw.circle(surface, c1, (cx + r - 1, cy - r + 3), r)
    pts = [(cx - size + 1, cy - r + 5),
           (cx,            cy + size - 3),
           (cx + size - 1, cy - r + 5)]
    pygame.draw.polygon(surface, c1, pts)
    pygame.draw.circle(surface, c2, (cx - r + 2, cy - r + 2), max(1, r // 2))


def screen_victory(surface, fonts, level_times, player_img=None, icon_img=None):
    """Stub de compatibilidad — en Game se usa VictoryScreen.draw() directamente."""
    pass

    # Viñeta radial oscura en las esquinas
    vig = pygame.Surface((SW, SH), pygame.SRCALPHA)
    for step in range(0, 260, 8):
        r_ = 340 - step
        a_ = step // 5
        if r_ > 0:
            pygame.draw.ellipse(vig, (0, 0, 0, a_),
                                (SW // 2 - r_, SH // 2 - r_, r_ * 2, r_ * 2))
    surface.blit(vig, (0, 0))

    # ══ BARRA SUPERIOR (scanline decorativa) ══════════════════════
    pygame.draw.rect(surface, (0, 60, 35), (0, 0, SW, 28))
    pygame.draw.line(surface, NEON, (0, 28), (SW, 28), 2)

    # ══ BARRA INFERIOR ════════════════════════════════════════════
    pygame.draw.rect(surface, (0, 60, 35), (0, SH - 28, SW, 28))
    pygame.draw.line(surface, NEON, (0, SH - 28), (SW, SH - 28), 2)
    fin_txt = "// FIN DEL SISTEMA //"
    shadow_text(surface, fin_txt, fonts["tiny"], NEON,
                SW - fonts["tiny"].size(fin_txt)[0] - 12, SH - 20)
    sync_txt = "DATA SYNC: OK  ■  PEPIS CORE: STABLE"
    shadow_text(surface, sync_txt, fonts["tiny"], (0, 160, 90),
                12, SH - 20)

    # ══ TÍTULO ════════════════════════════════════════════════════
    title   = "¡FELICIDADES!"
    pulse   = abs(math.sin(t * 2.2))
    t_green = (int(60 + 195 * pulse), 255, int(60 + 80 * pulse))
    tw      = fonts["big"].size(title)[0]
    # sombra neón tipo glow: blit 4 veces desplazado
    for dx, dy in [(-2,0),(2,0),(0,-2),(0,2)]:
        shadow_text(surface, title, fonts["big"], (0, 80, 40),
                    SW // 2 - tw // 2 + dx, 36 + dy)
    shadow_text(surface, title, fonts["big"], t_green,
                SW // 2 - tw // 2, 36)

    # Estrellas doradas flanqueando título
    for side in [-1, 1]:
        sx = SW // 2 + side * (tw // 2 + 20)
        draw_star_simple(surface, sx, 62, 14, True)

    # Subtítulo
    sub = "Has completado El Pepis — Ingeniería de Sistemas"
    sw_ = fonts["small"].size(sub)[0]
    shadow_text(surface, sub, fonts["small"], CYAN,
                SW // 2 - sw_ // 2, 100)

    # ════════════════════════════════════════════════════════════
    #  ZONA IZQUIERDA — Pepis grande
    #  Usa pepis_final.png (grande) si existe, si no pepis_idle.png
    # ════════════════════════════════════════════════════════════
    LEFT_W   = 300          # ancho reservado para el personaje
    PEPIS_CX = LEFT_W // 2  # centro horizontal de la zona
    PEPIS_BY = SH - 50      # base (pies) del personaje

    pimg = player_img       # puede ser None → placeholder
    if pimg:
        pw, ph = pimg.get_size()
        # Bob suave
        bob = int(math.sin(t * 1.8) * 5)

        # Plataforma circular neón bajo los pies
        plat_cx = PEPIS_CX
        plat_cy = PEPIS_BY - 8
        for ring_r in range(70, 10, -12):
            ring_a = int(30 + 40 * abs(math.sin(t * 1.2 + ring_r * 0.05)))
            ring_surf = pygame.Surface((ring_r * 2 + 4, 20), pygame.SRCALPHA)
            pygame.draw.ellipse(ring_surf, (*CYAN, ring_a),
                                (0, 0, ring_r * 2 + 4, 20))
            surface.blit(ring_surf,
                         (plat_cx - ring_r - 2, plat_cy - 8))

        # Halo verde detrás del sprite
        halo_r = max(pw, ph) // 2 + 30
        halo_a = int(35 + 20 * abs(math.sin(t * 1.4)))
        halo   = pygame.Surface((halo_r * 2, halo_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(halo, (*NEON, halo_a), (halo_r, halo_r), halo_r)
        surface.blit(halo, (PEPIS_CX - halo_r, PEPIS_BY - ph - halo_r + bob))

        # Sprite
        surface.blit(pimg, (PEPIS_CX - pw // 2, PEPIS_BY - ph + bob))

    else:
        # Placeholder si no hay imagen
        ph  = 180
        pw  = 120
        bob = int(math.sin(t * 1.8) * 5)
        ph_surf = make_placeholder(pw, ph, (40, 80, 60), "PEPIS")
        surface.blit(ph_surf, (PEPIS_CX - pw // 2, PEPIS_BY - ph + bob))

    # Etiqueta "EL PEPIS" bajo el personaje
    lbl = "EL PEPIS"
    lw  = fonts["small"].size(lbl)[0]
    shadow_text(surface, lbl, fonts["small"], NEON,
                PEPIS_CX - lw // 2, PEPIS_BY + 4)

    # ════════════════════════════════════════════════════════════
    #  ZONA DERECHA — panel de tiempos cyberpunk
    # ════════════════════════════════════════════════════════════
    PX   = 310     # origen X del panel
    PY   = 128     # origen Y
    PW   = SW - PX - 16   # ancho hasta el borde derecho
    RH   = 46      # alto de cada fila
    PH   = 52 + RH * 5 + 56  # alto total del panel

    # Fondo panel con bordes neón estilo HUD
    panel_s = pygame.Surface((PW, PH), pygame.SRCALPHA)
    panel_s.fill((0, 10, 5, 200))
    surface.blit(panel_s, (PX, PY))

    # Marco exterior doble línea
    pygame.draw.rect(surface, NEON,   (PX, PY, PW, PH), 2, border_radius=4)
    pygame.draw.rect(surface, (0,60,35), (PX+3, PY+3, PW-6, PH-6), 1, border_radius=3)

    # Barra diagonal decorativa en esquina superior derecha del panel
    for k in range(5):
        pygame.draw.line(surface, (*NEON, 120 - k * 20),
                         (PX + PW - 30 + k * 5, PY),
                         (PX + PW, PY + 30 - k * 5), 2)

    # Encabezado
    shadow_text(surface, "TIEMPOS POR NIVEL", fonts["small"], GOLD,
                PX + 16, PY + 14)
    pygame.draw.line(surface, NEON, (PX + 8, PY + 42), (PX + PW - 8, PY + 42), 1)

    # ── Filas de niveles ──────────────────────────────────────────
    total = sum(level_times)
    ry    = PY + 48

    for i, secs in enumerate(level_times):
        name     = f"Nivel {i + 1}"
        mins_, s_ = divmod(secs, 60)
        tstr     = f"{mins_:02d}:{s_:02d}" if mins_ else f"{secs}s"
        done     = secs > 0
        row_col  = NEON if done else (40, 70, 50)

        # Fondo de fila alterno
        if i % 2 == 0:
            rb = pygame.Surface((PW - 6, RH - 4), pygame.SRCALPHA)
            rb.fill((0, 255, 100, 12))
            surface.blit(rb, (PX + 3, ry + 2))

        # Icono — imagen PNG si existe, si no corazón vectorial
        icon_cx = PX + 28
        icon_cy = ry + RH // 2
        if icon_img:
            iw_ = icon_img.get_width()
            ih_ = icon_img.get_height()
            isz = 22
            iscaled = pygame.transform.scale(
                icon_img, (isz, int(isz * ih_ / max(iw_, 1))))
            surface.blit(iscaled,
                         (icon_cx - isz // 2,
                          icon_cy - iscaled.get_height() // 2))
        else:
            _draw_cyber_heart(surface, icon_cx, icon_cy, size=13)

        # Nombre
        shadow_text(surface, name, fonts["small"], row_col,
                    PX + 52, ry + (RH - fonts["small"].get_height()) // 2)

        # Tiempo (derecha, fuente más grande)
        tw_ = fonts["med"].size(tstr)[0]
        shadow_text(surface, tstr, fonts["med"], row_col,
                    PX + PW - tw_ - 18,
                    ry + (RH - fonts["med"].get_height()) // 2)

        # Línea separadora entre filas
        pygame.draw.line(surface, (0, 60, 35),
                         (PX + 8, ry + RH - 1),
                         (PX + PW - 8, ry + RH - 1), 1)
        ry += RH

    # ── Total ──────────────────────────────────────────────────────
    pygame.draw.line(surface, GOLD, (PX + 8, ry + 2), (PX + PW - 8, ry + 2), 2)

    mins_t, s_t = divmod(total, 60)
    tstr_total  = f"{mins_t:02d}:{s_t:02d}" if mins_t else f"{total}s"
    tw_tot      = fonts["med"].size(tstr_total)[0]
    shadow_text(surface, "TIEMPO TOTAL", fonts["med"], GOLD,
                PX + 18, ry + 12)
    shadow_text(surface, tstr_total, fonts["med"], GOLD,
                PX + PW - tw_tot - 18, ry + 12)

    # ── Botones ENTER / R estilo HUD ──────────────────────────────
    btn_y  = PY + PH + 18
    btn_defs = [
        (PX + PW // 4,       "[ ENTER ]", "Volver al menú",  CYAN),
        (PX + PW * 3 // 4,   "[ R ]",     "Reiniciar juego", (180, 180, 180)),
    ]
    for bx, key_txt, label_txt, bcol in btn_defs:
        bw, bh = 190, 48
        btn_s = pygame.Surface((bw, bh), pygame.SRCALPHA)
        btn_s.fill((0, 20, 12, 180))
        pygame.draw.rect(btn_s, bcol, (0, 0, bw, bh), 1, border_radius=6)
        surface.blit(btn_s, (bx - bw // 2, btn_y))
        kw = fonts["small"].size(key_txt)[0]
        lw = fonts["tiny"].size(label_txt)[0]
        shadow_text(surface, key_txt,   fonts["small"], bcol,
                    bx - kw // 2, btn_y + 6)
        shadow_text(surface, label_txt, fonts["tiny"],  bcol,
                    bx - lw // 2, btn_y + 28)


# ══════════════════════════════════════════════
#  GAME
# ══════════════════════════════════════════════
class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SW, SH))
        pygame.display.set_caption(TITLE)
        self.clock  = pygame.time.Clock()
        self.fonts = {
            "big":   pygame.font.SysFont("consolas", 52, bold=True),
            "med":   pygame.font.SysFont("consolas", 28, bold=True),
            "small": pygame.font.SysFont("consolas", 20),
            "tiny":  pygame.font.SysFont("consolas", 15),
        }
        base = os.path.dirname(os.path.abspath(__file__))
        icon_img = load_img(os.path.join(base, "pepis_idle.png"), 64)
        if icon_img is None:
            icon_img = make_placeholder(64, 64, (80, 110, 200), "P")
        try:
            icon_32 = pygame.transform.scale(icon_img, (32, 32))
            pygame.display.set_icon(icon_32)
        except Exception:
            pass
        self.img_player = load_img(os.path.join(base, "pepis_idle.png"), PLAYER_H)
        self.img_e_idle = load_img(os.path.join(base, "enemy_idle.png"),   ENEMY_H)
        self.img_e_att  = load_img(os.path.join(base, "enemy_attack.png"), ENEMY_H)

        # ── Assets pantalla de victoria ────────────────────────────
        # pepis_final.png — sprite grande exclusivo para la pantalla final.
        # Si no existe, usa pepis_idle.png escalado grande como fallback.
        _pf_path = os.path.join(base, "pepis_final.png")
        if os.path.exists(_pf_path):
            self.img_pepis_final = load_img(_pf_path, 340)   # alto: 340px
        else:
            self.img_pepis_final = (load_img(os.path.join(base, "pepis_idle.png"), 280)
                                    or make_placeholder(160, 280, (60, 100, 80), "PEPIS"))

        # heart.png — icono pequeño por fila. Si no existe → corazón vectorial.
        self.icon_img: pygame.Surface | None = None
        for _iname in ("heart.png", "icon.png", "pickup.png", "star.png"):
            _ip = os.path.join(base, _iname)
            if os.path.exists(_ip):
                try:
                    self.icon_img = pygame.image.load(_ip).convert_alpha()
                except Exception:
                    pass
                break
        self.sounds = SoundManager(base)
        self.sounds.play_music("menu")
        self.save_sys = SaveSystem(base)
        self.unlocked, self.level_stars = self.save_sys.load()
        self.current_lvl_idx = 0
        self.state  = "menu"
        self.level  = None
        self.quiz_answered   = -1
        self.quiz_correct    = None
        self.quiz_stars      = 0
        self.quiz_done       = False
        self._pending_stars  = 0
        self._quiz_opt_rects = []
        self._level_rects    = []

        # ── Sistema de tiempos ─────────────────────────────────────
        self.level_times:  list[int] = self.save_sys.load_times()
        self._level_start: float     = 0.0

        # ── VictoryScreen (instancia única, reutilizada cada frame) ─
        self.victory_screen = VictoryScreen(SW, SH, base)

        # ── MenuScreen (instancia única, reutilizada cada frame) ───
        self.menu_screen = MenuScreen(SW, SH, base)

    def start_level(self, idx):
        self.current_lvl_idx = idx
        self.level = Level(idx,
                           self.img_e_idle, self.img_e_att,
                           self.img_player,
                           sounds=self.sounds)
        self.state         = "playing"
        self.quiz_answered = -1
        self.quiz_correct  = None
        self.quiz_done     = False
        self._level_start  = pygame.time.get_ticks() / 1000.0   # segundos
        self.sounds.play_level_music(idx)

    def run(self):
        while True:
            self.clock.tick(FPS)
            keys = pygame.key.get_pressed()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._quit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.state in ("playing", "gameover", "quiz"):
                            self.state = "menu"
                            self.sounds.play_music("menu")
                        elif self.state == "victory":
                            self._reset_to_menu()
                        else:
                            self._quit()
                    if self.state == "playing":
                        if event.key in (pygame.K_SPACE, pygame.K_UP, pygame.K_w):
                            self.level.player.try_jump()
                    if self.state == "gameover":
                        if event.key == pygame.K_r:
                            self.start_level(self.current_lvl_idx)
                    if self.state == "quiz" and self.quiz_done:
                        if event.key == pygame.K_RETURN:
                            self._finish_quiz()
                    if self.state == "victory":
                        if event.key == pygame.K_RETURN:
                            self._reset_to_menu()
                        elif event.key == pygame.K_r:
                            self._reset_game()
                if event.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = event.pos
                    if self.state == "menu":
                        for i, (rx, ry, rw, rh) in enumerate(self._level_rects):
                            if rx <= mx <= rx + rw and ry <= my <= ry + rh:
                                if i <= self.unlocked:
                                    self.sounds.play("select")
                                    self.start_level(i)
                    elif self.state == "quiz" and self.quiz_answered < 0:
                        for i, r in enumerate(self._quiz_opt_rects):
                            if r.collidepoint(mx, my):
                                self._answer_quiz(i)

            if self.state == "playing":
                result = self.level.update(keys)
                if result == "dead":
                    self.state = "gameover"
                    self.sounds.stop_music()
                    self.sounds.play("gameover")
                elif result == "win":
                    # Registrar tiempo del nivel
                    elapsed = int(pygame.time.get_ticks() / 1000.0 - self._level_start)
                    idx     = self.current_lvl_idx
                    if self.level_times[idx] == 0 or elapsed < self.level_times[idx]:
                        self.level_times[idx] = elapsed
                    self.save_sys.save_times(self.level_times)

                    hp_r = self.level.player.hp / PLAYER_MAX_HP
                    base = 3 if hp_r > 0.7 else 2 if hp_r > 0.3 else 1
                    self._pending_stars  = base
                    self.quiz_stars      = base
                    self._quiz_opt_rects = []
                    self.quiz_answered   = -1
                    self.quiz_correct    = None
                    self.quiz_done       = False
                    # Todos los niveles pasan por el quiz primero
                    self.state = "quiz"
                    self.sounds.play("levelwin")

            if self.state == "menu":
                self._level_rects = self.menu_screen.draw(
                    self.screen, self.fonts,
                    self.unlocked, self.level_stars)
            elif self.state == "playing":
                self.level.draw(self.screen)
                draw_hud(self.screen, self.level.player, self.level,
                         self.fonts, self.current_lvl_idx)
            elif self.state == "quiz":
                self._quiz_opt_rects = screen_quiz(
                    self.screen, self.fonts,
                    self.level.quiz,
                    self.quiz_answered,
                    self.quiz_correct,
                    self.quiz_stars)
            elif self.state == "gameover":
                self.level.draw(self.screen)
                screen_gameover(self.screen, self.fonts)
            elif self.state == "victory":
                self.victory_screen.draw(
                    self.screen, self.fonts, self.level_times,
                    pepis_img=self.img_pepis_final,
                    icon_img=self.icon_img)

            pygame.display.flip()

    def _answer_quiz(self, i):
        self.quiz_answered = i
        self.quiz_correct  = (i == self.level.quiz["ans"])
        if self.quiz_correct:
            self.quiz_stars = 3
            self.sounds.play("correct")
        else:
            self.quiz_stars = min(2, self._pending_stars)
            self.sounds.play("hit")
        self.quiz_done = True

    def _finish_quiz(self):
        earned = self.quiz_stars
        idx    = self.current_lvl_idx

        # Desbloquear siguiente nivel
        if earned >= 2:
            new_unlock    = min(4, idx + 1)
            self.unlocked = max(self.unlocked, new_unlock)
        self.level_stars[idx] = max(self.level_stars[idx], earned)
        self.save_sys.save(self.unlocked, self.level_stars)

        # Nivel 5 → pantalla de victoria, resto → menú
        if idx == 4:
            self.sounds.stop_music()
            self.state = "victory"
        else:
            self.state = "menu"
            self.sounds.play_music("menu")

    def _reset_to_menu(self) -> None:
        """Vuelve al menú principal desde la pantalla de victoria."""
        self.state = "menu"
        self.sounds.play_music("menu")

    def _reset_game(self) -> None:
        """Reinicia todo el progreso y vuelve al nivel 1."""
        self.unlocked     = 0
        self.level_stars  = [0, 0, 0, 0, 0]
        self.level_times  = [0, 0, 0, 0, 0]
        self.save_sys.save(self.unlocked, self.level_stars)
        self.save_sys.save_times(self.level_times)
        self.state = "menu"
        self.sounds.play_music("menu")

    def _quit(self):
        self.save_sys.save(self.unlocked, self.level_stars)
        pygame.quit()
        sys.exit()


# ══════════════════════════════════════════════
#  ENTRADA
# ══════════════════════════════════════════════
if __name__ == "__main__":
    Game().run()