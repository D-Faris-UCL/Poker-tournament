import pygame
import sys
from scene import GameScene

FPS = 60

class Visualiser():
    def __init__(self, width:int=1080, height:int=720, title:str="Poker Tournament"):
        pygame.init()
        pygame.display.set_caption(title)
        self.screen = pygame.display.set_mode((width, height))
        self.scene = GameScene(self.screen)
        self.clock = pygame.time.Clock()

    def run(self):
        while True:
            events = pygame.event.get()
            for event in events:
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                    
            self.scene.handle_events(events)
            self.scene.update()
            self.scene.draw()
            pygame.display.flip()
            self.clock.tick(FPS)
            
if __name__ == "__main__":
    visualiser = Visualiser()
    visualiser.run()