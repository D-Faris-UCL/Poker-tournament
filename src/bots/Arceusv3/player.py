import itertools
from math import comb
import math

from collections import Counter

from typing import Tuple, List
import torch
from torch.distributions.categorical import Categorical
from src.core.player import Player
from src.core.gamestate import PublicGamestate
from src.helpers.hand_judge import HandJudge
from src.helpers.player_judge import PlayerJudge

from .player_stats import calculate_player_stats

RANK_TO_INT = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
               'T': 10, '10': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}

INT_TO_RANK = {2:'2', 3:'3', 4:'4', 5:'5', 6:'6', 7:'7', 8:'8', 9:'9',
               10:'T', 11:'J', 12:'Q', 13:'K', 14:'A'}

HAND_WINRATE = {
            1: {'high_card': 1.0, 'one_pair': 1.0, 'two_pair': 1.0, 'three_of_a_kind': 1.0, 'straight': 1.0, 'flush': 1.0, 'full_house': 1.0, 'four_of_a_kind': 1.0, 'straight_flush': 1.0, 'royal_flush': 1.0},
            2: {'high_card': 0.339, 'one_pair': 0.658, 'two_pair': 0.858, 'three_of_a_kind': 0.846, 'straight': 0.965, 'flush': 0.985, 'full_house': 0.986, 'four_of_a_kind': 1.0, 'straight_flush': 1.0, 'royal_flush': 1.0},
            3: {'high_card': 0.094, 'one_pair': 0.425, 'two_pair': 0.673, 'three_of_a_kind': 0.693, 'straight': 0.919, 'flush': 0.934, 'full_house': 0.939, 'four_of_a_kind': 1.0, 'straight_flush': 0.995, 'royal_flush': 1.0},
            4: {'high_card': 0.027, 'one_pair': 0.299, 'two_pair': 0.538, 'three_of_a_kind': 0.589, 'straight': 0.878, 'flush': 0.89, 'full_house': 0.897, 'four_of_a_kind': 1.0, 'straight_flush': 1.0, 'royal_flush': 1.0},
            5: {'high_card': 0.008, 'one_pair': 0.223, 'two_pair': 0.434, 'three_of_a_kind': 0.512, 'straight': 0.843, 'flush': 0.856, 'full_house': 0.861, 'four_of_a_kind': 1.0, 'straight_flush': 0.997, 'royal_flush': 1.0},
            6: {'high_card': 0.003, 'one_pair': 0.174, 'two_pair': 0.356, 'three_of_a_kind': 0.462, 'straight': 0.815, 'flush': 0.827, 'full_house': 0.825, 'four_of_a_kind': 1.0, 'straight_flush': 1.0, 'royal_flush': 1.0},
            7: {'high_card': 0.001, 'one_pair': 0.136, 'two_pair': 0.293, 'three_of_a_kind': 0.418, 'straight': 0.785, 'flush': 0.795, 'full_house': 0.804, 'four_of_a_kind': 1.0, 'straight_flush': 0.986, 'royal_flush': 1.0},
            8: {'high_card': 0.0, 'one_pair': 0.109, 'two_pair': 0.244, 'three_of_a_kind': 0.383, 'straight': 0.764, 'flush': 0.771, 'full_house': 0.777, 'four_of_a_kind': 1.0, 'straight_flush': 0.996, 'royal_flush': 1.0},
            9: {'high_card': 0.0, 'one_pair': 0.088, 'two_pair': 0.205, 'three_of_a_kind': 0.35, 'straight': 0.74, 'flush': 0.751, 'full_house': 0.758, 'four_of_a_kind': 0.999, 'straight_flush': 0.997, 'royal_flush': 1.0}
            }


deterministic = False

class ArceusBotV3(Player):
    def __init__(self, player_index: int, model=None, model_path: str = 'src/bots/Arceusv3/best arceus.pt', device: str = 'cpu'):
        super().__init__(player_index)
        # Your initialization here (optional)
        # You can initialize strategies, load data, etc.
        self.preflop_stacks = [0]*9
        self.flop_initial_pot = 0
        self.flop_stacks = [0]*9
        self.turn_initial_pot = 0
        self.turn_stacks = [0]*9
        self.river_initial_pot = 0
        self.river_stacks = [0]*9
        self.last_seen_street = None
        self.player_stats = None

        self.current_hand_step_data = []

        self.device = device
        if model is not None:
            self.model = model
        elif model_path:
            from .model import PokerPPOAgent
            self.model = PokerPPOAgent()
            checkpoint = torch.load(model_path, map_location=device)
            self.model.load_state_dict(checkpoint['model_state_dict'])
            self.model.to(device)
            self.model.eval()

    def get_action(
        self,
        gamestate: PublicGamestate,
        hole_cards: Tuple[str, str]
    ) -> Tuple[str, int]:
        """Get action from PPO policy.

        Args:
            gamestate: Current public game state
            hole_cards: Player's hole cards

        Returns:
            (action_type, amount) tuple
        """
        # Detect street changes and save initial values
        current_street = gamestate.get_current_street()

        if current_street != self.last_seen_street:
            if current_street == 'preflop':
                # New hand - reset all values
                self.preflop_stacks = [0] * 9
                self.flop_initial_pot = 0
                self.flop_stacks = [0] * 9
                self.turn_initial_pot = 0
                self.turn_stacks = [0] * 9
                self.river_initial_pot = 0
                self.river_stacks = [0] * 9

                # Save initial preflop stacks
                for i in range(9):
                    self.preflop_stacks[i] = gamestate.player_public_infos[i].stack + gamestate.player_public_infos[i].current_bet

                self.player_stats = calculate_player_stats(gamestate.previous_hand_histories)

            elif current_street == 'flop':
                # Save initial flop pot and stacks
                self.flop_initial_pot = gamestate.total_pot
                for i in range(9):
                    self.flop_stacks[i] = gamestate.player_public_infos[i].stack + gamestate.player_public_infos[i].current_bet
                    self.flop_initial_pot -= gamestate.player_public_infos[i].current_bet

            elif current_street == 'turn':
                # Save initial turn pot and stacks
                self.turn_initial_pot = gamestate.total_pot
                for i in range(9):
                    self.turn_stacks[i] = gamestate.player_public_infos[i].stack + gamestate.player_public_infos[i].current_bet
                    self.turn_initial_pot -= gamestate.player_public_infos[i].current_bet


            elif current_street == 'river':
                # Save initial river pot and stacks
                self.river_initial_pot = gamestate.total_pot
                for i in range(9):
                    self.river_stacks[i] = gamestate.player_public_infos[i].stack + gamestate.player_public_infos[i].current_bet
                    self.river_initial_pot -= gamestate.player_public_infos[i].current_bet


            # Update last seen street
            self.last_seen_street = current_street


        # Encode state
        main_data, opp_data, hist_data, action_mask = self._encode_state(gamestate, hole_cards)

        # Get action from model
        with torch.no_grad():
            logits, value = self.model(main_data.to(self.device), opp_data.to(self.device), hist_data.to(self.device))

            # Mask illegal actions with a large negative number
            logits = torch.where(action_mask, logits, torch.tensor(-1e9).to(logits.device))

            if deterministic:
                # Tournament mode: always pick the highest probability action
                action_idx_tensor = logits.argmax(dim=-1)
                log_prob = torch.tensor(0.0).to(self.device) # Not needed for evaluation
            else:
                # Training mode: create a distribution and sample from it
                dist = Categorical(logits=logits)
                action_idx_tensor = dist.sample()
                log_prob = dist.log_prob(action_idx_tensor)

            # Extract the integer index
            action_idx = action_idx_tensor.item()

        # Convert to poker action
        action_type, amount = self._action_idx_to_poker_action(action_idx, gamestate, hole_cards)

        self.current_hand_step_data.append({
                        'main': main_data, 'opp': opp_data, 'hist': hist_data,
                        'action': action_idx, 'value': value.cpu(), 'log_prob': log_prob.cpu(), 
                        'mask': action_mask
                    })
        return action_type, amount

    def _encode_state(self, gamestate: PublicGamestate, hole_cards: Tuple[str, str]):
        ######################## MAIN DATA ###############################
        main_data = [0]*80
        # Table data
        main_data[0] = gamestate.total_pot / 750
        main_data[1] = gamestate.blinds[1] / 50
        main_data[2] = gamestate.get_bet_to_call() / 250
        main_data[3] = (gamestate.button_position-self.player_index)%9
        main_data[4] = gamestate.round_number / 100
        
        # Hole cards
        main_data[5] = (RANK_TO_INT[hole_cards[0][0]] - 1) / 13
        main_data[6] = (RANK_TO_INT[hole_cards[1][0]] - 1) / 13
        main_data[7] = 1 if hole_cards[0][1] == hole_cards[1][1] else 0
        main_data[8] = 1 if hole_cards[0][0] == hole_cards[1][0] else 0
        main_data[9] = self.straight_draw(gamestate.community_cards, hole_cards)
        main_data[10] = self.flush_draw(gamestate.community_cards, hole_cards)

        # Community cards
        main_data[11] = (RANK_TO_INT[gamestate.community_cards[0][0]] - 1) / 13 if len(gamestate.community_cards) >= 3 else -1
        main_data[12] = (RANK_TO_INT[gamestate.community_cards[1][0]] - 1) / 13 if len(gamestate.community_cards) >= 3 else -1
        main_data[13] = (RANK_TO_INT[gamestate.community_cards[2][0]] - 1) / 13 if len(gamestate.community_cards) >= 3 else -1
        main_data[14] = (RANK_TO_INT[gamestate.community_cards[3][0]] - 1) / 13 if len(gamestate.community_cards) >= 4 else -1
        main_data[15] = (RANK_TO_INT[gamestate.community_cards[4][0]] - 1) / 13 if len(gamestate.community_cards) >= 5 else -1
        main_data[16] = self.straight_probability(gamestate.community_cards)
        main_data[17] = self.flush_probability(gamestate.community_cards)
        main_data[18] = self.is_paired(gamestate.community_cards)
        main_data[19] = self.is_two_paired(gamestate.community_cards)
        main_data[20] = self.is_trips(gamestate.community_cards)
        main_data[21] = self.is_quads(gamestate.community_cards)

        # My player information
        main_data[22] = gamestate.player_public_infos[self.player_index].stack / 2000
        main_data[23] = gamestate.player_public_infos[self.player_index].current_bet / 250

        # Hand value
        evaluation = HandJudge.evaluate_hand(hole_cards, gamestate.community_cards)
        made_hand_one_hot_index = HandJudge.HAND_RANKINGS[evaluation[0]] - 1

        main_data[24 + made_hand_one_hot_index] = 1  # 24–33 (10 hand types)
        main_data[34] = (evaluation[1][0] - 1) / 13 if len(evaluation[1]) >= 1 else 0
        main_data[35] = (evaluation[1][1] - 1) / 13 if len(evaluation[1]) >= 2 else 0
        main_data[36] = (evaluation[1][2] - 1) / 13 if len(evaluation[1]) >= 3 else 0
        main_data[37] = (evaluation[1][3] - 1) / 13 if len(evaluation[1]) >= 4 else 0
        main_data[38] = (evaluation[1][4] - 1) / 13 if len(evaluation[1]) >= 5 else 0
        main_data[39] = HAND_WINRATE[gamestate.get_active_players_count()][evaluation[0]]

        # Opponent information (8 opponents × 5 values = 40, indices 40–79)
        for i in range(8):
            player_off = (self.player_index+1+i)%9
            main_data[40+i*5] = gamestate.player_public_infos[player_off].stack / 2000
            main_data[41+i*5] = gamestate.player_public_infos[player_off].current_bet / 250
            main_data[42+i*5] = 1 if gamestate.player_public_infos[player_off].active else 0
            main_data[43+i*5] = 1 if gamestate.player_public_infos[player_off].is_all_in else 0
            main_data[44+i*5] = 1 if gamestate.player_public_infos[player_off].current_bet == gamestate.get_bet_to_call() else 0
        
        ######################## OPPONENT STATISTIC DATA ###############################
        opp_data = [0] * 256
        STAT_TO_INDEX = {
            # Preflop Frequencies
            'VPIP %': 0,
            'PFR %': 1,
            'PFR/VPIP Ratio': 2,
            'Limp %': 3,
            'Fold to PFR %': 4,
            'Cold Call %': 5,
            'Isolation Raise %': 6,

            # Positional Preflop
            'Attempt to Steal (ATS) %': 7,
            'Fold to Steal %': 8,
            'BB Defend %': 9,
            'RFI (Early/Mid) %': 10,
            '3-Bet Preflop %': 11,
            'Fold to 3-Bet %': 12,

            # Common Flop Dynamics
            'Flop C-Bet %': 13,
            'Fold to Flop C-Bet %': 14,
            'Call Flop C-Bet %': 15,
            'Check-Fold Flop %': 16,
            'Aggression Factor (AF)': 17,

            # Advanced Post-Flop & Global Metrics
            'Flop Check-Raise %': 18,
            'Turn Check-Raise %': 19,
            'Flop Donk Bet %': 20,
            'Float Flop %': 21,
            'Fold to Flop Float %': 22,
            'Turn C-Bet (Double Barrel) %': 23,
            'Fold to Turn C-Bet %': 24,
            'River Bet Frequency %': 25,
            'Fold to River Bet %': 26,
            'Went to Showdown (WTSD) %': 27,
            'Aggression Frequency (AFq) %': 28,

            # Exploitative Stats
            'WTSD with Air %': 29,
            'Limp-Fold %': 30,
            'Squeeze %': 31
        }

        for i in range(8):
            player_off = (self.player_index+1+i)%9
            for stat, value in self.player_stats[player_off].items():
                if stat != 'Hands Played':
                    if value is None or math.isnan(value) or math.isinf(value):
                        clean_value = -1.0
                    else:
                        clean_value = float(value)
                    opp_data[STAT_TO_INDEX[stat] + i * 32] = clean_value
        
        ######################## BETTING HISTORY DATA ###############################
        hist_data = [0] * 430

        # ---- PREFLOP (indices 0–99) ----
        # [0]       button position
        # [1–9]     preflop stacks (9 players)
        # [10–99]   actions (9 players × 10 values)

        hist_data[0] = (gamestate.button_position - self.player_index) % 9
        for i in range(9):
            player_off = (self.player_index+i)%9
            hist_data[1 + i] = self.preflop_stacks[player_off] / 2000   # 1–9
        
        for i in range(9):
            player_off = (self.player_index+i)%9
            last_actions = self.get_last_two_actions(gamestate, 'preflop', player_off)
            hist_data[10 + i * 10] = last_actions[0][0]
            hist_data[11 + i * 10] = last_actions[0][1]
            hist_data[12 + i * 10] = last_actions[0][2]
            hist_data[13 + i * 10] = last_actions[0][3]
            hist_data[14 + i * 10] = last_actions[0][4]

            hist_data[15 + i * 10] = last_actions[1][0]
            hist_data[16 + i * 10] = last_actions[1][1]
            hist_data[17 + i * 10] = last_actions[1][2]
            hist_data[18 + i * 10] = last_actions[1][3]
            hist_data[19 + i * 10] = last_actions[1][4]
            # player=0: 10–19 ... player=8: 90–99

        # ---- FLOP (indices 100–218) ----
        # [100]     initial pot
        # [101–109] stacks (9 players)
        # [110–112] community card ranks
        # [113–118] board texture (6 values)
        # [119–208] actions (9 players × 10 values)

        community_cards = gamestate.current_hand_history['flop'].community_cards

        hist_data[100] = self.flop_initial_pot / 250
        for i in range(9):
            player_off = (self.player_index+i)%9
            hist_data[101 + i] = self.flop_stacks[player_off] / 2000   # 101–109
        hist_data[110] = (RANK_TO_INT[community_cards[0][0]] - 1) / 13 if len(community_cards) >= 3 else -1
        hist_data[111] = (RANK_TO_INT[community_cards[1][0]] - 1) / 13 if len(community_cards) >= 3 else -1
        hist_data[112] = (RANK_TO_INT[community_cards[2][0]] - 1) / 13 if len(community_cards) >= 3 else -1
        hist_data[113] = self.straight_probability(community_cards)
        hist_data[114] = self.flush_probability(community_cards)
        hist_data[115] = self.is_paired(community_cards)
        hist_data[116] = self.is_two_paired(community_cards)
        hist_data[117] = self.is_trips(community_cards)
        hist_data[118] = self.is_quads(community_cards)
        
        for i in range(9):
            player_off = (self.player_index+i)%9
            last_actions = self.get_last_two_actions(gamestate, 'flop', player_off)
            hist_data[119 + i * 10] = last_actions[0][0]
            hist_data[120 + i * 10] = last_actions[0][1]
            hist_data[121 + i * 10] = last_actions[0][2]
            hist_data[122 + i * 10] = last_actions[0][3]
            hist_data[123 + i * 10] = last_actions[0][4]

            hist_data[124 + i * 10] = last_actions[1][0]
            hist_data[125 + i * 10] = last_actions[1][1]
            hist_data[126 + i * 10] = last_actions[1][2]
            hist_data[127 + i * 10] = last_actions[1][3]
            hist_data[128 + i * 10] = last_actions[1][4]
            # player=0: 119–128 ... player=8: 199–208

        # ---- TURN (indices 209–318) ----
        # [209]     initial pot
        # [210–218] stacks (9 players)
        # [219–222] community card ranks
        # [223–228] board texture (6 values)
        # [229–318] actions (9 players × 10 values)

        community_cards = gamestate.current_hand_history['turn'].community_cards

        hist_data[209] = self.turn_initial_pot / 500
        for i in range(9):
            player_off = (self.player_index+i)%9
            hist_data[210 + i] = self.turn_stacks[player_off] / 2000   # 210–218
        hist_data[219] = (RANK_TO_INT[community_cards[0][0]] - 1) / 13 if len(community_cards) >= 4 else -1
        hist_data[220] = (RANK_TO_INT[community_cards[1][0]] - 1) / 13 if len(community_cards) >= 4 else -1
        hist_data[221] = (RANK_TO_INT[community_cards[2][0]] - 1) / 13 if len(community_cards) >= 4 else -1
        hist_data[222] = (RANK_TO_INT[community_cards[3][0]] - 1) / 13 if len(community_cards) >= 4 else -1
        hist_data[223] = self.straight_probability(community_cards)
        hist_data[224] = self.flush_probability(community_cards)
        hist_data[225] = self.is_paired(community_cards)
        hist_data[226] = self.is_two_paired(community_cards)
        hist_data[227] = self.is_trips(community_cards)
        hist_data[228] = self.is_quads(community_cards)
        
        for i in range(9):
            player_off = (self.player_index+i)%9
            last_actions = self.get_last_two_actions(gamestate, 'turn', player_off)

            hist_data[229 + i * 10] = last_actions[0][0]
            hist_data[230 + i * 10] = last_actions[0][1]
            hist_data[231 + i * 10] = last_actions[0][2]
            hist_data[232 + i * 10] = last_actions[0][3]
            hist_data[233 + i * 10] = last_actions[0][4]

            hist_data[234 + i * 10] = last_actions[1][0]
            hist_data[235 + i * 10] = last_actions[1][1]
            hist_data[236 + i * 10] = last_actions[1][2]
            hist_data[237 + i * 10] = last_actions[1][3]
            hist_data[238 + i * 10] = last_actions[1][4]
            # player=0: 229–238 ... player=8: 309–318

        # ---- RIVER (indices 319–429) ----
        # [319]     initial pot
        # [320–328] stacks (9 players)
        # [329–333] community card ranks
        # [334–339] board texture (6 values)
        # [340–429] actions (9 players × 10 values)

        community_cards = gamestate.current_hand_history['river'].community_cards

        hist_data[319] = self.river_initial_pot / 750
        for i in range(9):
            player_off = (self.player_index+i)%9
            hist_data[320 + i] = self.river_stacks[player_off] / 2000  # 320–328
        hist_data[329] = (RANK_TO_INT[community_cards[0][0]] - 1) / 13 if len(community_cards) >= 5 else -1
        hist_data[330] = (RANK_TO_INT[community_cards[1][0]] - 1) / 13 if len(community_cards) >= 5 else -1
        hist_data[331] = (RANK_TO_INT[community_cards[2][0]] - 1) / 13 if len(community_cards) >= 5 else -1
        hist_data[332] = (RANK_TO_INT[community_cards[3][0]] - 1) / 13 if len(community_cards) >= 5 else -1
        hist_data[333] = (RANK_TO_INT[community_cards[4][0]] - 1) / 13 if len(community_cards) >= 5 else -1
        hist_data[334] = self.straight_probability(community_cards)
        hist_data[335] = self.flush_probability(community_cards)
        hist_data[336] = self.is_paired(community_cards)
        hist_data[337] = self.is_two_paired(community_cards)
        hist_data[338] = self.is_trips(community_cards)
        hist_data[339] = self.is_quads(community_cards)
        
        for i in range(9):
            player_off = (self.player_index+i)%9
            last_actions = self.get_last_two_actions(gamestate, 'river', i)
            hist_data[340 + i * 10] = last_actions[0][0]
            hist_data[341 + i * 10] = last_actions[0][1]
            hist_data[342 + i * 10] = last_actions[0][2]
            hist_data[343 + i * 10] = last_actions[0][3]
            hist_data[344 + i * 10] = last_actions[0][4]

            hist_data[345 + i * 10] = last_actions[1][0]
            hist_data[346 + i * 10] = last_actions[1][1]
            hist_data[347 + i * 10] = last_actions[1][2]
            hist_data[348 + i * 10] = last_actions[1][3]
            hist_data[349 + i * 10] = last_actions[1][4]
            # player=0: 340–349 ... player=8: 420–429

        ######################## ACTION MASK ###############################
        # Get legal actions from PlayerJudge
        legal_actions = PlayerJudge.get_legal_actions(
            self.player_index,
            gamestate.player_public_infos,
            gamestate.get_bet_to_call(),
            gamestate.minimum_raise_amount
        )

        # Create action mask - all False initially
        action_mask = [False] * 10

        # Action space mapping:
        # 0: fold, 1: check, 2: call
        # 3: raise 0.25x pot, 4: raise 0.5x pot, 5: raise 0.75x pot
        # 6: raise 1x pot, 7: raise 1.5x pot, 8: raise 2x pot
        # 9: all-in

        pot_size = gamestate.total_pot + sum(p.current_bet for p in gamestate.player_public_infos)
        my_stack = gamestate.player_public_infos[self.player_index].stack
        my_current_bet = gamestate.player_public_infos[self.player_index].current_bet
        amount_to_call = gamestate.get_bet_to_call() - my_current_bet

        action_mask[0] = not legal_actions['check']

        # Check is legal when no bet to call
        action_mask[1] = legal_actions['check']

        # Call is legal when there's a bet to call
        action_mask[2] = legal_actions['call']

        # Raise actions (0.25x, 0.5x, 0.75x, 1x, 1.5x, 2x pot)
        if legal_actions['raise']:
            pot_fractions = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0]
            for idx, fraction in enumerate(pot_fractions):
                raise_amount = int(pot_size * fraction)
                if raise_amount + my_current_bet > gamestate.minimum_raise_amount and raise_amount < my_stack:
                    action_mask[3+idx] = True

        # All-in is legal when have chips
        action_mask[9] = legal_actions['all-in']

        # Ensure at least one action is legal (safety check)
        if not any(action_mask):
            action_mask[1] = True  # Default to check

        ######################## RETURN TENSORS ###############################
        # Convert to torch tensors with proper shapes
        main_tensor = torch.tensor([main_data], dtype=torch.float32)
        opp_tensor = torch.tensor([opp_data], dtype=torch.float32)
        hist_tensor = torch.tensor([hist_data], dtype=torch.float32)
        mask_tensor = torch.tensor([action_mask], dtype=torch.bool)

        return main_tensor, opp_tensor, hist_tensor, mask_tensor

    def straight_draw(self, community_cards, hole_cards):
        rank_to_int = {'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,
                    'T':10,'J':11,'Q':12,'K':13,'A':14}

        known = set()
        mask = 0
        for c in list(hole_cards) + community_cards:
            r, s = c[:-1].upper(), c[-1].lower()
            known.add(f"{r}{s}")
            v = rank_to_int[r]
            mask |= (1 << v) | ((1 << 1) if v == 14 else 0)

        has_str = lambda m: bool(m & (m>>1) & (m>>2) & (m>>3) & (m>>4))
        if has_str(mask):
            return 0

        outs = 0
        for rank in '23456789TJQKA':
            rm = (1 << rank_to_int[rank]) | ((1 << 1) if rank == 'A' else 0)
            if not has_str(mask | rm):
                continue
            outs += sum(1 for s in 'hdcs' if f"{rank}{s}" not in known)
        return outs/8

    def flush_draw(self, community_cards, hole_cards):
        suit_count = {}

        suit_count[hole_cards[0][1]] = suit_count.get(hole_cards[0][1], 0) + 1
        suit_count[hole_cards[1][1]] = suit_count.get(hole_cards[1][1], 0) + 1
        for card in community_cards:
            if card[1] in suit_count:
                suit_count[card[1]] += 1
        return 1 if max(suit_count.values()) == 4 else 0

    def straight_probability(self, community_cards):
        rank_to_int = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
                    'T': 10, '10': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}

        board_mask = 0
        parsed_board = set()

        for card in community_cards:
            rank_str = card[:-1].upper()
            suit_str = card[-1].lower()
            rank_val = rank_to_int[rank_str]
            board_mask |= (1 << rank_val)
            if rank_val == 14:
                board_mask |= (1 << 1)
            parsed_board.add(f"{rank_str}{suit_str}")

        remaining_masks = []
        for rank in '23456789TJQKA':
            for suit in 'hdcs':
                card = f"{rank}{suit}"
                if card not in parsed_board:
                    rank_val = rank_to_int[rank]
                    mask = (1 << rank_val)
                    if rank_val == 14:
                        mask |= (1 << 1)
                    remaining_masks.append(mask)

        straight_hands = 0
        total_hands = 0
        for card1_mask, card2_mask in itertools.combinations(remaining_masks, 2):
            total_hands += 1
            combined_mask = board_mask | card1_mask | card2_mask
            if combined_mask & (combined_mask >> 1) & (combined_mask >> 2) & (combined_mask >> 3) & (combined_mask >> 4):
                straight_hands += 1

        return straight_hands / total_hands


    def flush_probability(self, community_cards):
        suit_count = {'h': 0, 'd': 0, 'c': 0, 's': 0}
        for card in community_cards:
            suit_count[card[-1].lower()] += 1

        total_remaining = 52 - len(community_cards)
        total_combos = comb(total_remaining, 2)

        flush_combos = 0
        for suit, on_board in suit_count.items():
            need = 5 - on_board
            if need > 2:        # opponent can't supply 3+ cards
                continue
            remaining_suit = 13 - on_board
            if need == 0:       # flush already on board — every hand qualifies
                flush_combos += total_combos
            elif need == 1:     # need ≥1 of this suit → total minus (0 of this suit)
                non_suit = total_remaining - remaining_suit
                flush_combos += total_combos - comb(non_suit, 2)
            elif need == 2:     # need both cards to be this suit
                flush_combos += comb(remaining_suit, 2)

        return flush_combos / total_combos
    
    def _rank_counts(self, board):
        return Counter(c[:-1].upper().replace('10','T') for c in board)

    def is_paired(self, board):
        """Board has exactly one pair."""
        if board:
            return 1 if sorted(self._rank_counts(board).values(), reverse=True)[:2] == [2, 1] else 0
        return 0

    def is_two_paired(self, board):
        """Board has two pairs."""
        if board:
            return 1 if sorted(self._rank_counts(board).values(), reverse=True)[:2] == [2, 2] else 0
        return 0

    def is_trips(self, board):
        """Board has three of a kind."""
        if board:
            return 1 if max(self._rank_counts(board).values()) == 3 else 0
        return 0
        

    def is_quads(self, board):
        """Board has four of a kind."""
        if board:
            return 1 if max(self._rank_counts(board).values()) == 4 else 0
        return 0
    
    def get_last_two_actions(self, gamestate:PublicGamestate, street, player_idx):
        hand_history = gamestate.current_hand_history
        last_action = [0]*5
        sec_last_action = [0]*5

        action_index = {
            'fold': 0,
            'call': 1,
            'raise': 2,
            'all-in': 3
        }

        actions = hand_history[street].actions
        for action in actions:
            if action.player_index == player_idx:
                if action.action_type in action_index:
                    sec_last_action = last_action.copy()
                    last_action[action_index[action.action_type]] = 1
                    last_action[4] = action.amount / 250
        
        return [last_action, sec_last_action]

    def _action_idx_to_poker_action(
        self,
        action_idx: int,
        gamestate: PublicGamestate,
        hole_cards: Tuple[str, str]
    ) -> Tuple[str, int]:
        """Convert model output index to poker action.

        Action space:
        0: fold
        1: check
        2: call
        3: raise 0.25x pot
        4: raise 0.5x pot
        5: raise 0.75x pot
        6: raise 1x pot
        7: raise 1.5x pot
        8: raise 2x pot
        9: all-in

        Args:
            action_idx: Index from model (0-9)
            gamestate: Current gamestate
            hole_cards: Player's cards

        Returns:
            (action_type, amount) tuple
        """
        my_info = gamestate.player_public_infos[self.player_index]
        my_stack = my_info.stack
        my_current_bet = my_info.current_bet
        bet_to_call = gamestate.get_bet_to_call()
        amount_to_call = bet_to_call - my_current_bet
        pot_size = gamestate.total_pot + sum(p.current_bet for p in gamestate.player_public_infos)

        # Fold
        if action_idx == 0:
            return ('fold', 0)

        # Check
        elif action_idx == 1:
            return ('check', 0)

        # Call
        elif action_idx == 2:
            return ('call', 0)

        # All-in
        elif action_idx == 9:
            return ('all-in', my_stack)

        # Raise actions (indices 3-8)
        elif 3 <= action_idx <= 8:
            pot_fractions = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0]
            fraction = pot_fractions[action_idx - 3]
            raise_amount = int(pot_size * fraction)

            return ('raise', raise_amount)

        # Default to check/call if invalid index
        else:
            if amount_to_call == 0:
                return ('check', 0)
            else:
                return ('call', 0)

