"""Small dungeon event sprites, drawn once on a pixel grid."""

import pygame


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
    pygame.draw.line(dart, shade, (3, 20), (19, 4), 4)
    pygame.draw.line(dart, silver, (4, 19), (18, 5), 2)
    pygame.draw.polygon(dart, "#e57b65", [(2, 16), (8, 14), (10, 17), (4, 22)])
    pygame.draw.polygon(dart, light, [(13, 5), (22, 2), (19, 11)])

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
