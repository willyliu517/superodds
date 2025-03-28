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
home_dir = Path(os.path.expanduser("~"))
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
        self.odds_set = load_yaml_file(current_dir / 'configs/odds_set.yml')
        
    def output_game_dict(self,
                         odds_response: Dict,
                         historical_ran_time = None
                        ) -> Union[Dict, None]:
        games_dict = {}
        if not historical_ran_time:
            historical_ran_time = datetime.datetime.now(datetime.timezone.utc)
            # Convert to string in ISO 8601 format
            dt_string = historical_ran_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        dt_string = historical_ran_time
        for item in odds_response:
            game_id = item['id']
            games_dict[game_id] = {}
            games_dict[game_id]['sport_key'] = item['sport_key']
            games_dict[game_id]['sport_title'] = item['sport_title']
            games_dict[game_id]['commence_time'] = item['commence_time']
            games_dict[game_id]['home_team'] = item['home_team']
            games_dict[game_id]['away_team'] = item['away_team']
            games_dict[game_id]['ran_time'] = dt_string
            
        self.latest_ran_game_dict = games_dict
        
        return games_dict

    def output_game_odds(self, 
                         odds_response: Dict) -> Dict:
        
        odds_response_json = odds_response
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

        self.latest_ran_home_team = home_team
        self.latest_ran_away_team = away_team
        self.latest_ran_event_id = game_id
        self.latest_ran_commence_time = commence_time
        self.latest_ran_odds = odds_dict
        
        return odds_dict
           
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
            self.api_tokens_left = odds_response.headers['x-requests-remaining']
            self.api_tokens_used = odds_response.headers['x-requests-used']
            return self.output_game_dict(odds_response = odds_response.json())

    def get_historical_matches(self,
                             sport: str,
                             date: str, 
                             hour_of_day = '12:00:00'
                            ) -> Union[Dict, None]:
        historical_url_request = f'https://api.the-odds-api.com/v4/historical/sports/{sport}/odds?regions=us&oddsFormat=american&apiKey={self.api_key}&date={date}T{hour_of_day}Z'
        odds_response = requests.get(historical_url_request)
        
        if odds_response.status_code != 200:
            print(f'Failed to get sports: status_code {odds_response.status_code}, response body {odds_response.text}')
        else: 
            self.api_tokens_left = odds_response.headers['x-requests-remaining']
            self.api_tokens_used = odds_response.headers['x-requests-used']
            ran_time = f'{date}T{hour_of_day}Z'
            self.latest_historical_ran_time = ran_time
            return self.output_game_dict(odds_response.json()['data'], historical_ran_time = ran_time)

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
                 market: Union[str, List[str]]) -> Union[Dict, None]: 
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
                self.api_tokens_left = odds_response.headers['x-requests-remaining']
                self.api_tokens_used = odds_response.headers['x-requests-used']
                self.latest_ran_markets = market 
                
                return self.output_game_odds(odds_response = odds_response.json())
                
    def get_historical_odds(self, 
                        sport: str, 
                        event_id: str,
                        market: Union[str, List[str]],
                        datestr: str) -> Union[Dict, None]: 
        
        if type(market) == list: 
            market_string = ','.join(market)
        else: 
            market_string = market
            
        historical_url_request = f'https://api.the-odds-api.com/v4/historical/sports/{sport}/events/{event_id}/odds?apiKey={self.api_key}&date={datestr}&regions={self.region}&markets={market_string}'
        odds_response = requests.get(
                historical_url_request,
                params={
                    'oddsFormat': self.odds_format
                })
        if odds_response.status_code != 200:
                print(f'Failed to get sports: status_code {odds_response.status_code}, response body {odds_response.text}')
        else: 
            self.historical_event_previous_timestamp = odds_response.json()['timestamp']
            self.historical_event_recently_ran_timestamp = odds_response.json()['previous_timestamp']
            self.historical_event_next_timestamp = odds_response.json()['next_timestamp']
            self.latest_ran_markets = market 

            self.api_tokens_left = odds_response.headers['x-requests-remaining']
            self.api_tokens_used = odds_response.headers['x-requests-used']
            
            return self.output_game_odds(odds_response = odds_response.json()['data'])
            
    def output_odds_csv(self,
                        odds_dict: Dict,
                       ) -> pd.DataFrame:
        
        default_column_set = ['event_id','home_team' , 'away_team', 'sportbook', 'event',
                              'event_type_counterpart', 'event_type', 'event_date',
                              'last_updated_at', 'odds', 'no_vig_prob']

        info_columns = ['index','event_id', 'home_team', 'away_team', 
                        'event', 'event_type', 'event_date', 
                        'event_type_counterpart', 'last_updated_at']
        
        agg_dict = {}
        for key, value in odds_dict.items():
            last_updated = value['last_updated_at']
            for sportsbook, odds in value['lines'].items():
                bet_counter = 0
                for bet_type, odd in odds.items():
                    counter_event = get_counter_event_name(bet_type, 
                                                           home_team = self.latest_ran_home_team, 
                                                           away_team = self.latest_ran_away_team)
                    event_unique_id = f'{self.latest_ran_event_id}_{sportsbook}_{key}_{bet_type}_{last_updated}'
                    counter_event_unique_id = f'{self.latest_ran_event_id}_{sportsbook}_{key}_{counter_event}_{last_updated}'
                    row = {
                        'event_id': self.latest_ran_event_id,
                        'home_team': self.latest_ran_home_team,
                        'away_team': self.latest_ran_away_team,
                        'sportbook': sportsbook,
                        'event': key,
                        'event_type': bet_type, 
                        'event_type_counterpart': counter_event,
                        'event_date': self.latest_ran_commence_time,
                        'last_updated_at': last_updated,
                        'odds': odd,
                        'no_vig_prob': None
                    }
                    agg_dict[event_unique_id] = row
                    if bet_counter > 0: 
                        if counter_event_unique_id in agg_dict: 
                            odd_1, odd_2 = compute_no_vig_probabilities(agg_dict[event_unique_id]['odds'],
                                                                        agg_dict[counter_event_unique_id]['odds'])
                            agg_dict[event_unique_id]['no_vig_prob'] = odd_1
                            agg_dict[counter_event_unique_id]['no_vig_prob'] = odd_2
                        
                    bet_counter+=1
                    
        odds_df = pd.DataFrame.from_dict(agg_dict, orient='index').reset_index()
        odds_df['event_type_counterpart'] = odds_df['event_type_counterpart'].fillna('Not Available')
        odds_df['no_vig_prob'] = odds_df['no_vig_prob'].fillna(0)

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
        self.latest_ran_timestamp = last_updated

        return odds_df

    def compute_arbitrage_opps(self, odds_df: pd.DataFrame) ->  pd.DataFrame:
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

    def get_all_positive_ev_arbitrage_opps(self, 
                                           event_id: str, 
                                           sport: str, 
                                           market: List[str],
                                           historical_event = False, 
                                           timestamp = None) -> Union[None, 
                                                                      pd.DataFrame, 
                                                                      Tuple[pd.DataFrame, pd.DataFrame]]:
        
        if historical_event:
            if not timestamp: 
                timestamp = self.latest_historical_ran_time
            odds_collection = self.get_historical_odds(
                sport = sport, 
                event_id = event_id,
                market = market,
                datestr = timestamp
            )
        else: 
            odds_collection = self.get_odds(
                sport = sport, 
                event_id = event_id,
                market = market
            )
        
        odds_dataframe = self.output_odds_csv(odds_collection)
        odds_dataframe = self.compute_arbitrage_opps(odds_dataframe)

        positive_ev = odds_dataframe[(odds_dataframe.ev_pct > 0)]
        
        arb_df = odds_dataframe[odds_dataframe.arbitrage_ind == True]
        # If no Positive EV opps are found, no arbitrage will be found 
        if positive_ev.shape[0] == 0:
            print(f'No positive EV opportunities identified for event {event_id}')
            return None
        elif arb_df.shape[0] == 0:
            print(f'No arbitrage opportunities identified for event {event_id}')
            return positive_ev
        else:
            return positive_ev, arb_df
                
    def get_all_odds(self,
                     sport: str,
                     market: List[str],
                     historical_event = False, 
                     date = None, 
                     hour_of_day = None,
                     get_event_prior_to_commence = False,
                     custoff_date = None) -> Union[pd.DataFrame, None]:
        df_list = []
        if historical_event:
            if not date: 
                raise ValueError("`date` and `hour_of_day` must be provided pulling in historical events")

            historical_matches = self.get_historical_matches(
                sport = sport,
                date = date, 
                hour_of_day = hour_of_day)
            
            for event_id, value in historical_matches.items():
                commence_time = value['commence_time']
                fmt = "%Y-%m-%dT%H:%M:%SZ"
                commence_time = datetime.datetime.strptime(commence_time , fmt)
                ran_time = datetime.datetime.strptime(self.latest_historical_ran_time, fmt)
                if get_event_prior_to_commence:
                    if ran_time <= commence_time and commence_time < custoff_date: 

                        print(f'Collecting historical odds for {event_id} at {self.latest_historical_ran_time}')
        
                        odds_collection = self.get_historical_odds(
                            sport = sport, 
                            event_id = event_id,
                            market = market,
                            datestr = self.latest_historical_ran_time
                        )
                    
                        output_df = self.output_odds_csv(odds_collection)
                        df_list.append(output_df)
                else: 
                    print(f'Collecting historical odds for {event_id} at {self.latest_historical_ran_time}')
        
                    odds_collection = self.get_historical_odds(
                        sport = sport, 
                        event_id = event_id,
                        market = market,
                        datestr = self.latest_historical_ran_time
                    )
                
                    output_df = self.output_odds_csv(odds_collection)
                    df_list.append(output_df)
        else: 
            
            upcoming_matches = self.get_upcoming_matches(sport = sport)
            
            for event_id in upcoming_matches.keys():
                print(f'Collecting odds for {event_id} at {self.latest_ran_timestamp}')
                odds_collection = self.get_odds(
                        sport = sport, 
                        event_id = event_id,
                        market = market)
                output_df = self.output_odds_csv(odds_collection)
                df_list.append(output_df)
        
        if df_list: 
            
            result = pd.concat(df_list, ignore_index=True)
        
            self.result_df = result 
        
            return result

    def output_historical_events_across_timestamps(self,
                                                sport: str,
                                                market: List[str],
                                                date = str, 
                                                hour_of_day = '12:00:00',
                                                interval_min = 60,
                                                dir = home_dir
                                               ) -> None:

        fmt = "%Y-%m-%dT%H:%M:%SZ"
        datetime_str = f'{date}T{hour_of_day}Z'
        datetime_var = datetime.datetime.strptime(datetime_str , fmt)
        output_dir = ensure_dir_exists(str(home_dir / sport /f'{sport}_{date}' ))

        #Excludes events that occured after 8am UTC the next day
        date_obj = datetime.datetime.strptime(date, "%Y-%m-%d")
        next_day = date_obj + datetime.timedelta(days=1)
        # Set time to 08:00 AM
        next_day_at_8am = next_day.replace(hour=8, minute=0, second=0)
        
        historcal_df = self.get_all_odds(
             sport = sport,
             market = market,
             historical_event = True, 
             date = date, 
             hour_of_day = hour_of_day,
             get_event_prior_to_commence = True, 
             custoff_date = next_day_at_8am 
        )
        
        date_part = date 
        while historcal_df is not None:
            csv_name = f'{sport}_{date_part}_{datetime_str}.csv'
            print(f'Saving {csv_name} to local')
            historcal_df.to_csv(home_dir / sport / f'{sport}_{date}' / csv_name, index=False)
            datetime_var = datetime_var + datetime.timedelta(minutes = interval_min) 
            datetime_str = datetime_var.strftime("%Y-%m-%dT%H:%M:%SZ")

            date_part, time_part = datetime_str.split("T")

            # Remove the 'Z' from time
            time_part = time_part.rstrip("Z")

            historcal_df = self.get_all_odds(
                                sport = sport,
                                market = market,
                                historical_event = True, 
                                date = date_part, 
                                hour_of_day = time_part,
                                get_event_prior_to_commence = True,
                                custoff_date = next_day_at_8am
                            )

        

        
        
            
        
        
                        

        


         

        

        