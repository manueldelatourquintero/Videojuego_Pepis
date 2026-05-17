# ══════════════════════════════════════════════════════════════════
#  level_tilemap_patch.py
#  Parche listo para copiar sobre la clase Level del juego original.
#  Solo modifica Level.__init__, Level.update y Level._draw_scene.
#  Todo lo demás (Player, Enemy, Camera, etc.) se mantiene igual.
# ══════════════════════════════════════════════════════════════════

# ─── AÑADIR al inicio del archivo principal ────────────────────────
# from tilemap import make_tilemap, PlayerTileCompat, TILE as TILE_SIZE
# ──────────────────────────────────────────────────────────────────


class Level:   # VERSION COMPLETA CON TILEMAP — reemplaza la original
    def __init__(self, idx, img_idle=None, img_attack=None,
                 player_img=None, sounds=None):
        import os, random, pygame
        from tilemap import make_tilemap, PlayerTileCompat

        data = build_level(idx)         # build_level original sigue siendo útil
        self.idx       = idx
        self.quiz      = data["quiz"]
        self.name      = data["name"]
        self.c_sky1, self.c_sky2, self.c_tile, self.c_plat = data["colors"]
        self.sounds    = sounds

        # ── TileMap (sustituye platforms y ground_y) ──────────────
        base_dir  = os.path.dirname(os.path.abspath(__file__))
        ts_path   = os.path.join(base_dir, "Tiles.png")
        bg_path   = os.path.join(base_dir, "Background_Props.png")

        self.tilemap   = make_tilemap(idx, ts_path,
                                      bg_path if os.path.exists(bg_path) else None)
        self.platforms = self.tilemap.get_platform_rects()   # one-way
        self.ground_y  = self.tilemap.ground_y
        self.world_w   = self.tilemap.world_w

        # ── Flag al final del mundo ───────────────────────────────
        self.flag_x    = self.world_w - 150
        self.flag_rect = pygame.Rect(self.flag_x,
                                     self.ground_y - TILE * 5,
                                     TILE // 2, TILE * 5)

        # ── Jugador ───────────────────────────────────────────────
        px, py = 80, self.ground_y - PLAYER_H
        self.player = Player(px, py, player_img)

        # ── Enemigos (posición relativa al world_w del tilemap) ───
        self.total_enemies  = data["enemy_count"]
        self.killed_enemies = 0

        section = self.world_w // (self.total_enemies + 1)
        enemy_positions = []
        for i in range(self.total_enemies):
            ex = section * (i + 1) + random.randint(-60, 60)
            ex = max(200, min(ex, self.world_w - 200))
            enemy_positions.append((ex, self.ground_y - ENEMY_H))

        self.enemies = [
            Enemy(ex, ey, img_idle, img_attack)
            for ex, ey in enemy_positions
        ]

        # ── Resto ────────────────────────────────────────────────
        self.fireballs = []
        self.particles = ParticlePool(300)
        self.camera    = Camera(self.world_w)
        self.shake     = ScreenShake()
        self.timer     = 0

        self.show_enemies_warning = 0
        self.bg_surf = self._build_bg()
        self._player_tile_compat = PlayerTileCompat()

    def _build_bg(self):
        """Gradiente de fondo de pantalla (sin tiles, eso lo hace tilemap.draw)."""
        import pygame
        surf = pygame.Surface((SW, SH))
        draw_grad_bg(surf, (0, 0, SW, self.ground_y), self.c_sky1, self.c_sky2)
        pygame.draw.rect(surf, C_GROUND,
                         (0, self.ground_y, SW, SH - self.ground_y))
        pygame.draw.line(surf, C_GLINE,
                         (0, self.ground_y), (SW, self.ground_y), 3)
        return surf

    def update(self, keys):
        """Retorna: 'playing' | 'dead' | 'win'"""
        from tilemap import PlayerTileCompat
        p   = self.player
        snd = self.sounds

        p_stomp_pre = p.get_stomp_rect()
        prev_bottom = p_stomp_pre.bottom

        p.handle_input(keys)

        # ── Colisiones con tiles visibles ─────────────────────────
        vis_solid = self.tilemap.get_visible_solid_rects(self.camera.x)
        vis_plat  = self.tilemap.get_visible_platform_rects(self.camera.x)

        # update usa plataformas one-way + ground_y (igual que antes)
        p.update(vis_plat, self.ground_y, self.world_w, self.flag_rect)

        # Aplica colisiones con bloques sólidos (paredes y techo)
        PlayerTileCompat.apply_solid_collisions(p, vis_solid)

        self.camera.follow(p.wx + p.W / 2)
        self.shake.update()
        self.timer += 1

        if self.show_enemies_warning > 0:
            self.show_enemies_warning -= 1

        # ── Actualizar enemigos ───────────────────────────────────
        for e in self.enemies:
            e.update(vis_plat, self.ground_y,
                     p.wx, p.wy, self.fireballs, self.world_w)
            if e.just_fired and snd:
                snd.play("shoot")

        # ── Colisiones jugador ↔ enemigos (igual que el original) ─
        p_rect  = p.get_rect()
        p_stomp = p.get_stomp_rect()

        for e in self.enemies:
            if not e.alive:
                continue
            e_rect = e.get_rect()
            if not p_rect.colliderect(e_rect):
                continue

            e_head = pygame.Rect(e_rect.left + 4, e_rect.top,
                                 e_rect.width - 8,
                                 int(e_rect.height * 0.35))
            e_body = pygame.Rect(e_rect.left + 2,
                                 e_rect.top + int(e_rect.height * 0.2),
                                 e_rect.width - 4,
                                 int(e_rect.height * 0.8))

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

        # ── Fireballs ─────────────────────────────────────────────
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

        # 2. TileMap (suelo + plataformas con sprites del tileset)
        #    Reemplaza COMPLETAMENTE los pygame.draw.rect de tiles/plataformas
        self.tilemap.draw(surface, cam.x, view_w=SW, view_h=SH)

        # 3. Flag (igual que el original)
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

        # 4. Enemigos, partículas, fireballs, jugador (sin cambios)
        for e in self.enemies:
            if cam.in_view(e.wx):
                e.draw(surface, cam)

        self.particles.draw(surface, cam.x)

        for fb in self.fireballs:
            if cam.in_view(fb.wx):
                fb.draw(surface, cam)

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
