from typing import List, Dict, Any

def calculate_preflop_frequencies(hand_histories: List[Any], use_bayesian: bool = True) -> Dict[int, Dict[str, float]]:
    """
    Calculates core preflop frequencies (VPIP, PFR, Limp, Fold to PFR, Cold Call, Iso Raise)
    from a list of HandRecord objects.
    """
    
    # 1. Initialize raw counters for 9 players
    raw_stats = {i: {
        'hands': 0, 'vpip': 0, 'pfr': 0, 'limp': 0,
        'faced_pfr': 0, 'fold_to_pfr': 0,
        'opp_cold_call': 0, 'cold_call': 0,
        'faced_limp': 0, 'iso_raise': 0
    } for i in range(9)}

    # 2. Process each hand
    for hand in hand_histories:
        preflop = hand.per_street['preflop'].actions
        if not preflop:
            continue
            
        # Determine active players and positional order based on first action taken
        ordered_players = []
        for act in preflop:
            if act.player_index not in ordered_players:
                ordered_players.append(act.player_index)
                
        # (Optional mapping ready for positional stats 8-13)
        # Assuming standard flow: ordered_players = [SB, BB, UTG, ..., BTN]
        
        for p in ordered_players:
            raw_stats[p]['hands'] += 1

        # Hand-level state tracking (using sets to avoid double-counting multi-action streets)
        vpip_players, pfr_players, limped_players = set(), set(), set()
        faced_pfr_players, folded_to_pfr_players = set(), set()
        opp_cold_call_players, cold_called_players = set(), set()
        faced_limp_players, iso_raised_players = set(), set()

        has_voluntarily_acted = set()
        highest_bet = 0
        is_raised = False
        limper_count = 0

        # 3. Step chronologically through preflop actions
        for act in preflop:
            p = act.player_index
            atype = act.action_type
            amt = act.amount

            # Blinds are forced, not voluntary
            if atype in ['small_blind', 'big_blind']:
                if amt > highest_bet:
                    highest_bet = amt
                continue

            is_first_action = p not in has_voluntarily_acted

            # --- Evaluate Opportunities (Before the action is taken) ---
            if is_first_action:
                if is_raised:
                    faced_pfr_players.add(p)
                    opp_cold_call_players.add(p)
                elif limper_count > 0:
                    faced_limp_players.add(p)

            # --- Process Action ---
            if atype == 'fold':
                if is_first_action and is_raised:
                    folded_to_pfr_players.add(p)
                has_voluntarily_acted.add(p)

            elif atype == 'check':
                # Big Blind checking option preflop; doesn't count as VPIP
                has_voluntarily_acted.add(p)

            elif atype == 'call':
                vpip_players.add(p)
                if is_first_action:
                    if not is_raised:
                        limped_players.add(p)
                        limper_count += 1
                    else:
                        cold_called_players.add(p)
                has_voluntarily_acted.add(p)

            elif atype in ['raise', 'all-in']:
                vpip_players.add(p)
                is_actual_raise = amt > highest_bet

                if is_actual_raise:
                    pfr_players.add(p)
                    if not is_raised:
                        is_raised = True
                        if is_first_action and limper_count > 0:
                            iso_raised_players.add(p)
                    highest_bet = amt
                else:
                    # All-in for less/equal to current highest bet acts exactly like a call
                    if is_first_action:
                        if not is_raised:
                            limped_players.add(p)
                            limper_count += 1
                        else:
                            cold_called_players.add(p)
                has_voluntarily_acted.add(p)

        # 4. Apply hand results to global counters
        for p in ordered_players:
            if p in vpip_players: raw_stats[p]['vpip'] += 1
            if p in pfr_players: raw_stats[p]['pfr'] += 1
            if p in limped_players: raw_stats[p]['limp'] += 1
            
            if p in faced_pfr_players:
                raw_stats[p]['faced_pfr'] += 1
                if p in folded_to_pfr_players: raw_stats[p]['fold_to_pfr'] += 1
                
            if p in opp_cold_call_players:
                raw_stats[p]['opp_cold_call'] += 1
                if p in cold_called_players: raw_stats[p]['cold_call'] += 1
                
            if p in faced_limp_players:
                raw_stats[p]['faced_limp'] += 1
                if p in iso_raised_players: raw_stats[p]['iso_raise'] += 1

    # 5. Calculate Final Percentages with optional Bayesian Smoothing
    # Priors represent a generic "Tight-Aggressive" profile over a ~10 hand sample.
    # Format: (Alpha/Successes, Beta/Failures)
    priors = {
        'vpip': (2.0, 8.0),        # 20% default
        'pfr': (1.5, 8.5),         # 15% default
        'limp': (1.0, 9.0),        # 10% default
        'fold_to_pfr': (7.0, 3.0), # 70% default
        'cold_call': (1.0, 9.0),   # 10% default
        'iso_raise': (2.0, 8.0)    # 20% default
    }

    final_stats = {}
    for p in range(9):
        st = raw_stats[p]
        p_stats = {}
        
        def get_stat(event_count, total_opps, stat_key):
            if use_bayesian:
                alpha, beta = priors[stat_key]
                return (event_count + alpha) / (total_opps + alpha + beta)
            return (event_count / total_opps) if total_opps > 0 else 0.0

        p_stats['Hands Played'] = st['hands']
        p_stats['VPIP %'] = get_stat(st['vpip'], st['hands'], 'vpip') 
        p_stats['PFR %'] = get_stat(st['pfr'], st['hands'], 'pfr') 
        p_stats['PFR/VPIP Ratio'] = (p_stats['PFR %'] / p_stats['VPIP %']) if p_stats['VPIP %'] > 0 else 0.0
        p_stats['Limp %'] = get_stat(st['limp'], st['hands'], 'limp') 
        p_stats['Fold to PFR %'] = get_stat(st['fold_to_pfr'], st['faced_pfr'], 'fold_to_pfr') 
        p_stats['Cold Call %'] = get_stat(st['cold_call'], st['opp_cold_call'], 'cold_call') 
        p_stats['Isolation Raise %'] = get_stat(st['iso_raise'], st['faced_limp'], 'iso_raise') 
        
        final_stats[p] = p_stats

    return final_stats

def calculate_positional_preflop_stats(hand_histories: List[Any], use_bayesian: bool = True) -> Dict[int, Dict[str, float]]:
    """
    Calculates advanced positional preflop frequencies (ATS, BB Defend, 3-Bet, etc.)
    from a list of HandRecord objects.
    """
    
    # 1. Initialize raw counters for 9 players
    raw_stats = {i: {
        'opp_ats': 0, 'did_ats': 0,
        'opp_fold_to_steal': 0, 'did_fold_to_steal': 0,
        'opp_bb_defend': 0, 'did_bb_defend': 0,
        'opp_rfi_em': 0, 'did_rfi_em': 0,
        'opp_3bet': 0, 'did_3bet': 0,
        'opp_fold_to_3bet': 0, 'did_fold_to_3bet': 0
    } for i in range(9)}

    # 2. Process each hand
    for hand in hand_histories:
        preflop = hand.per_street['preflop'].actions
        if not preflop:
            continue

        # --- Position Reconstruction ---
        # Get the strict order of all actors in the hand (including forced blinds)
        all_actors = []
        for a in preflop:
            if a.player_index not in all_actors:
                all_actors.append(a.player_index)
                
        if len(all_actors) < 3:
            continue # Skip stats requiring positional dynamics if heads-up or fewer
            
        sb = all_actors[0] # First to post
        bb = all_actors[1] # Second to post
        
        # Standardize the seating order starting from UTG (actor #3) to the BB
        ordered_seats = all_actors[2:] + [sb, bb]
        
        # Map players to categorical positions based on distance from the Button/Blinds
        steal_positions = []
        if len(ordered_seats) >= 3: steal_positions.append(ordered_seats[-3]) # BTN
        if len(ordered_seats) >= 4: steal_positions.append(ordered_seats[-4]) # CO
        steal_positions.append(sb) # SB is also a steal position
        
        ep_mp_positions = [p for p in ordered_seats if p not in steal_positions and p != bb]

        # --- Hand State Tracking ---
        unopened = True
        highest_bet = 0
        raiser_count = 0
        initial_raiser = None
        three_bettor = None
        is_steal_attempt = False
        has_acted = set()

        # Unique sets for hand-level tracking to prevent double counting
        opp_ats, did_ats = set(), set()
        opp_fold_steal, did_fold_steal = set(), set()
        opp_bb_defend, did_bb_defend = set(), set()
        opp_rfi_em, did_rfi_em = set(), set()
        opp_3bet, did_3bet = set(), set()
        opp_fold_3bet, did_fold_3bet = set(), set()

        # 3. Step chronologically through preflop actions
        for act in preflop:
            p = act.player_index
            atype = act.action_type
            amt = act.amount

            if atype in ['small_blind', 'big_blind']:
                if amt > highest_bet:
                    highest_bet = amt
                continue

            is_first_action = p not in has_acted

            # --- Evaluate Opportunities (Before action is taken) ---
            if unopened and is_first_action:
                if p in steal_positions:
                    opp_ats.add(p)
                elif p in ep_mp_positions:
                    opp_rfi_em.add(p)

            # Facing a Steal Attempt
            if is_first_action and is_steal_attempt and raiser_count == 1:
                if p == sb or p == bb:
                    opp_fold_steal.add(p)
                if p == bb:
                    opp_bb_defend.add(p)

            # Facing a single Raise (3-Bet opportunity)
            if is_first_action and raiser_count == 1 and initial_raiser is not None:
                opp_3bet.add(p)

            # Initial raiser facing a 3-Bet
            if p == initial_raiser and raiser_count == 2 and three_bettor is not None:
                opp_fold_3bet.add(p)

            # --- Process Action ---
            if atype == 'fold':
                if p in opp_fold_steal and is_first_action: did_fold_steal.add(p)
                if p in opp_fold_3bet: did_fold_3bet.add(p)
            
            elif atype == 'call':
                unopened = False
                if p in opp_bb_defend and is_first_action and is_steal_attempt and raiser_count == 1:
                    did_bb_defend.add(p)
                    
            elif atype in ['raise', 'all-in']:
                is_actual_raise = amt > highest_bet
                
                if is_actual_raise:
                    if unopened:
                        unopened = False
                        raiser_count = 1
                        initial_raiser = p
                        
                        if p in steal_positions:
                            did_ats.add(p)
                            is_steal_attempt = True
                        elif p in ep_mp_positions:
                            did_rfi_em.add(p)
                            
                    elif raiser_count == 1:
                        raiser_count = 2
                        three_bettor = p
                        if p in opp_3bet: did_3bet.add(p)
                        if p in opp_bb_defend and is_steal_attempt: did_bb_defend.add(p)
                        
                    elif raiser_count >= 2:
                        raiser_count += 1
                        
                    highest_bet = amt
                else:
                    # All-in for less/equal acts as a call
                    unopened = False
                    if p in opp_bb_defend and is_first_action and is_steal_attempt and raiser_count == 1:
                        did_bb_defend.add(p)

            has_acted.add(p)

        # 4. Apply hand results to global counters
        for p in ordered_seats:
            if p in opp_ats: raw_stats[p]['opp_ats'] += 1
            if p in did_ats: raw_stats[p]['did_ats'] += 1
            
            if p in opp_fold_steal: raw_stats[p]['opp_fold_to_steal'] += 1
            if p in did_fold_steal: raw_stats[p]['did_fold_to_steal'] += 1
            
            if p in opp_bb_defend: raw_stats[p]['opp_bb_defend'] += 1
            if p in did_bb_defend: raw_stats[p]['did_bb_defend'] += 1
            
            if p in opp_rfi_em: raw_stats[p]['opp_rfi_em'] += 1
            if p in did_rfi_em: raw_stats[p]['did_rfi_em'] += 1
            
            if p in opp_3bet: raw_stats[p]['opp_3bet'] += 1
            if p in did_3bet: raw_stats[p]['did_3bet'] += 1
            
            if p in opp_fold_3bet: raw_stats[p]['opp_fold_to_3bet'] += 1
            if p in did_fold_3bet: raw_stats[p]['did_fold_to_3bet'] += 1

    # 5. Calculate Final Percentages with optional Bayesian Smoothing
    # Profile priors (Alpha/Successes, Beta/Failures) geared toward a solid TAG player.
    priors = {
        'ats': (3.5, 6.5),          # ~35%
        'fold_to_steal': (6.0, 4.0),# ~60%
        'bb_defend': (4.0, 6.0),    # ~40% (Calling + 3-betting combined)
        'rfi_em': (1.5, 8.5),       # ~15% 
        '3bet': (0.8, 9.2),         # ~8%
        'fold_to_3bet': (5.0, 5.0)  # ~50%
    }

    final_stats = {}
    for p in range(9):
        st = raw_stats[p]
        p_stats = {}
        
        def get_stat(event_count, total_opps, stat_key):
            if use_bayesian:
                alpha, beta = priors[stat_key]
                return (event_count + alpha) / (total_opps + alpha + beta)
            return (event_count / total_opps) if total_opps > 0 else 0.0

        p_stats['Attempt to Steal (ATS) %'] = get_stat(st['did_ats'], st['opp_ats'], 'ats') 
        p_stats['Fold to Steal %'] = get_stat(st['did_fold_to_steal'], st['opp_fold_to_steal'], 'fold_to_steal') 
        p_stats['BB Defend %'] = get_stat(st['did_bb_defend'], st['opp_bb_defend'], 'bb_defend') 
        p_stats['RFI (Early/Mid) %'] = get_stat(st['did_rfi_em'], st['opp_rfi_em'], 'rfi_em') 
        p_stats['3-Bet Preflop %'] = get_stat(st['did_3bet'], st['opp_3bet'], '3bet') 
        p_stats['Fold to 3-Bet %'] = get_stat(st['did_fold_to_3bet'], st['opp_fold_to_3bet'], 'fold_to_3bet') 
        
        final_stats[p] = p_stats

    return final_stats


def calculate_common_flop_stats(hand_histories: List[Any], use_bayesian: bool = True) -> Dict[int, Dict[str, float]]:
    """
    Calculates Flop C-Bet dynamics, Check-Fold Flop %, and overall post-flop Aggression Factor (AF).
    Consolidated to keep the codebase clean.
    """
    
    # 1. Initialize raw counters for 9 players
    raw_stats = {i: {
        'opp_cbet': 0, 'did_cbet': 0,
        'faced_cbet': 0, 'fold_to_cbet': 0, 'call_cbet': 0,
        'af_aggressions': 0, 'af_calls': 0,
        'opp_check_fold': 0, 'did_check_fold': 0  # NEW: Check-Fold tracking
    } for i in range(9)}

    aggressive_actions = ['bet', 'raise', 'all-in']

    # 2. Process each hand
    for hand in hand_histories:
        # --- Preflop Analysis: Identify the PFR ---
        preflop = hand.per_street['preflop'].actions
        pfr = None
        highest_preflop_bet = 0
        
        for act in preflop:
            if act.action_type in ['raise', 'all-in'] and act.amount > highest_preflop_bet:
                pfr = act.player_index
                highest_preflop_bet = act.amount

        # --- Overall Aggression Factor (AF) Tracking ---
        for street in ['flop', 'turn', 'river']:
            for act in hand.per_street[street].actions:
                if act.action_type in aggressive_actions:
                    raw_stats[act.player_index]['af_aggressions'] += 1
                elif act.action_type == 'call':
                    raw_stats[act.player_index]['af_calls'] += 1

        # --- Flop Dynamics (C-Bets & Check-Folds) ---
        flop_actions = hand.per_street['flop'].actions
        if not flop_actions:
            continue

        # Variables for C-Bet Tracking
        cbet_occurred = False
        pfr_checked = False
        cbet_action_idx = -1
        
        # Variables for Check-Fold Tracking
        checked_players = set()
        bet_occurred = False

        # Single pass through the flop actions to evaluate both dynamics
        for i, act in enumerate(flop_actions):
            p = act.player_index
            atype = act.action_type

            # Check-Fold Logic
            if atype == 'check':
                if not bet_occurred:
                    checked_players.add(p)
            elif atype in aggressive_actions:
                bet_occurred = True
                if p in checked_players:
                    raw_stats[p]['opp_check_fold'] += 1
                    checked_players.remove(p)
            elif atype == 'fold':
                if p in checked_players and bet_occurred:
                    raw_stats[p]['opp_check_fold'] += 1
                    raw_stats[p]['did_check_fold'] += 1
                    checked_players.remove(p)
            elif atype == 'call':
                if p in checked_players and bet_occurred:
                    raw_stats[p]['opp_check_fold'] += 1
                    checked_players.remove(p)

            # C-Bet Logic (Opportunity mapping)
            if pfr is not None and not cbet_occurred:
                if atype in aggressive_actions:
                    if p == pfr and not pfr_checked:
                        raw_stats[pfr]['opp_cbet'] += 1
                        raw_stats[pfr]['did_cbet'] += 1
                        cbet_occurred = True
                        cbet_action_idx = i
                    # Once any bet happens, C-bet opportunity closes
                elif atype == 'check' and p == pfr:
                    raw_stats[pfr]['opp_cbet'] += 1
                    pfr_checked = True

        # Track responses if a C-bet actually occurred
        if cbet_occurred and cbet_action_idx != -1:
            responded = set()
            for act in flop_actions[cbet_action_idx + 1:]:
                p = act.player_index
                if p == pfr: 
                    continue
                    
                if p not in responded:
                    responded.add(p)
                    raw_stats[p]['faced_cbet'] += 1
                    if act.action_type == 'fold':
                        raw_stats[p]['fold_to_cbet'] += 1
                    elif act.action_type == 'call':
                        raw_stats[p]['call_cbet'] += 1

    # 3. Calculate Final Percentages with optional Bayesian Smoothing
    priors = {
        'cbet': (5.0, 5.0),          # ~50% C-Bet
        'fold_cbet': (4.0, 6.0),     # ~40% Fold to C-bet
        'call_cbet': (3.0, 7.0),     # ~30% Call C-bet
        'check_fold': (4.5, 5.5)     # ~45% Check-Fold Flop
    }
    
    af_agg_prior = 4.0
    af_call_prior = 2.0

    final_stats = {}
    for p in range(9):
        st = raw_stats[p]
        p_stats = {}
        
        def get_stat(event_count, total_opps, stat_key):
            if use_bayesian:
                alpha, beta = priors[stat_key]
                return (event_count + alpha) / (total_opps + alpha + beta)
            return (event_count / total_opps) if total_opps > 0 else 0.0

        p_stats['Flop C-Bet %'] = get_stat(st['did_cbet'], st['opp_cbet'], 'cbet')
        p_stats['Fold to Flop C-Bet %'] = get_stat(st['fold_to_cbet'], st['faced_cbet'], 'fold_cbet')
        p_stats['Call Flop C-Bet %'] = get_stat(st['call_cbet'], st['faced_cbet'], 'call_cbet')
        p_stats['Check-Fold Flop %'] = get_stat(st['did_check_fold'], st['opp_check_fold'], 'check_fold')
        
        if use_bayesian:
            p_stats['Aggression Factor (AF)'] = (st['af_aggressions'] + af_agg_prior) / (st['af_calls'] + af_call_prior)
        else:
            p_stats['Aggression Factor (AF)'] = (st['af_aggressions'] / st['af_calls']) if st['af_calls'] > 0 else float(st['af_aggressions'])
            
        final_stats[p] = p_stats

    return final_stats


def calculate_advanced_and_global_stats(hand_histories: List[Any], use_bayesian: bool = True) -> Dict[int, Dict[str, float]]:
    """
    Calculates advanced post-flop plays (Check-Raises, Floats, Double Barrels) 
    and global metrics (AFq, WTSD).
    """
    
    # 1. Initialize raw counters for 9 players
    raw_stats = {i: {
        'saw_flop': 0, 'went_to_showdown': 0,
        'afq_aggressions': 0, 'afq_passives': 0, # Passives = Calls + Folds
        'opp_flop_cr': 0, 'did_flop_cr': 0,
        'opp_turn_cr': 0, 'did_turn_cr': 0,
        'opp_donk': 0, 'did_donk': 0,
        'opp_float': 0, 'did_float': 0,
        'faced_float': 0, 'fold_to_float': 0,
        'opp_turn_cbet': 0, 'did_turn_cbet': 0,
        'faced_turn_cbet': 0, 'fold_to_turn_cbet': 0,
        'opp_river_bet': 0, 'did_river_bet': 0,
        'faced_river_bet': 0, 'fold_to_river_bet': 0,
        'river_call_amount': 0 # For River Call Efficiency
    } for i in range(9)}

    aggressive_actions = ['bet', 'raise', 'all-in']

    # 2. Process each hand
    for hand in hand_histories:
        # --- Preflop Setup & PFR Identification ---
        preflop_actions = hand.per_street['preflop'].actions
        pfr = None
        highest_preflop_bet = 0
        active_going_to_flop = set()
        
        for act in preflop_actions:
            active_going_to_flop.add(act.player_index)
            if act.action_type == 'fold':
                active_going_to_flop.remove(act.player_index)
            elif act.action_type in ['raise', 'all-in'] and act.amount > highest_preflop_bet:
                pfr = act.player_index
                highest_preflop_bet = act.amount

        # --- Global AFq Tracking (All Post-Flop Streets) ---
        for street in ['flop', 'turn', 'river']:
            for act in hand.per_street[street].actions:
                p = act.player_index
                if act.action_type in aggressive_actions:
                    raw_stats[p]['afq_aggressions'] += 1
                elif act.action_type in ['call', 'fold']:
                    raw_stats[p]['afq_passives'] += 1

        # --- Flop Dynamics ---
        flop_actions = hand.per_street['flop'].actions
        if flop_actions:
            for p in active_going_to_flop:
                raw_stats[p]['saw_flop'] += 1

            pfr_acted = False
            pfr_cbet = False
            first_bet_made = False
            checked_players = set()
            
            for i, act in enumerate(flop_actions):
                p = act.player_index
                atype = act.action_type
                
                # Check-Raise Logic
                if atype == 'check':
                    checked_players.add(p)
                elif atype in aggressive_actions and p in checked_players:
                    # If they previously checked and are now betting/raising, it's a check-raise
                    raw_stats[p]['opp_flop_cr'] += 1
                    raw_stats[p]['did_flop_cr'] += 1
                elif atype == 'call' and p in checked_players:
                    raw_stats[p]['opp_flop_cr'] += 1 # They had the opportunity but just called
                    
                # Donk Bet Logic
                if not first_bet_made and atype in aggressive_actions:
                    first_bet_made = True
                    if pfr is not None and p != pfr and not pfr_acted:
                        raw_stats[p]['opp_donk'] += 1
                        raw_stats[p]['did_donk'] += 1
                    
                    if p == pfr:
                        pfr_cbet = True

                # Float Logic (PFR checks, IP player bets)
                if p == pfr:
                    pfr_acted = True
                
                if pfr is not None and pfr_acted and not pfr_cbet and atype in aggressive_actions:
                    raw_stats[p]['opp_float'] += 1
                    raw_stats[p]['did_float'] += 1
                    
                # Fold to Float Logic
                if p == pfr and not pfr_cbet and atype == 'fold':
                    # Assuming they faced a float bet since they folded after checking
                    raw_stats[p]['faced_float'] += 1
                    raw_stats[p]['fold_to_float'] += 1

        # --- Turn Dynamics (Double Barrels & Check-Raises) ---
        turn_actions = hand.per_street['turn'].actions
        turn_cbet_occurred = False
        
        if turn_actions:
            checked_turn_players = set()
            turn_bet_made = False
            
            for act in turn_actions:
                p = act.player_index
                atype = act.action_type
                
                # Turn Check-Raise Logic
                if atype == 'check':
                    checked_turn_players.add(p)
                elif atype in aggressive_actions and p in checked_turn_players:
                    raw_stats[p]['opp_turn_cr'] += 1
                    raw_stats[p]['did_turn_cr'] += 1
                elif atype == 'call' and p in checked_turn_players:
                    raw_stats[p]['opp_turn_cr'] += 1

                # Double Barrel (Turn C-Bet) Logic
                if not turn_bet_made and atype in aggressive_actions:
                    turn_bet_made = True
                    if p == pfr and pfr_cbet: # PFR fired flop AND is firing turn
                        raw_stats[p]['opp_turn_cbet'] += 1
                        raw_stats[p]['did_turn_cbet'] += 1
                        turn_cbet_occurred = True
                    elif p == pfr:
                        raw_stats[p]['opp_turn_cbet'] += 1 # Opportunity missed

                # Fold to Turn C-Bet
                if turn_cbet_occurred and p != pfr:
                    if p not in checked_turn_players: # First time acting after the turn cbet
                        raw_stats[p]['faced_turn_cbet'] += 1
                        if atype == 'fold':
                            raw_stats[p]['fold_to_turn_cbet'] += 1

        # --- River Dynamics ---
        river_actions = hand.per_street['river'].actions
        if river_actions:
            river_bet_made = False
            for act in river_actions:
                p = act.player_index
                atype = act.action_type
                
                if not river_bet_made:
                    if atype in aggressive_actions:
                        river_bet_made = True
                        raw_stats[p]['opp_river_bet'] += 1
                        raw_stats[p]['did_river_bet'] += 1
                    elif atype == 'check':
                        raw_stats[p]['opp_river_bet'] += 1
                else:
                    if atype == 'fold':
                        raw_stats[p]['faced_river_bet'] += 1
                        raw_stats[p]['fold_to_river_bet'] += 1
                    elif atype == 'call':
                        raw_stats[p]['faced_river_bet'] += 1
                        raw_stats[p]['river_call_amount'] += act.amount

        # --- Showdown Metrics ---
        if hand.showdown_details:
            for p in hand.showdown_details['players']:
                raw_stats[p]['went_to_showdown'] += 1

    # 3. Calculate Final Percentages with optional Bayesian Smoothing
    priors = {
        'cr': (1.0, 9.0),         # ~10% Check-Raise
        'donk': (1.0, 9.0),       # ~10% Donk Bet
        'float': (3.0, 7.0),      # ~30% Float
        'fold_float': (4.0, 6.0), # ~40% Fold to Float
        'turn_cbet': (4.5, 5.5),  # ~45% Turn C-bet (Double Barrel)
        'fold_turn_cbet': (4.0, 6.0), # ~40% Fold to Turn C-Bet
        'river_bet': (3.0, 7.0),  # ~30% River Bet
        'fold_river_bet': (5.0, 5.0), # ~50% Fold to River Bet
        'wtsd': (3.0, 7.0)        # ~30% Went To Showdown
    }

    final_stats = {}
    for p in range(9):
        st = raw_stats[p]
        p_stats = {}
        
        def get_stat(event_count, total_opps, stat_key):
            if use_bayesian:
                alpha, beta = priors[stat_key]
                return (event_count + alpha) / (total_opps + alpha + beta)
            return (event_count / total_opps) if total_opps > 0 else 0.0

        p_stats['Flop Check-Raise %'] = get_stat(st['did_flop_cr'], st['opp_flop_cr'], 'cr') 
        p_stats['Turn Check-Raise %'] = get_stat(st['did_turn_cr'], st['opp_turn_cr'], 'cr') 
        p_stats['Flop Donk Bet %'] = get_stat(st['did_donk'], st['opp_donk'], 'donk') 
        p_stats['Float Flop %'] = get_stat(st['did_float'], st['opp_float'], 'float') 
        p_stats['Fold to Flop Float %'] = get_stat(st['fold_to_float'], st['faced_float'], 'fold_float') 
        p_stats['Turn C-Bet (Double Barrel) %'] = get_stat(st['did_turn_cbet'], st['opp_turn_cbet'], 'turn_cbet') 
        p_stats['Fold to Turn C-Bet %'] = get_stat(st['fold_to_turn_cbet'], st['faced_turn_cbet'], 'fold_turn_cbet') 
        p_stats['River Bet Frequency %'] = get_stat(st['did_river_bet'], st['opp_river_bet'], 'river_bet') 
        p_stats['Fold to River Bet %'] = get_stat(st['fold_to_river_bet'], st['faced_river_bet'], 'fold_river_bet') 
        p_stats['Went to Showdown (WTSD) %'] = get_stat(st['went_to_showdown'], st['saw_flop'], 'wtsd') 
        
        # Aggression Frequency (AFq)
        total_afq_actions = st['afq_aggressions'] + st['afq_passives']
        if use_bayesian:
            p_stats['Aggression Frequency (AFq) %'] = (st['afq_aggressions'] + 4.0) / (total_afq_actions + 10.0)
        else:
            p_stats['Aggression Frequency (AFq) %'] = (st['afq_aggressions'] / total_afq_actions) if total_afq_actions > 0 else 0.0

        final_stats[p] = p_stats

    return final_stats

def calculate_exploitative_stats(hand_histories: List[Any], use_bayesian: bool = True) -> Dict[int, Dict[str, float]]:
    """
    Calculates highly actionable, fast-converging exploitative metrics:
    WTSD with Air, Limp-Fold %, and Squeeze %.
    """
    
    # 1. Initialize raw counters
    raw_stats = {i: {
        'went_to_showdown': 0, 'wtsd_with_air': 0,
        'opp_limp_fold': 0, 'did_limp_fold': 0,
        'opp_squeeze': 0, 'did_squeeze': 0
    } for i in range(9)}

    # 2. Process each hand
    for hand in hand_histories:
        
        # --- 1. Showdown with Air Logic ---
        # The showdown_details dict contains 'players', 'hands', and 'hole_cards'
        if hand.showdown_details:
            for p in hand.showdown_details['players']: #
                raw_stats[p]['went_to_showdown'] += 1
                
                # Assuming HandJudge outputs standard strings like "High Card, Ace"
                hand_str = hand.showdown_details['hands'].get(p, "") #
                if "high_card" in hand_str:
                    raw_stats[p]['wtsd_with_air'] += 1

        # --- 2. Preflop Dynamics (Limp-Fold & Squeeze) ---
        preflop = hand.per_street.get('preflop') #
        if not preflop or not preflop.actions:
            continue

        highest_bet = 0
        raiser_count = 0
        callers_since_raise = 0
        
        # Track player states for this specific hand
        has_limped = set()
        has_acted = set()

        for act in preflop.actions:
            p = act.player_index #
            atype = act.action_type #
            amt = act.amount #

            if atype in ['small_blind', 'big_blind']: #
                if amt > highest_bet: highest_bet = amt
                continue

            is_first_action = p not in has_acted

            # --- Squeeze Opportunity Evaluation ---
            # A squeeze opportunity exists if there is exactly 1 raiser and at least 1 caller before us
            if is_first_action and raiser_count == 1 and callers_since_raise >= 1:
                raw_stats[p]['opp_squeeze'] += 1
                if atype in ['raise', 'all-in'] and amt > highest_bet:
                    raw_stats[p]['did_squeeze'] += 1

            # --- Limp-Fold Opportunity Evaluation ---
            # If a player previously limped, and the bet is now higher than a blind, they face a decision
            if p in has_limped and highest_bet > amt:
                raw_stats[p]['opp_limp_fold'] += 1
                if atype == 'fold': #
                    raw_stats[p]['did_limp_fold'] += 1
                
                # Once they respond to the raise, they no longer have a pending limp-fold opportunity
                has_limped.remove(p)

            # --- Action Processing ---
            if atype == 'call': #
                if is_first_action and raiser_count == 0:
                    has_limped.add(p)
                elif raiser_count == 1:
                    callers_since_raise += 1
                    
            elif atype in ['raise', 'all-in']: #
                if amt > highest_bet:
                    raiser_count += 1
                    callers_since_raise = 0 # Reset callers for the new raise level
                    highest_bet = amt

            has_acted.add(p)

    # 3. Calculate Final Percentages
    priors = {
        'wtsd_air': (0.5, 9.5),   # ~5% baseline for having pure air at showdown
        'limp_fold': (6.0, 4.0),  # ~60% baseline (limpers fold to raises often)
        'squeeze': (0.5, 9.5)     # ~5% baseline (squeezing is a rare, aggressive play)
    }

    final_stats = {}
    for p in range(9):
        st = raw_stats[p]
        p_stats = {}
        
        def get_stat(event_count, total_opps, stat_key):
            if use_bayesian:
                alpha, beta = priors[stat_key]
                return (event_count + alpha) / (total_opps + alpha + beta)
            return (event_count / total_opps) if total_opps > 0 else 0.0

        p_stats['WTSD with Air %'] = get_stat(st['wtsd_with_air'], st['went_to_showdown'], 'wtsd_air')
        p_stats['Limp-Fold %'] = get_stat(st['did_limp_fold'], st['opp_limp_fold'], 'limp_fold')
        p_stats['Squeeze %'] = get_stat(st['did_squeeze'], st['opp_squeeze'], 'squeeze')
        
        final_stats[p] = p_stats

    return final_stats

def calculate_player_stats(hand_histories):
    advance = calculate_advanced_and_global_stats(hand_histories)
    common_flop = calculate_common_flop_stats(hand_histories)
    exploitative = calculate_exploitative_stats(hand_histories)
    positional_preflop = calculate_positional_preflop_stats(hand_histories)
    preflop_frequencies = calculate_preflop_frequencies(hand_histories)

    full_stats = []
    for i in range(9):
        full_stat = advance[i] | common_flop[i] | exploitative[i] | positional_preflop[i] | preflop_frequencies[i]
        full_stats.append(full_stat)
    return full_stats
    