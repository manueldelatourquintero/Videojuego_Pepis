# ══════════════════════════════════════════════════════════════════
#  tilemap.py  —  Sistema de TileMap para El Pepis v3
#  Auto-tiling basado en vecinos (16-tile bitmask)
#  Compatible 100% con el sistema actual de Level, Player y Enemy
# ══════════════════════════════════════════════════════════════════

import pygame
import os
import math

# ─────────────────────────────────────────────────────────────────
#  CONSTANTES
# ─────────────────────────────────────────────────────────────────
TILE = 48          # Tamaño en píxeles de cada tile (coincide con el juego)
AIR  = 0           # Vacío / aire — no colisiona, no se dibuja
SOLID = 1          # Tile sólido principal (suelo / bloque)
PLATFORM = 2       # Plataforma one-way (solo colisión desde arriba)
DECO = 3           # Decoración visual, no colisiona

# ─────────────────────────────────────────────────────────────────
#  AUTO-TILING — tabla de bitmask → (col, row) en el tileset
#
#  Bitmask de 4 bits usando vecinos ortogonales:
#    bit 3 = arriba, bit 2 = derecha, bit 1 = abajo, bit 0 = izquierda
#    (solo vecinos del mismo tipo cuentan como "conectados")
#
#  Tileset Tiles.png: 8 columnas × 12 filas a 48 px
#  Fila 0-1: estructuras industriales (arriba) — usadas como deco BG
#  Fila 2-7: bloques principales del nivel
#  Fila 8-9: panel/ventana (mid)
#  Fila 10-11: suelo con rivet (bottom)
#
#  Mapeo elegido para el tileset industrial morado:
#   - Tiles sólidos (SOLID): Filas 10-11 (rivet floor) para suelo,
#     Fila 2-3 para bloques flotantes/plataformas
#   - Plataformas (PLATFORM): Fila 0 (shelf/ledge)
# ─────────────────────────────────────────────────────────────────

# Índices de tiles en el tileset (col, row) para 48×48
# Usamos las filas más reconocibles del tileset industrial
_T = {
    # ── Tiles SOLID (suelo / bloques) ────────────────────────────
    # Clave: bitmask UDRL (Up Down Right Left como bits 3,2,1,0)
    # Valor: (col_tileset, row_tileset)

    # Isla flotante (sin vecinos) — bloque solo
    0b0000: (2, 10),   # solo → tile con borde completo (rivet)

    # Una conexión
    0b1000: (1, 10),   # solo arriba conectado
    0b0100: (2, 11),   # solo abajo conectado
    0b0010: (3, 10),   # solo derecha conectada
    0b0001: (1, 10),   # solo izquierda conectada

    # Dos conexiones — opuestos (tubería)
    0b1010: (0, 10),   # arriba + abajo (columna vertical)
    0b0101: (4, 10),   # izq + der (fila horizontal, sin borde arriba/abajo)

    # Dos conexiones — esquinas
    0b1001: (0, 11),   # arriba + izq (esquina sup-izq)
    0b1100: (1, 11),   # arriba + abajo + nada lados → usar borde
    0b0110: (3, 11),   # der + abajo (esquina inf-der)
    0b0011: (4, 11),   # abajo + izq (esquina inf-izq)
    0b1010: (0, 10),   # arriba + der
    0b0110: (3, 11),
    0b0011: (4, 11),

    # Tres conexiones — T juntas
    0b1110: (5, 10),   # arriba + der + abajo (T izq)
    0b1101: (6, 10),   # arriba + izq + abajo (T der)
    0b1011: (5, 11),   # arriba + der + izq  (T abajo)
    0b0111: (6, 11),   # der + abajo + izq   (T arriba)

    # Todo conectado — interior
    0b1111: (7, 10),   # completamente rodeado → tile interior

    # Bordes (arriba libre = top edge más común)
    0b0110: (3, 10),   # borde superior derecha
    0b0011: (2, 10),   # borde superior izquierda
}

# Tileset PLATFORM (plataforma one-way): usa fila 0 del tileset
_P = {
    0b0000: (0, 0),
    0b0010: (1, 0),   # conectada a la derecha
    0b0001: (2, 0),   # conectada a la izquierda
    0b0011: (3, 0),   # centro (izq + der)
    0b0010: (4, 0),
}

# Tiles de decoración: columna 5-7 filas 0-7
_DECO_TILES = [
    (5, 0), (6, 0), (7, 0),
    (5, 1), (6, 1), (7, 1),
    (5, 2), (6, 2), (7, 2),
]


# ─────────────────────────────────────────────────────────────────
#  CLASE TILESET — carga y recorta una imagen en tiles
# ─────────────────────────────────────────────────────────────────
class Tileset:
    """
    Carga una imagen y la divide en tiles de tile_size × tile_size.
    Uso:
        ts = Tileset("Tiles.png", tile_size=48)
        surf = ts.get(col, row)
    """

    def __init__(self, path: str, tile_size: int = TILE):
        self.tile_size = tile_size
        self._cache: dict[tuple, pygame.Surface] = {}

        if os.path.exists(path):
            raw = pygame.image.load(path).convert_alpha()
        else:
            # Fallback: tileset generado programáticamente
            raw = self._make_fallback(tile_size)

        self._img   = raw
        self._cols  = raw.get_width()  // tile_size
        self._rows  = raw.get_height() // tile_size

    # ── API pública ───────────────────────────────────────────────
    def get(self, col: int, row: int) -> pygame.Surface:
        key = (col, row)
        if key in self._cache:
            return self._cache[key]
        s = self.tile_size
        # Clamp para evitar errores fuera de rango
        col = col % self._cols
        row = row % self._rows
        surf = pygame.Surface((s, s), pygame.SRCALPHA)
        surf.blit(self._img, (0, 0),
                  pygame.Rect(col * s, row * s, s, s))
        self._cache[key] = surf
        return surf

    def get_scaled(self, col: int, row: int,
                   w: int, h: int) -> pygame.Surface:
        """Devuelve el tile escalado a (w, h)."""
        base = self.get(col, row)
        if w == self.tile_size and h == self.tile_size:
            return base
        key = (col, row, w, h)
        if key in self._cache:
            return self._cache[key]
        s = pygame.transform.scale(base, (w, h))
        self._cache[key] = s
        return s

    # ── Fallback programático ─────────────────────────────────────
    @staticmethod
    def _make_fallback(tile_size: int) -> pygame.Surface:
        """
        Genera un tileset de 8×12 tiles con bloques coloreados
        cuando el archivo de imagen no existe.
        """
        cols, rows = 8, 12
        s    = tile_size
        surf = pygame.Surface((cols * s, rows * s), pygame.SRCALPHA)

        for row in range(rows):
            for col in range(cols):
                # Color varía por posición
                r = int(40  + col * 25)
                g = int(30  + row * 15)
                b = int(120 + col * 10 - row * 5)
                rect = pygame.Rect(col * s, row * s, s, s)
                pygame.draw.rect(surf, (r, g, b), rect)
                pygame.draw.rect(surf, (r + 40, g + 40, b + 40), rect, 2)
                # Rivet decorativo
                pygame.draw.circle(surf, (min(255, r + 60), g, b),
                                   (col * s + 8, row * s + 8), 3)
                pygame.draw.circle(surf, (min(255, r + 60), g, b),
                                   (col * s + s - 8, row * s + s - 8), 3)

        return surf


# ─────────────────────────────────────────────────────────────────
#  AUTO-TILE — decide qué tile del tileset usar según vecinos
# ─────────────────────────────────────────────────────────────────
class AutoTiler:
    """
    Calcula el bitmask de vecinos para cada celda y devuelve
    las coordenadas (col, row) correctas del tileset.

    Lógica de bitmask ortogonal de 4 bits:
        bit 3 = vecino arriba
        bit 2 = vecino derecha
        bit 1 = vecino abajo
        bit 0 = vecino izquierda
    """

    # ── Mapeo completo SOLID (16 combinaciones) ───────────────────
    # Tileset industrial morado — distribución elegida visualmente:
    #   Fila 10: variantes del "rivet floor" (tiles sólidos base)
    #   Fila 11: esquinas y bordes del rivet floor
    #   Fila  2: variantes de bloque industrial oscuro
    #   Fila  0: shelf / borde de plataforma

    SOLID_MAP = {
        # bitmask → (col, row) en el tileset
        # ── Sin vecinos (isla) ────────────────────────────────────
        0b0000: (2, 10),

        # ── Un vecino ─────────────────────────────────────────────
        0b1000: (3, 10),   # arriba
        0b0100: (3, 11),   # derecha
        0b0010: (2, 11),   # abajo
        0b0001: (1, 11),   # izquierda

        # ── Dos vecinos (opuestos = corredor) ─────────────────────
        0b1010: (0, 10),   # arriba + abajo  → columna
        0b0101: (4, 10),   # izq   + der     → fila

        # ── Dos vecinos (esquinas) ────────────────────────────────
        0b1100: (5, 10),   # arriba + der
        0b1001: (6, 10),   # arriba + izq
        0b0110: (5, 11),   # der   + abajo
        0b0011: (6, 11),   # abajo + izq

        # ── Tres vecinos (T) ──────────────────────────────────────
        0b1110: (7, 10),   # arriba + der + abajo  → T apuntando izq
        0b1101: (0, 11),   # arriba + izq + abajo  → T apuntando der
        0b1011: (7, 11),   # arriba + der + izq    → T apuntando abajo
        0b0111: (4, 11),   # der   + abajo + izq   → T apuntando arriba

        # ── Todos los vecinos (interior) ─────────────────────────
        0b1111: (1, 10),
    }

    # ── Mapeo PLATFORM (one-way) ──────────────────────────────────
    # Usa fila 0 del tileset: los tiles tipo "ledge/shelf"
    PLATFORM_MAP = {
        0b0000: (0, 0),    # isla sola
        0b0100: (1, 0),    # conectada a la derecha
        0b0001: (2, 0),    # conectada a la izquierda
        0b0101: (3, 0),    # centro (izq + der)
        0b0100: (4, 0),    # extremo derecho
    }

    @classmethod
    def get_solid_tile(cls, bitmask: int) -> tuple[int, int]:
        """Devuelve (col, row) del tileset para un tile SOLID."""
        return cls.SOLID_MAP.get(bitmask, (2, 10))

    @classmethod
    def get_platform_tile(cls, bitmask: int) -> tuple[int, int]:
        """Devuelve (col, row) del tileset para un tile PLATFORM."""
        return cls.PLATFORM_MAP.get(bitmask, (0, 0))


# ─────────────────────────────────────────────────────────────────
#  CLASE TILEMAP — núcleo del sistema
# ─────────────────────────────────────────────────────────────────
class TileMap:
    """
    Representa el nivel como una matriz 2D de enteros.
    Gestiona: carga del tileset, auto-tiling, colisiones y renderizado.

    Valores de celda:
        AIR      = 0   vacío, no colisiona, no se dibuja
        SOLID    = 1   bloque sólido, colisiona por todos los lados
        PLATFORM = 2   plataforma one-way (solo colisión desde arriba)
        DECO     = 3   decoración, no colisiona (dibujada antes que SOLID)

    Uso básico:
        tm = TileMap(grid, tileset_path="Tiles.png")
        rects = tm.get_solid_rects()           # para colisiones
        platforms = tm.get_platform_rects()    # plataformas one-way
        tm.draw(surface, camera_x)             # renderizado optimizado
    """

    def __init__(self, grid: list[list[int]],
                 tileset_path: str = "Tiles.png",
                 tile_size: int = TILE,
                 bg_tileset_path: str | None = None):
        self.grid      = grid
        self.tile_size = tile_size
        self.rows      = len(grid)
        self.cols      = max((len(row) for row in grid), default=0)
        self.world_w   = self.cols * tile_size
        self.world_h   = self.rows * tile_size

        # ── Cargar tilesets ───────────────────────────────────────
        self.tileset    = Tileset(tileset_path,    tile_size)
        self.bg_tileset = (Tileset(bg_tileset_path, tile_size)
                           if bg_tileset_path else None)

        # ── Precalcular bitmasks y tiles renderizables ────────────
        # self._tile_surfs[row][col] = Surface ya cortada y lista
        # self._bg_surfs[row][col]  = Surface de decoración de fondo
        self._tile_surfs: list[list[pygame.Surface | None]] = []
        self._bg_surfs:   list[list[pygame.Surface | None]] = []
        self._bitmasks:   list[list[int]] = []
        self._bake()

        # ── Caché de rectángulos de colisión ─────────────────────
        # Se generan una sola vez al cargar el mapa.
        self._solid_rects:    list[pygame.Rect] = []
        self._platform_rects: list[pygame.Rect] = []
        self._build_collision_rects()

    # ──────────────────────────────────────────────────────────────
    #  BAKE — precalcular qué tile visual usar en cada celda
    # ──────────────────────────────────────────────────────────────
    def _bake(self):
        """
        Calcula el bitmask de vecinos y selecciona el tile del
        tileset para cada celda. Los resultados se guardan en
        self._tile_surfs para evitar recalcular en cada frame.
        """
        for row in range(self.rows):
            row_surfs = []
            row_bg    = []
            row_masks = []

            for col in range(self.cols):
                cell = self._get(row, col)

                if cell == AIR:
                    row_surfs.append(None)
                    row_bg.append(None)
                    row_masks.append(0)
                    continue

                # Calcular bitmask con vecinos del mismo "grupo"
                mask = self._bitmask_for(row, col, cell)
                row_masks.append(mask)

                if cell == SOLID:
                    tc, tr = AutoTiler.get_solid_tile(mask)
                    row_surfs.append(self.tileset.get(tc, tr))
                    row_bg.append(None)

                elif cell == PLATFORM:
                    # Máscara solo horizontal (bit 2=der, bit 0=izq)
                    pmask = (mask & 0b0100) | (mask & 0b0001)
                    tc, tr = AutoTiler.get_platform_tile(pmask)
                    row_surfs.append(self.tileset.get(tc, tr))
                    row_bg.append(None)

                elif cell == DECO:
                    # Decoración: tile fijo de la zona decorativa
                    col_idx = (col + row) % 3
                    dc, dr  = _DECO_TILES[col_idx]
                    deco_s  = self.tileset.get(dc, dr)
                    # Semitransparente para fondo
                    bg = deco_s.copy()
                    bg.set_alpha(140)
                    row_surfs.append(None)
                    row_bg.append(bg)

                else:
                    row_surfs.append(None)
                    row_bg.append(None)

            self._tile_surfs.append(row_surfs)
            self._bg_surfs.append(row_bg)
            self._bitmasks.append(row_masks)

    def _bitmask_for(self, row: int, col: int, cell_type: int) -> int:
        """
        Bitmask de 4 bits: vecinos que son del mismo tipo sólido.
        Un SOLID y un PLATFORM NO se conectan entre sí.
        Bits: Up=3, Right=2, Down=1, Left=0
        """
        # "Sólido" cuenta como vecino para bitmask si es del mismo grupo
        same = lambda r, c: (
            0 <= r < self.rows and
            0 <= c < self.cols and
            self._get(r, c) == cell_type
        )

        mask = 0
        if same(row - 1, col): mask |= 0b1000   # arriba
        if same(row,     col + 1): mask |= 0b0100 # derecha
        if same(row + 1, col): mask |= 0b0010   # abajo
        if same(row,     col - 1): mask |= 0b0001 # izquierda
        return mask

    # ──────────────────────────────────────────────────────────────
    #  COLISIONES — generar listas de pygame.Rect
    # ──────────────────────────────────────────────────────────────
    def _build_collision_rects(self):
        """
        Genera los rectángulos de colisión una sola vez.
        Los rects de plataforma son de altura TILE//3 en el borde superior.
        """
        s = self.tile_size
        for row in range(self.rows):
            for col in range(self.cols):
                cell = self._get(row, col)
                x = col * s
                y = row * s
                if cell == SOLID:
                    self._solid_rects.append(pygame.Rect(x, y, s, s))
                elif cell == PLATFORM:
                    # Solo la franja superior del tile (colisión one-way)
                    self._platform_rects.append(
                        pygame.Rect(x, y, s, s // 3))

    # ──────────────────────────────────────────────────────────────
    #  API PÚBLICA — colisiones
    # ──────────────────────────────────────────────────────────────
    def get_solid_rects(self) -> list[pygame.Rect]:
        """Lista de pygame.Rect para todos los tiles SOLID."""
        return self._solid_rects

    def get_platform_rects(self) -> list[pygame.Rect]:
        """Lista de pygame.Rect (franja superior) para tiles PLATFORM."""
        return self._platform_rects

    def get_all_collision_rects(self) -> tuple[list[pygame.Rect],
                                               list[pygame.Rect]]:
        """Devuelve (solid_rects, platform_rects)."""
        return self._solid_rects, self._platform_rects

    def get_visible_solid_rects(self, cam_x: float,
                                view_w: int = 1000,
                                margin: int = 96) -> list[pygame.Rect]:
        """
        Optimización: devuelve solo los rects SOLID visibles en pantalla.
        Útil para pasar al Player/Enemy en update() sin iterar miles de rects.
        """
        s = self.tile_size
        col_min = max(0, int((cam_x - margin) / s))
        col_max = min(self.cols,
                      int((cam_x + view_w + margin) / s) + 1)
        result = []
        for r in self._solid_rects:
            if col_min * s <= r.x < col_max * s:
                result.append(r)
        return result

    def get_visible_platform_rects(self, cam_x: float,
                                   view_w: int = 1000,
                                   margin: int = 96) -> list[pygame.Rect]:
        """Igual que get_visible_solid_rects pero para PLATFORM."""
        s = self.tile_size
        col_min = max(0, int((cam_x - margin) / s))
        col_max = min(self.cols,
                      int((cam_x + view_w + margin) / s) + 1)
        result = []
        for r in self._platform_rects:
            if col_min * s <= r.x < col_max * s:
                result.append(r)
        return result

    # ──────────────────────────────────────────────────────────────
    #  API PÚBLICA — renderizado
    # ──────────────────────────────────────────────────────────────
    def draw(self, surface: pygame.Surface, cam_x: float,
             view_w: int = 1000, view_h: int = 600,
             margin: int = 1):
        """
        Dibuja solo los tiles visibles en pantalla (frustum culling).

        Orden de dibujo:
          1. Tiles DECO (fondo semitransparente)
          2. Tiles SOLID y PLATFORM (sólidos con auto-tiling)

        Parámetros:
            surface : pygame.Surface   — superficie destino
            cam_x   : float            — posición X de la cámara
            view_w  : int              — ancho de la ventana (SW)
            view_h  : int              — alto de la ventana (SH)
            margin  : int              — columnas extra fuera de pantalla
        """
        s = self.tile_size

        # Rango de columnas visibles
        col_start = max(0, int(cam_x / s) - margin)
        col_end   = min(self.cols, int((cam_x + view_w) / s) + margin + 1)

        # Rango de filas visibles
        row_start = max(0, 0)           # normalmente toda la altura
        row_end   = min(self.rows, int(view_h / s) + 2)

        # ── Paso 1: decoración de fondo ───────────────────────────
        for row in range(row_start, row_end):
            for col in range(col_start, col_end):
                bg = self._bg_surfs[row][col]
                if bg is not None:
                    sx = col * s - int(cam_x)
                    sy = row * s
                    surface.blit(bg, (sx, sy))

        # ── Paso 2: tiles sólidos y plataformas ───────────────────
        for row in range(row_start, row_end):
            for col in range(col_start, col_end):
                surf = self._tile_surfs[row][col]
                if surf is not None:
                    sx = col * s - int(cam_x)
                    sy = row * s
                    surface.blit(surf, (sx, sy))

    # ──────────────────────────────────────────────────────────────
    #  HELPERS
    # ──────────────────────────────────────────────────────────────
    def _get(self, row: int, col: int) -> int:
        """Devuelve el valor de la celda, 0 (AIR) si fuera de rango."""
        if 0 <= row < self.rows and 0 <= col < len(self.grid[row]):
            return self.grid[row][col]
        return AIR

    def world_to_tile(self, wx: float, wy: float) -> tuple[int, int]:
        """Convierte coordenadas mundiales a (col, row) del mapa."""
        return int(wx // self.tile_size), int(wy // self.tile_size)

    def tile_to_world(self, col: int, row: int) -> tuple[int, int]:
        """Convierte (col, row) del mapa a coordenadas mundiales (px)."""
        return col * self.tile_size, row * self.tile_size

    @property
    def ground_y(self) -> int:
        """
        Píxel Y del borde SUPERIOR de la fila sólida más baja del mapa.
        Es el punto donde una entidad aterriza en el suelo base.
        Se usa como safety-net absoluto en Player.update y Enemy.update.
        """
        s = self.tile_size
        for row in range(self.rows - 1, -1, -1):
            for col in range(self.cols):
                if self._get(row, col) == SOLID:
                    return row * s      # top del tile, no bottom
        return self.world_h - s


# ─────────────────────────────────────────────────────────────────
#  MAPAS DE NIVEL — 5 niveles tipo Mario con huecos y plataformas
#  Nomenclatura: 0=AIR, 1=SOLID, 2=PLATFORM, 3=DECO
#  Ancho: ~100 tiles, Alto: 13 filas
#  Los niveles son compatibles con los LEVEL_DEFS originales
# ─────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────
#  MAPAS DE NIVEL — diseño estilo Mario
#  Leyenda: 0=AIR  1=SOLID  2=PLATFORM(one-way)  3=DECO
#  Grid: 13 filas de alto (filas 0-12, fila 12 = suelo base)
#  Altura útil de juego: filas 4-11  (9 filas × 48px = 432px)
#
#  Filosofía de cada nivel:
#    Nivel 1 — Tutorial: suelo casi continuo, plataformas anchas, 2 huecos
#    Nivel 2 — Escalones: secciones a 3 alturas distintas, zigzag claro
#    Nivel 3 — Isla a isla: mucho aire, saltos precisos obligatorios
#    Nivel 4 — Verticaldad: columnas, escaleras, huecos profundos
#    Nivel 5 — Caos controlado: solo plataformas, sin suelo, timing crítico
# ─────────────────────────────────────────────────────────────────

S  = SOLID
P  = PLATFORM
A  = AIR
D  = DECO

def _col(grid, col, row_start, row_end, val=SOLID):
    """Rellena una columna vertical de tiles."""
    for r in range(row_start, row_end):
        if 0 <= r < len(grid) and 0 <= col < len(grid[r]):
            grid[r][col] = val

def _row_range(grid, row, col_start, col_end, val=SOLID):
    """Rellena un rango horizontal de una fila."""
    for c in range(col_start, min(col_end, len(grid[row]))):
        grid[row][c] = val

def _floor(grid, col_start, col_end):
    """Coloca suelo doble (filas 11 y 12) en el rango dado."""
    _row_range(grid, 11, col_start, col_end, SOLID)
    _row_range(grid, 12, col_start, col_end, SOLID)

def _plat(grid, row, col_start, col_end):
    """Coloca plataforma one-way."""
    _row_range(grid, row, col_start, col_end, PLATFORM)

def _block(grid, row, col_start, col_end):
    """Coloca bloque sólido (una fila)."""
    _row_range(grid, row, col_start, col_end, SOLID)


# ── Nivel 1 — Tutorial ───────────────────────────────────────────
# Concepto: presentar huecos pequeños, plataformas a 2 alturas,
# un escalón de bloques al centro. Enemigos en zonas de paso.
#
# Enemigos (4): 1 al inicio fácil, 2 en zona media, 1 en final
# Posiciones X recomendadas (en px): 600, 1150, 1800, 3600
#
#   col:  0         10        20        30        40        50        60        70        80        90       99
# fila 4  . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
# fila 5  . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
# fila 6  . . . [P P P] . . . . . . . . . . . . . [P P P] . . . . . [P P P P] . . . . . . . [P P P] . . .
# fila 7  . . . . . . . . . . . . . . [P P P P] . . . . . . . . . . . . . . . . . [P P P P] . . . . . . .
# fila 8  [P P P P] . . . . . [P P P P] . . . . . . . . . [P P P P] . . . . . . . . . . . . . . . [P P P P]
# fila 9  . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
# fila10  . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
# fila11  [S S S S S S S] . [S S S S] . [S S S S S S] . [S S S S] . [S S S S S S] . [S S S S] . [S S S S S]
# fila12  [S S S S S S S S S S S S S S S S S S S S S S S S S S S S S S S S S S S S S S S S S S S S S S S S S]
def make_level_1_grid():
    C = 100
    G = [[A] * C for _ in range(13)]

    # Suelo base completo en fila 12 (safety net visual)
    _row_range(G, 12, 0, C, SOLID)

    # Suelo jugable en fila 11 con 3 huecos
    # Segmento 1: cols 0-14
    _floor(G, 0, 15)
    # Hueco 1: cols 15-18 (3 tiles = saltable fácil)
    # Segmento 2: cols 19-35
    _floor(G, 19, 36)
    # Hueco 2: cols 36-39 (4 tiles = saltable con run)
    # Segmento 3: cols 40-59
    _floor(G, 40, 60)
    # Hueco 3: cols 60-63 (4 tiles = necesita plataforma intermedia)
    # Segmento 4: cols 64-79
    _floor(G, 64, 80)
    # Hueco 4: cols 80-83
    # Segmento 5: cols 84-99
    _floor(G, 84, C)

    # Plataformas bajas (fila 8) — paso sobre huecos y ruta alternativa
    _plat(G, 8,  3,  7)    # sobre inicio
    _plat(G, 8, 14, 19)    # puente sobre hueco 1
    _plat(G, 8, 32, 37)    # sobre hueco 2
    _plat(G, 8, 57, 62)    # sobre inicio hueco 3
    _plat(G, 8, 62, 67)    # aterrizaje tras hueco 3
    _plat(G, 8, 78, 84)    # puente hueco 4
    _plat(G, 8, 93, 99)    # final

    # Plataformas medias (fila 6) — ruta alta opcional
    _plat(G, 6, 22, 27)
    _plat(G, 6, 44, 49)
    _plat(G, 6, 68, 73)

    # Plataformas altas (fila 4) — bonus/secreto
    _plat(G, 4, 10, 14)
    _plat(G, 4, 55, 60)
    _plat(G, 4, 85, 90)

    # Bloques decorativos / escalones
    _block(G, 10,  5,  6)   # escalón de 1 tile
    _block(G,  9,  6,  7)
    _block(G, 10, 46, 47)
    _block(G,  9, 47, 48)
    _block(G,  8, 48, 49)

    return G


# ── Nivel 2 — Escalones y zigzag ─────────────────────────────────
# Concepto: el nivel sube y baja en 3 alturas de suelo distintas.
# No hay suelo continuo — el jugador siempre está eligiendo ruta.
# Enemigos (6): distribuidos en cada plataforma grande.
# Posiciones X recomendadas: 400, 900, 1550, 2300, 3100, 4200
def make_level_2_grid():
    C = 118
    G = [[A] * C for _ in range(13)]

    _row_range(G, 12, 0, C, SOLID)   # safety net

    # Zona A (cols 0-25): suelo bajo — nivel 11
    _floor(G, 0, 12)
    # hueco 12-14
    _floor(G, 15, 25)

    # Escalón subida (cols 22-30): plataformas escalera hacia nivel 9
    _plat(G, 10, 22, 26)
    _plat(G,  8, 26, 30)

    # Zona B (cols 28-55): suelo medio — fila 9
    _block(G,  9, 28, 50)
    _block(G, 10, 28, 50)
    # Hueco dentro de zona B
    for c in range(37, 41):
        G[9][c] = A
        G[10][c] = A

    # Plataformas en zona B
    _plat(G, 6, 30, 35)
    _plat(G, 6, 44, 50)

    # Escalón subida (cols 50-60)
    _plat(G, 8, 50, 54)
    _plat(G, 6, 54, 58)

    # Zona C (cols 58-90): suelo alto — fila 7
    _block(G,  7, 58, 80)
    _block(G,  8, 58, 80)
    # Huecos en zona C
    for c in range(65, 69):
        G[7][c] = A
        G[8][c] = A
    for c in range(76, 80):
        G[7][c] = A
        G[8][c] = A

    # Plataformas en zona C
    _plat(G, 5, 60, 65)
    _plat(G, 5, 70, 76)
    _plat(G, 5, 80, 85)

    # Descenso final (cols 80-90)
    _plat(G, 7, 80, 84)
    _plat(G, 9, 84, 88)

    # Zona final (cols 88-117): suelo bajo de nuevo
    _floor(G, 88, C)
    # Hueco final difícil
    for c in range(100, 105):
        G[11][c] = A

    _plat(G, 9, 100, 105)   # puente sobre hueco final
    _plat(G, 7,  92,  98)   # plataforma alta final

    return G


# ── Nivel 3 — Isla a isla ────────────────────────────────────────
# Concepto: muy poco suelo, el jugador salta de isla en isla.
# Cada isla tiene 3-6 tiles. Algunas solo accesibles con doble salto.
# Enemigos (8): uno por isla grande, forzando decisión de engagement.
# Posiciones X recomendadas: 350,900,1500,2100,2800,3400,4000,4700
def make_level_3_grid():
    C = 134
    G = [[A] * C for _ in range(13)]

    _row_range(G, 12, 0, C, SOLID)   # safety net

    # Isla de inicio (siempre segura, ancha)
    _floor(G, 0, 8)

    # Secuencia de islas con gap variable
    islas = [
        # (col_start, col_end, fila_suelo, tiene_plat_encima, fila_plat)
        (12, 18, 11, True,  8),
        (22, 26, 11, False, 0),
        (30, 36,  9, True,  6),   # isla elevada
        (40, 44, 11, True,  8),
        (48, 53,  9, True,  6),
        (57, 61, 11, False, 0),
        (65, 70,  7, True,  4),   # muy alta
        (74, 79, 11, True,  8),
        (83, 87,  9, True,  6),
        (91, 97, 11, True,  8),
        (101,106, 9, True,  6),
        (110,116, 11,True,  8),
        (120,134, 11,False, 0),   # isla final larga
    ]

    for (cs, ce, row_suelo, tiene_plat, row_plat) in islas:
        # Suelo de la isla
        for r in range(row_suelo, 13):
            _row_range(G, r, cs, ce, SOLID)
        # Plataforma encima si aplica
        if tiene_plat and row_plat > 0:
            _plat(G, row_plat, cs, cs + min(4, ce - cs))

    # Plataformas puente sobre los gaps más largos
    _plat(G, 9, 26, 30)       # gap 26-30
    _plat(G, 9, 44, 48)       # gap 44-48
    _plat(G, 9, 61, 65)       # gap 61-65
    _plat(G, 9, 87, 91)       # gap 87-91

    return G


# ── Nivel 4 — Verticalidad y columnas ───────────────────────────
# Concepto: el nivel tiene 3 "torres" que el jugador debe escalar
# y secciones de suelo muy fragmentado debajo.
# Enemigos (10): guardianes de cada torre y emboscadas en huecos.
# Posiciones X recomendadas: 300,750,1200,1800,2400,2900,3500,4100,4700,5500
def make_level_4_grid():
    C = 152
    G = [[A] * C for _ in range(13)]

    _row_range(G, 12, 0, C, SOLID)   # safety net

    # Inicio seguro
    _floor(G, 0, 10)

    # Fragmentos de suelo bajo (fila 11) con huecos amplios
    fragmentos_bajos = [(13, 20), (25, 30), (35, 40), (45, 50),
                        (55, 60), (65, 70), (75, 80), (85, 90),
                        (95,100), (105,110),(115,120),(125,130),
                        (135,140),(143,152)]
    for (cs, ce) in fragmentos_bajos:
        _floor(G, cs, ce)

    # Torre 1 (cols 18-22): columna vertical + plataformas escalera
    for r in range(5, 12):
        G[r][18] = SOLID
        G[r][19] = SOLID
    _plat(G, 9, 14, 18)     # acceso torre 1
    _plat(G, 7, 20, 25)     # salida torre 1 hacia la derecha
    _plat(G, 5, 13, 18)     # cima torre 1

    # Torre 2 (cols 60-63): más alta
    for r in range(4, 12):
        G[r][60] = SOLID
        G[r][61] = SOLID
    _plat(G,  9, 55, 60)    # acceso
    _plat(G,  7, 62, 67)    # salida
    _plat(G,  5, 55, 60)    # nivel medio
    _plat(G,  4, 61, 66)    # cima

    # Torre 3 (cols 110-113): la más alta, necesita doble salto
    for r in range(3, 12):
        G[r][110] = SOLID
        G[r][111] = SOLID
    _plat(G, 9, 105, 110)
    _plat(G, 7, 112, 117)
    _plat(G, 5, 105, 110)
    _plat(G, 3, 111, 116)   # cima más alta del juego

    # Plataformas de conexión entre torres
    _plat(G, 8, 30, 35)
    _plat(G, 7, 40, 45)
    _plat(G, 8, 50, 55)
    _plat(G, 8, 80, 85)
    _plat(G, 7, 90, 95)
    _plat(G, 8,100,105)
    _plat(G, 7,120,125)
    _plat(G, 8,130,135)
    _plat(G, 7,140,145)

    return G


# ── Nivel 5 — Sin suelo, solo plataformas ───────────────────────
# Concepto: no hay suelo — caer es morir. Todas las plataformas
# son small (2-3 tiles). Timing y doble salto son críticos.
# Enemigos (14): en plataformas grandes. Difícil evitarlos.
# Posiciones X recomendadas: 400,800,1200,1700,2200,2700,3200,
#                            3700,4200,4700,5200,5700,6200,6800
def make_level_5_grid():
    C = 168
    G = [[A] * C for _ in range(13)]

    _row_range(G, 12, 0, C, SOLID)   # safety net invisible (fila 12 = muerte)
    # No hay fila 11 sólida — caer a fila 12 = pit

    # Isla de inicio (amplia — el jugador necesita orientarse)
    _block(G, 11, 0, 10)

    # Secuencia de plataformas a alturas variadas
    # Patrón: (col_start, col_end, row)
    secuencia = [
        # Bloque de entrada suave
        (12, 16, 10), (18, 22,  9), (24, 27,  8),
        # Primera subida
        (29, 32,  7), (34, 37,  6), (39, 42,  5),
        # Cruce alto peligroso (gaps de 2)
        (44, 46,  5), (48, 50,  5), (52, 54,  5),
        # Descenso escalonado
        (56, 59,  6), (61, 64,  7), (66, 69,  8),
        # Zona media — plataformas alternas
        (71, 74,  9), (73, 76,  7), (78, 81,  5),
        (80, 83,  8), (85, 88,  6), (87, 90,  9),
        # Segunda subida agresiva
        (92, 94,  8), (95, 97,  6), (98,100,  4),
        (101,103, 5), (104,106, 7), (107,109, 9),
        # Plataformas doble salto obligatorio
        (111,113, 7), (115,117, 5), (119,121, 7),
        (123,125, 9), (127,129, 7), (131,133, 5),
        # Final — carrera de plataformas
        (135,138, 8), (140,143, 7), (145,148, 6),
        (150,153, 7), (155,158, 8),
        # Isla final (más ancha para la flag)
        (159, C, 10),
    ]

    for (cs, ce, row) in secuencia:
        for c in range(cs, min(ce, C)):
            if 0 <= row < 13:
                G[row][c] = PLATFORM

    # Algunas plataformas clave son SOLID (permiten pararse con más seguridad)
    for (cs, ce, row) in [(0,10,11),(71,76,9),(92,94,8),(159,C,10)]:
        for c in range(cs, min(ce, C)):
            if 0 <= row < 13:
                G[row][c] = SOLID

    return G


# Mapa de índice → función generadora
LEVEL_GRIDS = {
    0: make_level_1_grid,
    1: make_level_2_grid,
    2: make_level_3_grid,
    3: make_level_4_grid,
    4: make_level_5_grid,
}


# ─────────────────────────────────────────────────────────────────
#  FACTORY — crear TileMap para un nivel dado
# ─────────────────────────────────────────────────────────────────
def make_tilemap(level_idx: int,
                 tileset_path: str = "Tiles.png",
                 bg_path: str | None = None) -> TileMap:
    """
    Crea y devuelve un TileMap listo para usar dado el índice de nivel.

    Uso en Level.__init__:
        self.tilemap = make_tilemap(idx, tileset_path)
        solid, plats = self.tilemap.get_all_collision_rects()
        self.platforms = plats   # one-way
        self.ground_y  = self.tilemap.ground_y

    Uso en Level._draw_scene:
        self.tilemap.draw(surface, cam.x)
    """
    grid_fn = LEVEL_GRIDS.get(level_idx, make_level_1_grid)
    grid    = grid_fn()
    return TileMap(grid,
                   tileset_path=tileset_path,
                   tile_size=TILE,
                   bg_tileset_path=bg_path)


# ─────────────────────────────────────────────────────────────────
#  PARCHE PARA Level — integración mínima con el código existente
# ─────────────────────────────────────────────────────────────────
#
#  Para integrar TileMap en el Level.py existente, aplica estos
#  cambios (ya incluye compatibilidad total con Player y Enemy):
#
#  En Level.__init__() añadir/reemplazar:
#  ─────────────────────────────────────────────
#  base_dir = os.path.dirname(os.path.abspath(__file__))
#  ts_path  = os.path.join(base_dir, "Tiles.png")
#  self.tilemap = make_tilemap(idx, ts_path)
#  # Sustituye platforms y ground_y
#  self.platforms = self.tilemap.get_platform_rects()
#  self.ground_y  = self.tilemap.ground_y
#  # Los solid rects van a Player y Enemy directamente
#  self._solid_rects = self.tilemap.get_solid_rects()
#
#  En Level.update() en la parte de Player y Enemy:
#  ─────────────────────────────────────────────
#  # Player ya recibe self.platforms (one-way) y ground_y
#  # pero ahora también necesita los solid rects para no atravesar bloques.
#  # Reemplazar la llamada a p.update():
#
#  vis_solid = self.tilemap.get_visible_solid_rects(self.camera.x)
#  vis_plat  = self.tilemap.get_visible_platform_rects(self.camera.x)
#
#  p.update(vis_plat, self.tilemap.ground_y, self.world_w, self.flag_rect,
#           solid_rects=vis_solid)
#  # (requiere que Player.update acepte solid_rects, ver PlayerTileCompat abajo)
#
#  En Level._draw_scene() reemplazar el bloque de plataformas:
#  ─────────────────────────────────────────────
#  self.tilemap.draw(surface, cam.x)
#  # (ELIMINAR los bloques pygame.draw.rect de tiles y plataformas)
#
# ─────────────────────────────────────────────────────────────────


class PlayerTileCompat:
    """
    Mixin/parche para añadir colisión con SOLID tiles al Player existente.
    No reemplaza Player: lo envuelve o se usa con herencia.

    El Player original solo colisiona con platforms (one-way) y ground_y.
    Con TileMap, los bloques SOLID también son paredes laterales y techo.

    Uso como función standalone (sin modificar Player):
        apply_solid_collisions(player, solid_rects)
    """

    @staticmethod
    def apply_solid_collisions(player, solid_rects: list[pygame.Rect]):
        """
        Aplica colisiones del jugador con rects sólidos (paredes y techo).
        Llamar DESPUÉS de player.update() en Level.update().

        Resuelve colisiones separadamente en X e Y para evitar
        el clipping diagonal (técnica estándar AABB split-axis).
        """
        p_rect = player.get_rect()

        for sr in solid_rects:
            if not p_rect.colliderect(sr):
                continue

            # ── Colisión vertical ─────────────────────────────────
            # Desde arriba (aterrizaje)
            if player.vy > 0 and p_rect.bottom > sr.top and \
               p_rect.top < sr.top:
                player.wy       = sr.top - player.H
                player.vy       = 0
                player.on_ground = True
                player.jumps_left = 2
                p_rect = player.get_rect()   # actualizar rect

            # Desde abajo (golpe de techo)
            elif player.vy < 0 and p_rect.top < sr.bottom and \
                 p_rect.bottom > sr.bottom:
                player.wy = sr.bottom
                player.vy = 0
                p_rect = player.get_rect()

        # ── Segunda pasada: colisiones horizontales ───────────────
        p_rect = player.get_rect()
        for sr in solid_rects:
            if not p_rect.colliderect(sr):
                continue
            if player.vx > 0 and p_rect.right > sr.left and \
               p_rect.left < sr.left:
                player.wx = sr.left - player.W
                p_rect = player.get_rect()
            elif player.vx < 0 and p_rect.left < sr.right and \
                 p_rect.right > sr.right:
                player.wx = sr.right
                p_rect = player.get_rect()


# ─────────────────────────────────────────────────────────────────
#  INTEGRACIÓN COMPLETA — clase Level lista para reemplazar la original
#  (versión con TileMap integrado, mantiene API pública igual)
# ─────────────────────────────────────────────────────────────────
#
#  NOTA: Este es el código de integración a copiar en tu archivo principal.
#  Busca el comentario "# TILEMAP_INTEGRATION" para saber dónde va cada bloque.
#


INTEGRATION_GUIDE = """
══════════════════════════════════════════════════════════════════
  GUÍA DE INTEGRACIÓN DE TILEMAP EN Level
══════════════════════════════════════════════════════════════════

PASO 1 — En el archivo principal, añadir al inicio:
──────────────────────────────────────────────────
    from tilemap import TileMap, make_tilemap, PlayerTileCompat, TILE

PASO 2 — En Level.__init__(), después de self.platforms = [...]:
──────────────────────────────────────────────────
    # Crear TileMap para el nivel
    base_dir = os.path.dirname(os.path.abspath(__file__))
    ts_path  = os.path.join(base_dir, "Tiles.png")

    self.tilemap      = make_tilemap(idx, ts_path)
    self.platforms    = self.tilemap.get_platform_rects()   # one-way
    self.ground_y     = self.tilemap.ground_y               # suelo
    self.world_w      = self.tilemap.world_w                # ancho mundo

PASO 3 — En Level.update(), reemplazar la llamada a p.update():
──────────────────────────────────────────────────
    # Obtener solo rects visibles (optimización)
    vis_solid = self.tilemap.get_visible_solid_rects(self.camera.x)
    vis_plat  = self.tilemap.get_visible_platform_rects(self.camera.x)

    p.update(vis_plat, self.tilemap.ground_y, self.world_w, self.flag_rect)
    PlayerTileCompat.apply_solid_collisions(p, vis_solid)

    # Para enemigos, misma lógica:
    for e in self.enemies:
        e.update(vis_plat, self.tilemap.ground_y,
                 p.wx, p.wy, self.fireballs, self.world_w)

PASO 4 — En Level._draw_scene(), reemplazar el renderizado de tiles:
──────────────────────────────────────────────────
    # ELIMINAR los bloques pygame.draw.rect de suelo y plataformas
    # AÑADIR en su lugar (después del blit del fondo):
    self.tilemap.draw(surface, cam.x, view_w=SW, view_h=SH)

    # El resto del draw (flag, enemigos, jugador, partículas) se mantiene igual.

══════════════════════════════════════════════════════════════════
"""


if __name__ == "__main__":
    # ── Test standalone — verifica que todo carga correctamente ───
    pygame.init()
    screen = pygame.display.set_mode((1000, 600))
    pygame.display.set_caption("TileMap Test — El Pepis")
    clock  = pygame.time.Clock()

    print("Cargando TileMap de prueba...")
    import os
    base    = os.path.dirname(os.path.abspath(__file__))
    ts_path = os.path.join(base, "Tiles.png")

    tm = make_tilemap(0, ts_path)
    print(f"TileMap creado: {tm.cols}x{tm.rows} tiles, "
          f"{len(tm.get_solid_rects())} sólidos, "
          f"{len(tm.get_platform_rects())} plataformas")
    print(f"ground_y = {tm.ground_y}")
    print(INTEGRATION_GUIDE)

    cam_x   = 0.0
    running = True

    while running:
        clock.tick(60)
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False

        keys = pygame.key.get_pressed()
        if keys[pygame.K_RIGHT]: cam_x += 6
        if keys[pygame.K_LEFT]:  cam_x  = max(0, cam_x - 6)

        screen.fill((18, 20, 50))
        tm.draw(screen, cam_x, view_w=1000, view_h=600)

        # Dibujar rects de colisión en modo debug
        for r in tm.get_visible_solid_rects(cam_x):
            pygame.draw.rect(screen, (255, 0, 0),
                             pygame.Rect(r.x - int(cam_x), r.y, r.w, r.h), 1)
        for r in tm.get_visible_platform_rects(cam_x):
            pygame.draw.rect(screen, (0, 255, 100),
                             pygame.Rect(r.x - int(cam_x), r.y, r.w, r.h), 2)

        font = pygame.font.SysFont("consolas", 16)
        screen.blit(font.render(
            f"cam_x={int(cam_x)}  ← → mover   ESC salir   "
            f"ROJO=solid  VERDE=plataform",
            True, (200, 200, 255)), (10, 10))

        pygame.display.flip()

    pygame.quit()
