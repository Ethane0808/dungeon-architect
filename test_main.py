# pyrefly: ignore[missing-import]
import pygame

pygame.init()

screen = pygame.display.set_mode((800, 600))
pygame.display.set_caption("Pygame Window Test")

print("Window created successfully!")
print("Display driver:", pygame.display.get_driver())

clock = pygame.time.Clock()
running = True

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    screen.fill((50, 100, 180))
    pygame.display.flip()
    clock.tick(60)

pygame.quit()
