import pygame
import sys
from src.visualiser.scene import GameScene
from src.core.gamestate import PublicGamestate
from src.core.data_classes import PlayerPublicInfo, Pot

FPS = 60

class Visualiser():
    def __init__(self, width:int=1080, height:int=720, title:str="Poker Tournament"):
        pygame.init()
        pygame.display.set_caption(title)
        self.screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
        self.scene = GameScene(self.screen)
        self.clock = pygame.time.Clock()

    def run(self):
        gamestate: PublicGamestate = PublicGamestate(
            round_number=1,
            player_public_infos=[PlayerPublicInfo(active=True, stack=1000, current_bet=0, busted=False, is_all_in=False) for _ in range(10)],
            button_position=0,
            community_cards=["Kh", "9d", "Ac"],
            total_pot=3292,
            pots=[Pot(amount=3292, eligible_players=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9])],
            blinds=(10, 20),
            blinds_schedule={},
            minimum_raise_amount=0,
            current_hand_history={},
            previous_hand_histories=[],
        )
        
        while True:
            events = pygame.event.get()
            for event in events:
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                    
                if event.type == pygame.VIDEORESIZE:
                    self.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                    self.scene.screen = self.screen
                    
            self.scene.update(gamestate)
            self.scene.handle_events(events)
            self.scene.draw()
            pygame.display.flip()
            self.clock.tick(FPS)
            
if __name__ == "__main__":
    visualiser = Visualiser()
    visualiser.run()