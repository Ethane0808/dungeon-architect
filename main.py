# pyrefly: ignore[missing-import]
import pygame

def main() -> None:
    """啟動 Phase 1 視窗；匯入模組不初始化 pygame。"""
    pygame.init()
    try:
        screen = pygame.display.set_mode((800, 600))
        pygame.display.set_caption("Dungeon Architect")

        clock = pygame.time.Clock()
        running = True

        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

            screen.fill((30, 35, 45))
            pygame.display.flip()
            clock.tick(60)
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
