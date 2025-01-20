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
        self.region_books = load_yaml_file(current_dir / 'configs/market_regions.yml')
        
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

    def organize_pairs(self,
                       lines_dict: Dict) -> Dict:
        # Split the dictionary into keys and sort by team and point spread
        sorted_keys = sorted(lines_dict.keys(), key=lambda x: (x.split(' ')[-1], x.split(' ')[0]))
        sorted_keys[1], sorted_keys[3] = sorted_keys[3], sorted_keys[1]
        
        # Create a new dictionary to store the ordered pairs
        organized_dict = {key: lines_dict[key] for key in sorted_keys}
        return organized_dict
    
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
                            if len(odds_dict[bet_spread_name]['lines'][bookmaker_name]) > 3: 
                                odds_dict[bet_spread_name]['lines'][bookmaker_name] = self.organize_pairs(odds_dict[bet_spread_name]['lines'][bookmaker_name])

                self.api_tokens_left = odds_response.headers['x-requests-remaining']
                self.api_tokens_used = odds_response.headers['x-requests-used']

                self.latest_ran_home_team = home_team
                self.latest_ran_away_team = away_team
                self.latest_ran_event_id = event_id
                self.latest_ran_commence_time = commence_time
                self.latest_ran_odds = odds_dict
                
                return odds_dict
            
    def output_odds_csv(self,
                        odds_dict: Dict,
                       ) -> pd.DataFrame:
        
        default_column_set = ['event_id','home_team' , 'away_team', 'sportbook', 'event',
                              'event_type_counterpart', 'event_type', 'event_date',
                              'last_updated_at', 'odds', 'no_vig_prob']

        info_columns = ['index','event_id', 'home_team', 'away_team', 
                        'event', 'event_type', 'event_date', 
                        'event_type_counterpart', 'last_updated_at']
        
        rows = []
        for key, value in odds_dict.items():
            last_updated = value['last_updated_at']
            for sportsbook, odds in value['lines'].items():
                bet_counter = 0
                for bet_type, odd in odds.items():
                    row = {
                        'event_id': self.latest_ran_event_id,
                        'home_team': self.latest_ran_home_team,
                        'away_team': self.latest_ran_away_team,
                        'sportbook': sportsbook,
                        'event': key,
                        'event_type': bet_type, 
                        'event_type_counterpart': None,
                        'event_date': self.latest_ran_commence_time,
                        'last_updated_at': last_updated,
                        'odds': odd,
                        'no_vig_prob': None
                    }
                    if bet_counter == 0: 
                        stored_bet_type = bet_type
                        stored_odd = odd
                        rows.append(row)
                    else:
                        odd_1, odd_2 = compute_no_vig_probabilities(stored_odd, odd)
                        prior_row = rows.pop()
                        prior_row['event_type_counterpart'] = bet_type
                        prior_row['no_vig_prob'] = odd_1

                        row['event_type_counterpart'] = stored_bet_type
                        row['no_vig_prob'] = odd_2
                    
                        rows.append(prior_row)
                        rows.append(row)
                        
                        bet_counter = -1 

                    bet_counter+=1
                    
                    
                                    
        odds_df = pd.DataFrame(columns = default_column_set, data = rows)

        odds_df = odds_df.pivot_table(
            index=['event_id', 'home_team', 'away_team', 'event', 'event_type', 
                   'event_type_counterpart', 'event_date', 'last_updated_at'],
            columns= 'sportbook',
            values=["odds", "no_vig_prob"]).reset_index()
        
        odds_df['avg_odds'] =  odds_df['odds'].mean(axis = 1)
        odds_df['best_odds'] = odds_df['odds'].max(axis = 1)
        odds_df['sportsbook_w_best_odds'] = odds_df['odds'].idxmax(axis = 1)
        odds_df['avg_no_vig_odds'] = odds_df['no_vig_prob'].mean(axis = 1 )
        odds_df['num_sportsbooks'] = odds_df['odds'].notnull().sum(axis = 1)

        odds_df = odds_df.drop('no_vig_prob', axis = 1)
        
        odds_df.columns = odds_df.columns.map(lambda x: f"{x[1]}" if x[1] else x[0])

        odds_df['min_odds_needed_positive_ev'] = odds_df['avg_no_vig_odds'].apply(compute_positive_ev_odds)

        odds_df['ev_pct']= odds_df.apply(lambda x: compute_expected_return(x['best_odds'], x['avg_no_vig_odds']), 
                                         axis = 1)
        self.latest_ran_df = odds_df

        return odds_df

     def compute_arbitrage_opps(self, odds_df: pandas.DataFrame) ->  pandas.DataFrame:
         counterpart_odds = odds_df.copy()
         counterpart_odds = counterpart_odds[['event','event_type', 'best_odds',
                                              'sportsbook_w_best_odds']].rename(columns = {'event_type': 'event_type_counterpart', 
                                                                                           'best_odds': 'counterpart_event_best_odds',
                                                                                           'sportsbook_w_best_odds': 'counterpart_sportsbook_w_best_odds'})
        
        odds_df = odds_df.set_index(['event', 
                                     'event_type_counterpart']).join(counterpart_odds.set_index(['event', 
                                                                                                 'event_type_counterpart']), how = 'left').reset_index()


        odds_df['arbitrage_ind'] =  odds_df[['best_odds','counterpart_event_best_odds']].apply(lambda x: determin_arbitrage_opps(x['best_odds'], 
                                                                                                                                 x['counterpart_event_best_odds']),
                                                                                               axis = 1)
        self.latest_ran_df = odds_df
        return odds_df

        


         

        

        