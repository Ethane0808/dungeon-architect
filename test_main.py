# pyrefly: ignore[missing-import]
import pygame

def main() -> None:
    """手動視窗測試；pytest 收集本模組時不開啟視窗。"""
    pygame.init()
    try:
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
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
