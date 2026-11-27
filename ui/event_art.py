"""Small dungeon event sprites, drawn once on a pixel grid."""

import pygame
from math import cos, sin, tau
from functools import lru_cache
from random import Random


def vine_spires_art(source, cell_size):
    """Set the spires into the existing floor, leaving the surrounding paving visible."""
    art = source.subsurface(source.get_bounding_rect(min_alpha=64)).copy()
    for y in range(art.get_height()):
        for x in range(art.get_width()):
            r, g, b, alpha = art.get_at((x, y))
            if not alpha:
                continue
            light = (3 * r + 6 * g + b) // 10
            if g > b and r > b:  # Olive vines, from shaded stems to sage-green tips.
                color = (14 + light * 49 // 100, 27 + light * 58 // 100, 22 + light * 35 // 100)
            else:  # Blue slate, in the same value range as the nearby stone passages.
                color = (13 + light * 62 // 100, 19 + light * 67 // 100, 26 + light * 70 // 100)
            art.set_at((x, y), (*color, alpha))

    tile = pygame.Surface((cell_size, cell_size), pygame.SRCALPHA)
    footprint = tile.get_rect().inflate(-20, -20)
    stone = art.get_rect().fit(footprint)
    stone.center = (tile.get_width() // 2, tile.get_height() // 2 + 2)
    for inset, opacity in ((0, 45), (3, 76), (6, 108)):
        shadow = pygame.Rect(stone.left - 2, stone.bottom - 13, stone.width + 5, 12)
        pygame.draw.ellipse(tile, (11, 17, 22, opacity), shadow.inflate(-2 * inset, -inset))
    tile.blit(pygame.transform.scale(art, stone.size), stone)
    return tile


def traveler_art(explorer):
    """Dress the original explorer in a travel cloak, preserving its pose and anchor."""
    cloak = explorer.copy()
    for y in range(cloak.get_height()):
        for x in range(cloak.get_width()):
            r, g, b, alpha = explorer.get_at((x, y))
            if not alpha:
                continue
            if r > g > b:  # Ochre fabric becomes teal, retaining the painted folds.
                cloak.set_at((x, y), (r * 2 // 5, g * 9 // 10, g, alpha))
            elif y < 11 and b > r and r > 65:  # Warm linen hood.
                cloak.set_at((x, y), (g, g * 4 // 5, r * 3 // 5, alpha))

    # The satchel and hanging lantern follow the shoulders and hand of the 20x25 sprite.
    pygame.draw.line(cloak, "#9e754a", (14, 8), (6, 16))
    pygame.draw.rect(cloak, "#654838", (5, 15, 5, 4), border_radius=1)
    pygame.draw.line(cloak, "#c79b62", (5, 16), (9, 16))
    pygame.draw.lines(cloak, "#b48b55", False, [(1, 15), (2, 13), (3, 13), (4, 15)])
    pygame.draw.rect(cloak, "#654838", (0, 15, 6, 6), border_radius=1)
    pygame.draw.rect(cloak, "#ffc460", (1, 16, 4, 3))
    cloak.set_at((2, 17), "#fff1a3")
    pygame.draw.line(cloak, "#c29253", (1, 19), (4, 19))

    frames = []
    lights = []
    for phase in range(24):
        angle = phase * tau / 24
        wave = .75 * sin(angle) + .25 * sin(3 * angle + .5)
        frame = cloak.copy()
        frame.set_at((3, 17), "#fff1a3" if wave > 0 else "#ffbf5a")
        frame.set_at((2, 16), "#fff6c7" if wave > .35 else "#ffd17b")
        # Cast light onto the pavement separately so the traveler keeps its native bounds.
        light = pygame.Surface((64, 60), pygame.SRCALPHA)
        lamp_x, lamp_y = (light.get_width() - cloak.get_width()) // 2 + 3, 35
        for radius in range(22, 0, -1):
            strength = (1 - radius / 23) ** 1.6
            pygame.draw.circle(light, (255, 182, 82, round((145 + 20 * wave) * strength)),
                               (lamp_x, lamp_y), radius)
        pool = pygame.Surface((56, 18), pygame.SRCALPHA)
        for inset in range(8):
            pygame.draw.ellipse(pool, (255, 181, 82, round((5 + 5 * inset) * (1 + .15 * wave))),
                                pool.get_rect().inflate(-4 * inset, -2 * inset))
        light.blit(pool, (0, 40))
        for offset, drift in ((0, -1), (11, 1)):
            age = (phase + offset) % 24
            opacity = round(175 * sin(age * tau / 48))
            x = lamp_x - 3 + round(drift * age / 6 + 1.5 * sin(age / 4))
            pygame.draw.line(light, (255, 207, 117, opacity), (x, lamp_y - 3 - age),
                             (x, lamp_y - 2 - age))
        frames.append(frame)
        lights.append(light)
    return cloak, tuple(frames), tuple(lights)


@lru_cache(maxsize=1)
def mist_texture():
    """Tileable pixel mist, shaded in the blue-violet tones of the ruin."""
    rng = Random("dungeon-mist-art")
    clouds = pygame.Surface((128, 80))
    palette = ("#191b2b", "#242737", "#2d3043", "#393d50", "#474e62", "#586477")
    layers = []
    for cols, rows in ((4, 6), (8, 12), (16, 24)):
        layers.append([[rng.random() for _ in range(cols)] for _ in range(rows)])
    for y in range(clouds.get_height()):
        for x in range(128):
            density = 0
            for grid, weight in zip(layers, (.6, .28, .12)):
                rows, cols = len(grid), len(grid[0])
                u, v = x * cols / 128, y * rows / 80
                i, j = int(u), int(v)
                a, b = u-i, v-j
                a, b = a*a*(3-2*a), b*b*(3-2*b)
                top, bottom = grid[j], grid[(j+1) % rows]
                k = (i+1) % cols
                density += weight * ((1-b)*(top[i]*(1-a)+top[k]*a) + b*(bottom[i]*(1-a)+bottom[k]*a))
            ribbon = .5 + .5*cos(tau*(y/80*3 + density + .14*sin(tau*x/128)))
            # Restrict dithering to the transition between two flat shades.
            tone = (density * .66 + ribbon**3 * .34) * len(palette)
            if (x + y) % 2 == 0:
                tone += .13
            clouds.set_at((x, y), palette[min(int(tone), len(palette)-1)])
    tile = pygame.transform.scale(clouds, (384, 240))
    atlas = pygame.Surface((768, 480))
    for x in (0, 384):
        for y in (0, 240):
            atlas.blit(tile, (x, y))
    return atlas


def portal_effect(surface, rect, now_ms, unlock_age_ms=None):
    """Draw the open portal's glow and motes, with a burst on unlock."""
    effect = pygame.Surface((72, 72), pygame.SRCALPHA)
    center = pygame.Vector2(36, 36)
    phase = now_ms / 1600 * tau
    pulse = (1 + sin(phase)) / 2
    pygame.draw.ellipse(effect, (74, 248, 146, round(70 + 70 * pulse)), (18, 12, 36, 46), 2)
    for index in range(9):
        age = (now_ms / 1450 + index / 9) % 1
        x = 36 + sin(age * tau + index * 2.4) * (17 + index % 4 * 3)
        y = 57 - 47 * age
        opacity = round(230 * sin(age * tau / 2))
        pygame.draw.circle(effect, (150, 255, 191, opacity), (x, y), 1 + index % 2)
    if unlock_age_ms is not None and 0 <= unlock_age_ms < 950:
        progress = unlock_age_ms / 950
        color = (133, 255, 177, round(240 * (1 - progress)))
        radius = 13 + progress * 20
        pygame.draw.circle(effect, color, center, round(radius), 2)
        for index in range(12):
            angle = index * tau / 12
            point = center + pygame.Vector2(cos(angle), sin(angle)) * radius
            pygame.draw.circle(effect, color, point, 2)
    surface.blit(effect, effect.get_rect(center=rect.center))


def event_effect(surface, rect, notice, age_ms, sprites):
    """Draw a bounded, deterministic burst without consuming gameplay randomness."""
    if notice.category == "neutral" or not 0 <= age_ms < 1100:
        return
    progress = age_ms / 1100
    effect = pygame.Surface((180, 180), pygame.SRCALPHA)
    center = pygame.Vector2(90, 90)
    icon = notice.icon or notice.category
    healing = notice.category in ("spring", "medkit") or icon == "herb"
    damage = notice.hp_delta < 0 or notice.supplies_delta < 0
    color = ((255, 114, 93) if damage else (108, 239, 211) if healing
             else (193, 155, 255) if notice.category in ("relic", "altar")
             else (255, 218, 123) if notice.category in ("supply", "construction") or icon == "barbed-cache"
             else (145, 190, 220))
    alpha = round(250 * (1 - progress))
    radius = round(42 + 48 * progress)
    pygame.draw.circle(effect, (*color, round(alpha * .34)), center, radius)
    pygame.draw.circle(effect, (*color, alpha), center, radius, 5)
    pygame.draw.circle(effect, (255, 246, 213, round(alpha * .65)), center, max(5, 18 - round(progress * 10)), 3)
    for index in range(16):
        angle = index * tau / 16 + .35
        distance = 20 + progress * (44 + index % 4 * 8)
        point = center + pygame.Vector2(cos(angle), sin(angle)) * distance
        pygame.draw.circle(effect, (*color, alpha), point, max(2, 6 - int(progress * 4)))

    if icon == "dart":
        flight = min(1, age_ms / 340)
        tip = center + pygame.Vector2(-64 + 83 * flight, 40 - 52 * flight)
        pygame.draw.line(effect, (255, 238, 181, alpha), tip + (-42, 27), tip, 8)
        pygame.draw.line(effect, (*color, alpha), tip + (-60, 38), tip + (-10, 7), 3)
        arrow = pygame.transform.scale(sprites["dart"], (58, 58))
        arrow.set_alpha(alpha)
        effect.blit(arrow, arrow.get_rect(center=tip))
    elif icon == "falling-stone":
        for index in range(3):
            fall = min(1, max(0, (age_ms - index * 85) / 300))
            stone = pygame.transform.rotate(pygame.transform.scale(sprites[icon], (46, 46)), index * 23)
            stone.set_alpha(alpha)
            point = (65 + index * 24, 25 + 70 * fall)
            effect.blit(stone, stone.get_rect(center=point))
        impact = min(1, max(0, (age_ms - 260) / 240))
        if impact:
            pygame.draw.circle(effect, (*color, round(alpha * impact)), (90, 112), 34, 5)
            for offset in (-36, -18, 18, 36):
                pygame.draw.line(effect, (*color, alpha), (90, 112), (90 + offset, 126 + abs(offset) // 5), 4)
    elif icon in ("thorn", "barbed-cache"):
        extent = min(1, age_ms / 250)
        for index in range(4):
            angle = tau * index / 4 + .4
            start = center + pygame.Vector2(cos(angle), sin(angle)) * 44
            end = start.lerp(center, extent * .7)
            pygame.draw.line(effect, (*color, alpha), start, end, 7)
            point = start.lerp(end, .55)
            pygame.draw.polygon(effect, (*color, alpha), [point, point + (8, -9), point + (7, 5)])
        if icon == "barbed-cache":
            cache = pygame.transform.scale(sprites[icon], (54, 54))
            cache.set_alpha(alpha)
            effect.blit(cache, cache.get_rect(center=center))
    elif icon == "herb":
        sprig = pygame.transform.scale(sprites[icon], (50, 50))
        sprig.set_alpha(alpha)
        effect.blit(sprig, sprig.get_rect(center=(90, 94 - round(progress * 18))))
    elif notice.category == "supply":
        chest = pygame.transform.scale(sprites["supply"], (54, 54))
        chest.set_alpha(alpha)
        effect.blit(chest, chest.get_rect(center=center))
        for angle in range(0, 360, 45):
            ray = pygame.Vector2(0, -1).rotate(angle)
            pygame.draw.line(effect, (*color, alpha), center + ray * 34, center + ray * 55, 5)
    elif healing:
        for offset in (-22, 0, 22):
            x, y = 90 + offset, 104 - int(progress * 45) + abs(offset) // 2
            pygame.draw.line(effect, (*color, alpha), (x - 6, y), (x + 6, y), 4)
            pygame.draw.line(effect, (*color, alpha), (x, y - 6), (x, y + 6), 4)
    elif notice.category in ("relic", "altar"):
        points = [center + pygame.Vector2(cos(tau * i / 4 + progress), sin(tau * i / 4 + progress)) * 29
                  for i in range(4)]
        pygame.draw.polygon(effect, (*color, alpha), points, 3)
        pygame.draw.line(effect, (*color, alpha), (90, 35), (90, 125), 3)
        if notice.category == "altar":
            for index in range(10):
                travel = progress * (29 + index % 4 * 8)
                x = 90 + sin(index * 2.4 + progress * tau) * (10 + index % 3 * 5)
                y = 97 - travel - index * 2
                pygame.draw.polygon(effect, (229, 197, 255, alpha),
                                    [(x, y - 4), (x + 2, y), (x, y + 4), (x - 2, y)])
        if notice.category == "relic" and "relic" in sprites:
            relic = pygame.transform.scale(sprites["relic"], (54, 54))
            relic.set_alpha(alpha)
            effect.blit(relic, relic.get_rect(center=center))
    elif icon in ("bell", "fog", "monster", "casino", "construction"):
        emblem = pygame.transform.scale(sprites[icon], (40, 40))
        if icon == "bell":
            emblem = pygame.transform.rotate(emblem, 14 * sin(progress * tau * 2))
        elif icon == "casino":
            emblem = pygame.transform.rotate(emblem, (1 - progress) * 24)
        elif icon == "fog":
            for i in range(3):
                x = 45 + int(12 * sin(progress * tau + i))
                pygame.draw.arc(effect, (185, 211, 237, alpha), (x, 60 + i * 15, 82, 18), 0, 3.1, 3)
        emblem.set_alpha(alpha)
        effect.blit(emblem, emblem.get_rect(center=(90, 90 - int(progress * 12))))
    elif notice.category == "guard":
        for offset in (-9, 9):
            pygame.draw.line(effect, (*color, alpha), (65 + offset, 65), (110 + offset, 115), 5)
    surface.blit(effect, effect.get_rect(center=rect.center))


def chest_frames():
    """Opening lid frames followed by a dim, visibly empty chest."""
    frames = []
    for lift in (0, 3, 6, 9, 9):
        sprite = pygame.Surface((24, 24), pygame.SRCALPHA)
        pygame.draw.rect(sprite, "#382a30", (2, 12, 20, 10))
        pygame.draw.rect(sprite, "#a57940", (3, 13, 18, 8))
        pygame.draw.rect(sprite, "#e5bc68", (3, 13, 18, 8), 1)
        pygame.draw.line(sprite, "#795337", (4, 18), (19, 18))
        pygame.draw.rect(sprite, "#211d29", (4, 12, 16, 4))
        lid = pygame.Rect(3, 11 - lift, 18, 6)
        pygame.draw.rect(sprite, "#a57940", lid)
        pygame.draw.rect(sprite, "#f5cf7a", lid, 1)
        pygame.draw.line(sprite, "#bc9255", (4, lid.top + 2), (19, lid.top + 2))
        for x in (6, 16):
            pygame.draw.line(sprite, "#e5bc68", (x, lid.top), (x, lid.bottom - 1))
            pygame.draw.line(sprite, "#e5bc68", (x, 17), (x, 20))
            sprite.set_at((x, 20), "#ffe0a2")
        pygame.draw.rect(sprite, "#f5cf7a", (10, lid.bottom - 2, 4, 3))
        sprite.set_at((12, lid.bottom - 1), "#694534")
        frames.append(sprite)
    frames[-1].fill((160, 160, 175, 255), special_flags=pygame.BLEND_RGBA_MULT)
    return tuple(frames)


def event_sprites(objects):
    stone = "#706d87"
    light = "#b6b4c9"
    shade = "#302c40"
    silver = "#d8e1ee"
    sprites = {}
    for name in ("supply", "danger"):
        sprite = objects[name]
        sprites[name] = sprite.subsurface(sprite.get_bounding_rect())

    def canvas(name):
        sprites[name] = pygame.Surface((24, 24), pygame.SRCALPHA)
        return sprites[name]

    dart = canvas("dart")
    pygame.draw.line(dart, "#211626", (3, 20), (19, 4), 6)
    pygame.draw.line(dart, "#ffca78", (3, 20), (19, 4), 3)
    pygame.draw.polygon(dart, "#ff795c", [(1, 17), (5, 12), (9, 15), (6, 21), (2, 23)])
    head = [(10, 6), (23, 0), (18, 14), (16, 8)]
    pygame.draw.polygon(dart, "#fff6cb", head)
    pygame.draw.polygon(dart, "#482f39", head, 1)

    slab = canvas("falling-stone")
    for x in (5, 11, 17):
        pygame.draw.line(slab, light, (x, 1), (x, 5), 1)
    pygame.draw.polygon(slab, stone, [(2, 10), (9, 6), (21, 9), (19, 18), (6, 21), (2, 17)])
    pygame.draw.lines(slab, light, False, [(2, 10), (9, 6), (21, 9)], 2)
    pygame.draw.lines(slab, shade, False, [(12, 8), (9, 13), (13, 14), (10, 18)], 2)

    thorn = canvas("thorn")
    stem = [(3, 21), (8, 16), (8, 12), (13, 8), (17, 9), (21, 5)]
    pygame.draw.lines(thorn, "#272034", False, stem, 6)
    pygame.draw.lines(thorn, "#6fa75b", False, stem, 4)
    for base, tip, end in [((6, 17), (1, 8), (9, 13)),
                           ((9, 12), (18, 19), (13, 9)),
                           ((13, 8), (11, 0), (17, 9))]:
        pygame.draw.polygon(thorn, "#de8078", [base, tip, end])
        pygame.draw.line(thorn, "#ffe0ad", base, tip, 2)

    cache = canvas("barbed-cache")
    cache.blit(pygame.transform.scale(sprites["supply"], (21, 17)), (1, 4))
    for a, b in [((2, 4), (21, 20)), ((2, 20), (21, 4))]:
        pygame.draw.line(cache, shade, a, b, 3)
        pygame.draw.line(cache, silver, a, b)
    pygame.draw.line(cache, silver, (15, 12), (19, 14), 2)

    herb = canvas("herb")
    pygame.draw.polygon(herb, "#73b98b", [(3, 6), (11, 9), (13, 16), (6, 14)])
    pygame.draw.polygon(herb, "#b3de94", [(12, 12), (14, 5), (22, 2), (20, 9)])
    pygame.draw.lines(herb, "#478069", False, [(7, 22), (12, 15), (15, 10), (19, 6)], 2)
    pygame.draw.line(herb, "#ebcf87", (7, 16), (13, 20), 2)

    gem = canvas("relic")
    pygame.draw.polygon(gem, "#866bc1", [(12, 1), (20, 9), (16, 18), (11, 22), (4, 12), (5, 7)])
    pygame.draw.polygon(gem, "#d3b6ff", [(12, 2), (14, 8), (9, 14), (6, 8)])
    pygame.draw.line(gem, "#514079", (14, 9), (11, 21), 2)

    bell = canvas("bell")
    pygame.draw.circle(bell, "#e6b660", (12, 4), 3, 2)
    pygame.draw.circle(bell, "#ffdb90", (12, 19), 3)
    pygame.draw.polygon(bell, "#9c6139", [(2,18),(5,14),(6,8),(10,5),(15,5),(18,9),(19,14),(22,18),(22,20),(2,20)])
    pygame.draw.polygon(bell, "#edb85e", [(5,16),(8,13),(8,9),(11,7),(14,7),(16,11),(17,16)])
    pygame.draw.line(bell, "#fff0b5", (10,8), (8,13), 2)
    pygame.draw.line(bell, "#ffd88b", (3,18), (20,18), 2)

    fog = canvas("fog")
    for x, y, radius in ((6,12,4),(11,9,6),(17,12,5)):
        pygame.draw.circle(fog, "#718da6", (x,y), radius)
    pygame.draw.arc(fog, "#dbedf5", (6,3,12,12), .4, 2.9, 2)
    for x, y, w in ((2,15,16),(7,18,15),(3,21,10)):
        pygame.draw.line(fog, "#c1d9dd", (x,y), (x+w,y), 2)

    beast = canvas("monster")
    pygame.draw.polygon(beast, "#ad6470", [(1,2),(8,7),(15,7),(22,2),(20,16),(12,22),(4,17)])
    for x in (4, 15):
        pygame.draw.polygon(beast, "#ffe4ad", [(x,12),(x+5,13),(x+3,15)])
    pygame.draw.polygon(beast, "#472e45", [(8,17),(16,17),(12,21)])
    pygame.draw.line(beast, "#e5a19b", (3,5), (6,10), 2)
    pygame.draw.polygon(beast, "#73495c", [(20, 6), (17, 10), (13, 11), (14, 16), (19, 15)])
    pygame.draw.line(beast, "#ffe4ad", (15, 13), (18, 12))
    for x in (8, 15):
        pygame.draw.line(beast, "#dec6aa", (x, 17), (x, 19))

    table = canvas("casino")
    pygame.draw.ellipse(table, "#b38b52", (0,9,24,14))
    pygame.draw.ellipse(table, "#23685d", (1,8,22,12))
    pygame.draw.rect(table, "#bfa9ce", (4,3,10,14), border_radius=2)
    pygame.draw.rect(table, "#fff0d3", (10,6,10,14), border_radius=2)
    pygame.draw.polygon(table, "#ad475c", [(15,8),(18,12),(15,16),(12,12)])

    well = canvas("spring")
    pygame.draw.ellipse(well, "#505362", (1,8,22,14))
    pygame.draw.ellipse(well, "#aca7a0", (1,5,22,13))
    pygame.draw.ellipse(well, "#253f52", (4,7,16,8))
    pygame.draw.ellipse(well, "#58bfb9", (6,9,12,5))
    pygame.draw.line(well, "#c1f5dd", (8,10), (12,10))
    for x in (5,13,20):
        pygame.draw.line(well, "#333547", (x,17), (x,19))

    quiet = canvas("neutral")
    for x,y in ((2,5),(12,5)):
        pygame.draw.polygon(quiet, "#a1b5c3", [(x,y),(x+9,y+4),(x+8,y+10),(x+3,y+7)])
    pygame.draw.line(quiet, "#dfd3ba", (12,9), (12,17), 2)

    for name, asset in (("guard", "patrol-guard"), ("construction", "chisel"), ("medkit", "health")):
        sprite = objects[asset]
        sprites[name] = sprite.subsurface(sprite.get_bounding_rect())
    return sprites


def fit_sprites(sprites, size):
    frame = pygame.Rect(0, 0, size, size)
    return {name: pygame.transform.scale(sprite, sprite.get_rect().fit(frame).size)
            for name, sprite in sprites.items()}
