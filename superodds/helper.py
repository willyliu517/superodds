import requests
import re
import time
import datetime
import yaml
import math
import numpy as np
from typing import Dict, List, Tuple
from pathlib import Path

def load_yaml_file(path: str) -> Dict | List | None:
    '''
    loads in the yaml file specified in the path depending on the format of the yaml, the output will be either a List or Dictonary 
    '''
    
    with open(path, 'r') as stream:
        try:
            config = yaml.safe_load(stream)
            return config
        except yaml.YAMLError as exc:
            print(exc)


def ensure_dir_exists(dir_path: str) -> str:
    '''
    checks if the directory exists and creates it if not
    '''
    try:
        os.makedirs(dir_path)
        return dir_path
    except FileExistsError:
        return dir_path

def compute_vig_implied_probability(odds: int) -> float:
    '''
        computes the implied probability (with vig included) for a particular match
    '''
    # negative odds imply that you are the favourite
    if odds < 0: 
        return abs(odds) / (abs(odds) + 100)
    else:
        return 100 / (100 + odds)

def compute_no_vig_probabilities(odds_team_1: int, odds_team_2: int) -> Tuple[float, float]:
    '''
        computes the implied fair odds (excluding the vig from the sportsbook) for a particular match 
    '''
    team_1_vig_incl_prob = compute_vig_implied_probability(odds_team_1)
    team_2_vig_incl_prob = compute_vig_implied_probability(odds_team_2)

    no_vig_prob_team_1 = team_1_vig_incl_prob / (team_1_vig_incl_prob + team_2_vig_incl_prob)
    no_vig_prob_team_2 = team_2_vig_incl_prob / (team_1_vig_incl_prob + team_2_vig_incl_prob)
        
    return (no_vig_prob_team_1, no_vig_prob_team_2)

def compute_return_on_bet(odds: int) -> float: 
    '''
        computes how much a one unit bet would win if the returns hit 
    '''

    # negative odds imply that you are the favourite
    if odds < 0: 
        return 100 / abs(odds)
    else:
        return odds / 100

def compute_positive_ev_odds(novig_prob: float) -> int:
    '''
        computes the minumum betting threshold needed based on the novig prob for the bet to reach positive expected value
    '''
    if novig_prob == 0:
        return np.NaN
    break_even_return = (1- novig_prob) / novig_prob
    if break_even_return < 1: 
        return math.ceil(-1 * 100 / break_even_return)
    else:
        return math.ceil(break_even_return * 100)


def determin_arbitrage_opps(odds1: int, odds2: int) -> bool: 
    '''
        determines whether the pair of odds provide an arbitrage opportunity 
    '''
    return compute_vig_implied_probability(odds1) + compute_vig_implied_probability(odds2) < 1

def compute_expected_return(odds: int, novig_prob: float) -> float: 
    '''
        given the implied no vig probability and corresponding odds compute the expected return from the bet 
    '''

    if odds < 0: 
        return 100 / abs(odds) * novig_prob - (1- novig_prob)
    else:
        return odds / 100 * novig_prob - (1- novig_prob)

def compute_arbitrage_optimization(odd1: int, odd2: int) -> float:
    '''
        computes the amount to distribute between two bets if an arbitrage opportunity exists 
        assuming betting with a single unit
    '''

    dec_odd1 = 1 + compute_return_on_bet(odd1) 
    dec_odd2 = 1 + compute_return_on_bet(odd2) 
    return 1 / (dec_odd1 / dec_odd2 + 1)

def compute_arbitrage_optimization(odd1: int, odd2: int) -> float:
    '''
        computes the amount to distribute between two bets if an arbitrage opportunity exists 
        assuming betting with a single unit
    '''

    dec_odd1 = 1 + compute_return_on_bet(odd1) 
    dec_odd2 = 1 + compute_return_on_bet(odd2) 
    return 1 / (dec_odd1 / dec_odd2 + 1)

def compute_arbitrage_profit(odd1: int, odd1_allocation: float, odd2: int, odd2_allocation: float) -> Tuple[float, float]:
    '''
        computes the range of profit in an arbitrage opportunity 
    '''

    return_odd1 = compute_return_on_bet(odd1) 
    return_odd2 = compute_return_on_bet(odd2) 
    
    profit = return_odd1 * odd1_allocation - odd2_allocation
    return profit