import requests
import re
import time
import os
import copy
import pandas as pd
import datetime
from .helper import *
from typing import Dict, List, Tuple, Union
from pathlib import Path

api_source = 'https://api.the-odds-api.com/v4/sports'
ODDS_FORMAT = 'american' # decimal | american
DATE_FORMAT = 'iso' # iso | unix
SPORT = 'upcoming' # use the sport_key from the /sports endpoint below, or use 'upcoming' to see the next 8 games across all sports
REGIONS = 'us,us2' # uk | us | us2 | eu | au Multiple can be specified if comma delimited
current_dir = Path(os.path.dirname(__file__))

class OddsAPI:
    
    """OddsAPI class
    
    This class is a essentially a wrapper around https://the-odds-api.com; we will be using this as the primary source for pulling data and identifying market inefficiencies.

    To access the the-odds-api, you'd need to get an api-key. The volume of requests per month will vary based on the plan selected.
    """
    def __init__(self, 
                 api_key: str, 
                 api_source = api_source,
                 odds_format = ODDS_FORMAT,
                 date_format = DATE_FORMAT,
                 region = REGIONS):
        self.api_key = api_key
        self.source = api_source
        self.odds_format = odds_format
        self.date_format = date_format
        self.region = REGIONS
        self.league_config =  load_yaml_file(current_dir / 'configs/sports_leagues.yml')
        self.betting_markets = load_yaml_file(current_dir / 'configs/odds_api_markets.yml')
        
    def get_upcoming_matches(self,
                             sport: str,
                            ) -> Union[Dict, None]:

        url_link = f'https://api.the-odds-api.com/v4/sports/{sport}/events?apiKey={self.api_key}'
        odds_response = requests.get(
            url_link,
            params={
                'api_key': self.api_key,
                'regions': self.region,
                'oddsFormat': self.odds_format,
                'dateFormat': self.date_format,
            })

        if odds_response.status_code != 200:
            print(f'Failed to get sports: status_code {odds_response.status_code}, response body {odds_response.text}')
        else: 
            games_dict = {}
            for item in odds_response.json():
                game_id = item['id']
                games_dict[game_id] = {}
                games_dict[game_id]['sport_key'] = item['sport_key']
                games_dict[game_id]['sport_title'] = item['sport_title']
                games_dict[game_id]['commence_time'] = item['commence_time']
                games_dict[game_id]['home_team'] = item['home_team']
                games_dict[game_id]['away_team'] = item['away_team']
                
            self.api_tokens_left = odds_response.headers['x-requests-remaining']
            self.api_tokens_used = odds_response.headers['x-requests-used']
            return games_dict
    def get_odds(self,
                 sport: str, 
                 event_id: str,
                 market: Union[str, List[str]],
                 save_odds = True) -> Union[Dict, None]: 
            if type(market) == list: 
                market_string = ','.join(market)
            else: 
                market_string = market
            url_link = f'https://api.the-odds-api.com/v4/sports/{sport}/events/{event_id}/odds?apiKey={self.api_key}&markets={market_string}'
            odds_response = requests.get(
                url_link,
                params={
                    'api_key': self.api_key,
                    'regions': self.region,
                    'oddsFormat': self.odds_format,
                    'dateFormat': self.date_format,
                }
            )
            if odds_response.status_code != 200:
                print(f'Failed to get sports: status_code {odds_response.status_code}, response body {odds_response.text}')
            else: 
                odds_response_json = odds_response.json()
                game_id = odds_response_json['id']
                sport_key = odds_response_json['sport_key']
                commence_time = odds_response_json['commence_time']
                home_team = odds_response_json['home_team']
                away_team = odds_response_json['away_team']
                bookmakers = odds_response_json['bookmakers']
                odds_dict = {}
                for bookmaker in bookmakers:
                    bookmaker_name = bookmaker['key']
                    markets = bookmaker['markets']
                    for market in markets:
                        market_key = market['key']
                        updated_time = market['last_update']
                        market_outcomes = market['outcomes']
                        for market_outcome in market_outcomes:
                            market_name = market_outcome['name']
                            market_description = market_outcome['description'] if 'description' in market_outcome else ''
                            market_point_abs = abs(market_outcome['point']) if 'point' in market_outcome else ''
                            market_point = market_outcome['point'] if 'point' in market_outcome else ''
                            bet_spread_name = "_".join(map(str, [market_key, 
                                                                 market_description, 
                                                                 market_point_abs]))
                            market_price = market_outcome['price']
                            if bet_spread_name not in odds_dict:
                                odds_dict[bet_spread_name] = {}
                                odds_dict[bet_spread_name]['lines'] = {}
                            market_name_for_dict = f'{market_name} {market_point}'
                            if bookmaker_name not in odds_dict[bet_spread_name]['lines']:
                                odds_dict[bet_spread_name]['lines'][bookmaker_name] = {}
                            odds_dict[bet_spread_name]['last_updated_at'] = updated_time
                            odds_dict[bet_spread_name]['lines'][bookmaker_name][market_name_for_dict] = market_price

                
                self.api_tokens_left = odds_response.headers['x-requests-remaining']
                self.api_tokens_used = odds_response.headers['x-requests-used']

                self.latest_ran_odds = odds_dict
                
                return odds_dict

    def compute_no_vig_odds(self,
                            odds_dict: Dict,
                           ) -> Dict:
        prob_dict = copy.deepcopy(odds_dict)
        for key, value in odds_dict.items():
            for line_key, odds in value['lines'].items():
                odds_items = list(odds.items())
                odds_line_1 = odds_items[0][0]
                odds_line_2 = odds_items[1][0]
                odds_value_1 = odds_items[0][1]
                odds_value_2 = odds_items[1][1]
                odd_1, odd_2 = compute_no_vig_probabilities(odds_value_1, odds_value_2)
                
                prob_dict[key]['lines'][line_key][odds_line_1] = odd_1
                prob_dict[key]['lines'][line_key][odds_line_2] = odd_2

        self.latest_computed_no_vig_odds = prob_dict

        return prob_dict
        
    def compute_expected_return(self,
                                odds_dict: Dict,
                                prob_dict: Dict
                           ) -> Dict:
        expected_return_dict = copy.deepcopy(odds_dict)
        for key, value in odds_dict.items():
            for line_key, odds in value['lines'].items():
                odds_items = list(odds.items())
                odds_line_1 = odds_items[0][0]
                odds_line_2 = odds_items[1][0]
                return_value_1 = compute_return_on_bet(odds_items[0][1])
                return_value_2 = compute_return_on_bet(odds_items[1][1])

                prob_1 = prob_dict[key]['lines'][line_key][odds_line_1] 
                prob_2 = prob_dict[key]['lines'][line_key][odds_line_2]

                ev_1 = prob_1 * return_value_1 - prob_2
                ev_2 = prob_2 * return_value_2 - prob_1

                expected_return_dict[key]['lines'][line_key][odds_line_1] = ev_1
                expected_return_dict[key]['lines'][line_key][odds_line_2] = ev_2
                
        self.latest_expected_return = expected_return_dict

        return expected_return_dict
            
        
        

        