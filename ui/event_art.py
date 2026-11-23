"""Small dungeon event sprites, drawn once on a pixel grid."""

import pygame
from math import cos, sin, tau


def event_effect(surface, rect, notice, age_ms, sprites):
    """Draw a bounded, deterministic burst without consuming gameplay randomness."""
    if notice.category == "neutral" or not 0 <= age_ms < 1100:
        return
    progress = age_ms / 1100
    effect = pygame.Surface((180, 180), pygame.SRCALPHA)
    center = pygame.Vector2(90, 90)
    icon = notice.icon or notice.category
    healing = notice.category in ("spring", "medkit")
    damage = notice.hp_delta < 0 or notice.supplies_delta < 0
    color = ((255, 114, 93) if damage else (108, 239, 211) if healing
             else (193, 155, 255) if notice.category == "relic"
             else (255, 218, 123) if notice.category in ("supply", "altar", "construction") or icon == "barbed-cache"
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
        if notice.category == "relic" and "relic" in sprites:
            relic = pygame.transform.scale(sprites["relic"], (54, 54))
            relic.set_alpha(alpha)
            effect.blit(relic, relic.get_rect(center=center))
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
        pygame.draw.rect(sprite, "#211d29", (4, 12, 16, 4))
        lid = pygame.Rect(3, 11 - lift, 18, 6)
        pygame.draw.rect(sprite, "#a57940", lid)
        pygame.draw.rect(sprite, "#f5cf7a", lid, 1)
        for x in (6, 16):
            pygame.draw.line(sprite, "#e5bc68", (x, lid.top), (x, lid.bottom - 1))
            pygame.draw.line(sprite, "#e5bc68", (x, 17), (x, 20))
        pygame.draw.rect(sprite, "#f5cf7a", (10, lid.bottom - 2, 4, 3))
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

    gem = canvas("relic")
    pygame.draw.polygon(gem, "#866bc1", [(12, 1), (20, 9), (16, 18), (11, 22), (4, 12), (5, 7)])
    pygame.draw.polygon(gem, "#d3b6ff", [(12, 2), (14, 8), (9, 14), (6, 8)])
    pygame.draw.line(gem, "#514079", (14, 9), (11, 21), 2)
    return sprites


def fit_sprites(sprites, size):
    frame = pygame.Rect(0, 0, size, size)
    return {name: pygame.transform.scale(sprite, sprite.get_rect().fit(frame).size)
            for name, sprite in sprites.items()}
