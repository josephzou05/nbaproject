from nba_api.stats.endpoints import playergamelog, teamgamelogs, commonplayerinfo
from nba_api.stats.static import players, teams
import pandas as pd
import logging
import sys

logging.basicConfig(level=logging.INFO, format='%(message)s')

def getPlayerID(playerName):
    matchingPlayers = []
    for player in players.get_active_players():
        if playerName.lower() in player['full_name'].lower():
            matchingPlayers.append(player)

    if not matchingPlayers:
        raise ValueError(f"No active player found with the name '{playerName}'.")

    if len(matchingPlayers) > 12:
        print("Too many results found. Showing the first 12 matches:")
        matchingPlayers = matchingPlayers[:12]

    if len(matchingPlayers) > 1:
        print("\nMultiple active players found:")
        for idx, p in enumerate(matchingPlayers, 1):
            print(f"{idx}. {p['full_name']}")
        choice = input("Enter the number of the player you want: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(matchingPlayers):
            selected = matchingPlayers[int(choice) - 1]
            return selected['id'], selected['full_name']
        else:
            raise ValueError("Invalid selection. Please try again.")
    else:
        return matchingPlayers[0]['id'], matchingPlayers[0]['full_name']

def getPlayerData(playerName, season="2024-25"):
    playerID, fullName = getPlayerID(playerName)
    logging.info(f"\nFetching game logs for: {fullName}")
    gameLog = playergamelog.PlayerGameLog(
        player_id=playerID, 
        season=season, 
        season_type_all_star="Regular Season"  # Correct parameter for PlayerGameLog
    )
    dataFrame = gameLog.get_data_frames()[0]
    return dataFrame, fullName, playerID

def getTeamIdByAbbreviation(abbreviation):
    nbaTeams = teams.get_teams()
    teamId = None
    for team in nbaTeams:
        if team['abbreviation'] == abbreviation:
            teamId = team['id']
            break
    return teamId

def findTeamName(teamID):
    nbaTeams = teams.get_teams()
    teamName = None
    for team in nbaTeams:
        if team['id'] == teamID:
            teamName = team['full_name']
            break
    return teamName

def getOpponentTeamId(dataFrame):
    opponentAbbreviations = dataFrame['MATCHUP'].apply(lambda x: x.split(' ')[-1]).unique()
    opponentTeamIds = []
    for abbrev in opponentAbbreviations:
        teamID = getTeamIdByAbbreviation(abbrev)
        if teamID:
            opponentTeamIds.append(teamID)
    if not opponentTeamIds:
        print("No opponent teams found in the game logs.")
        return None
    print("\nRecent Opponent Teams:")
    uniqueOpponents = list(set(opponentTeamIds))
    for idx, teamID in enumerate(uniqueOpponents, 1):
        teamName = findTeamName(teamID)
        print(f"{idx}. {teamName} ({teamID})")
    choice = input("Choose an opponent team number for strength analysis (or press Enter to skip): ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(uniqueOpponents):
        return uniqueOpponents[int(choice) - 1]  # Return Team ID
    return None


def getOpponentTeamStats(teamID, rankings, season="2024-25", numGames=5):
    # Fetch recent team game logs
    logs = teamgamelogs.TeamGameLogs(
        team_id_nullable=teamID, 
        season_nullable=season, 
        season_type_nullable="Regular Season"  # Correct parameter for TeamGameLogs
    )
    dataFrame = logs.get_data_frames()[0]
    
    if dataFrame.empty:
        return None

    numericStats = ['PTS', 'REB', 'AST', 'STL', 'BLK']
    teamGames = dataFrame[numericStats].head(numGames).apply(pd.to_numeric, errors='coerce')
    
    teamAvg = teamGames.mean()
    
    teamRankings = {stat: rankings[stat].get(teamID, 'N/A') for stat in numericStats}
    
    teamAvg = teamAvg.round(1).to_dict()
    teamAvg.update({f"{stat}_RANK": rank for stat, rank in teamRankings.items()})
    
    return teamAvg

def getLeagueTeamRankings(season="2024-25"):
    logging.info("\nFetching league-wide team statistics for rankings...")
    logs = teamgamelogs.TeamGameLogs(
        season_nullable=season, 
        season_type_nullable="Regular Season"  # Correct parameter for TeamGameLogs
    )
    dataFrame = logs.get_data_frames()[0]
    
    aggregated = dataFrame.groupby('TEAM_ID').agg({
        'PTS': 'mean',
        'REB': 'mean',
        'AST': 'mean',
        'STL': 'mean',
        'BLK': 'mean'
    }).reset_index()
    
    stats = ['PTS', 'REB', 'AST', 'STL', 'BLK']
    rankings = {}
    for stat in stats:
        aggregated[f'{stat}_RANK'] = aggregated[stat].rank(ascending=False, method='min')
        rankings[stat] = dict(zip(aggregated['TEAM_ID'], aggregated[f'{stat}_RANK']))
    
    logging.info("League-wide team rankings calculated.")
    return rankings

def calculateAverages(dataFrame, numGames=5):
    stats = ['PTS', 'REB', 'AST', 'STL', 'BLK']
    stats = [stat for stat in stats if stat in dataFrame.columns]
    dataFrame[stats + ['MIN']] = dataFrame[stats + ['MIN']].apply(pd.to_numeric, errors='coerce')
    avgMinutes = dataFrame['MIN'].mean()
    
    def weightGame(row):
        if row['MIN'] < 0.7 * avgMinutes:
            return 0.5
        elif row['MIN'] > 0.85 * avgMinutes:
            return 1.5
        return 1.0
    
    dataFrame['WEIGHT'] = dataFrame.apply(weightGame, axis=1)
    recentGames = dataFrame.head(numGames)
    weightedAvg = (recentGames[stats].multiply(recentGames['WEIGHT'], axis=0)).sum() / recentGames['WEIGHT'].sum()
    p = weightedAvg.get('PTS', 0)
    r = weightedAvg.get('REB', 0)
    a = weightedAvg.get('AST', 0)
    p_r = p + r
    p_a = p + a
    r_a = r + a
    p_r_a = p + r + a
    return {
        'PTS': round(p, 1), 'REB': round(r, 1), 'AST': round(a, 1),
        'STL': round(weightedAvg.get('STL', 0), 1), 'BLK': round(weightedAvg.get('BLK', 0), 1),
        'P+R': round(p_r, 1), 'P+A': round(p_a, 1), 'R+A': round(r_a, 1), 'P+R+A': round(p_r_a, 1)
    }

from nba_api.stats.endpoints import commonteamroster

def getPlayerPosition(playerID, season="2024-25"):
    try:
        info = commonplayerinfo.CommonPlayerInfo(player_id=playerID)
        dataFrame = info.get_data_frames()[0]
        positionFull = dataFrame['POSITION'][0].strip()
        
        positionMap = {
            'G': 'G',
            'SG': 'SG',
            'Shooting Guard': 'SG',
            'SF': 'SF',
            'Shooting Forward': 'SF',
            'PF': 'PF',
            'Power Forward': 'PF',
            'C': 'C',
            'Center': 'C',
            '': '',
            None: ''
        }
        
        positionShorthand = positionMap.get(positionFull, '')
        if not positionShorthand:
            if positionFull.upper() in ['G', 'SG', 'SF', 'PF', 'C']:
                positionShorthand = positionFull.upper()
            else:
                positionShorthand = ''
        
        return positionShorthand
    except Exception as e:
        logging.error(f"Error fetching position for player ID {playerID}: {e}")
        return None

def getMatchupDeltas(opponentTeamID, position, season="2024-25"):
    teamName = findTeamName(opponentTeamID)
    if not teamName:
        teamName = "Unknown Team"
    logging.info(f"\nCalculating matchup deltas for position: {position} against {teamName}...")
    allPlayers = players.get_active_players()
    samePositionPlayers = [p for p in allPlayers if p.get('position', '') == position]
    
    deltas = {'PTS': [], 'REB': [], 'AST': [], 'STL': [], 'BLK': []}
    
    if not teamName:
        logging.error("Opponent team name could not be determined.")
        return deltas
    
    for idx, player in enumerate(samePositionPlayers, 1):
        playerID = player['id']
        try:
            gameLog = playergamelog.PlayerGameLog(
                player_id=playerID, 
                season=season, 
                season_type_all_star="Regular Season"  # Correct parameter for PlayerGameLog
            )
            dataFrame = gameLog.get_data_frames()[0]
            if dataFrame.empty:
                continue
            matchupGames = dataFrame[dataFrame['MATCHUP'].str.contains(f"@ {teamName}|vs. {teamName}")]
            if matchupGames.empty:
                continue
            matchupAvg = matchupGames[['PTS', 'REB', 'AST', 'STL', 'BLK']].mean()
            seasonAvg = dataFrame[['PTS', 'REB', 'AST', 'STL', 'BLK']].mean()
            delta = matchupAvg - seasonAvg
            for stat in deltas.keys():
                deltas[stat].append(delta.get(stat, 0))
        except Exception as e:
            logging.error(f"Error processing player {player['full_name']}: {e}")
            continue
    
    avgDeltas = {stat: round(pd.Series(values).mean(), 2) if values else 0 for stat, values in deltas.items()}
    logging.info("Matchup deltas calculated.")
    return avgDeltas

def calculateProjectedStats(projectedLine, matchupDeltas):
    projected = {}
    for stat, value in projectedLine.items():
        # Only adjust base stats, not combined stats like P+R
        if stat in matchupDeltas:
            projected[stat] = round(value + matchupDeltas[stat], 1)
        else:
            projected[stat] = value
    return projected

if __name__ == "__main__":
    # Fetch league-wide team rankings once to avoid redundant API calls
    try:
        rankings = getLeagueTeamRankings(season="2024-25")
    except Exception as e:
        logging.error(f"Failed to fetch league team rankings: {e}")
        sys.exit(1)
    
    while True:
        playerName = input("Enter the player's name or last name (or type 'quit' to exit): ").strip()
        if playerName.lower() in ["quit", "exit"]:
            print("Exiting the program.")
            break

        try:
            numGamesInput = input("Enter the number of recent games to analyze (default is 5): ").strip()
            numGames = int(numGamesInput) if numGamesInput.isdigit() else 5

            season = "2024-25"
            dataFrame, fullName, playerID = getPlayerData(playerName, season)

            if dataFrame.empty:
                print(f"No game logs found for {fullName} in the {season} season.")
                continue

            opponentTeam = getOpponentTeamId(dataFrame)
            matchupDeltas = {}
            playerPosition = None

            if opponentTeam:
                opponentStats = getOpponentTeamStats(opponentTeam, rankings, season=season, numGames=numGames)
                if opponentStats is not None:
                    print("\nOpponent Team Recent Averages and Rankings:")
                    for stat, value in opponentStats.items():
                        print(f"{stat}: {value}")
                else:
                    print("Could not fetch opponent team stats.")
                
                playerPosition = getPlayerPosition(playerID, season=season)
                if playerPosition:
                    matchupDeltas = getMatchupDeltas(opponentTeam, playerPosition, season=season)
                    print("\nMatchup Deltas:")
                    for stat, delta in matchupDeltas.items():
                        print(f"{stat}: {delta}")
                else:
                    print("Could not determine player position.")
            else:
                print("No opponent team selected for strength analysis.")

            projectedLine = calculateAverages(dataFrame, numGames=numGames)
            
            if opponentTeam and playerPosition and matchupDeltas:
                projectedLine = calculateProjectedStats(projectedLine, matchupDeltas)
            
            print(f"\nProjected line for {fullName} based on last {numGames} games and matchup:")
            for stat, value in projectedLine.items():
                print(f"{stat}: {value}")
            
            fileName = f"{fullName.replace(' ', '_')}_projected_stats.csv"
            pd.DataFrame([projectedLine]).to_csv(fileName, index=False)
            print(f"Projected stats saved to '{fileName}'.")
        
        except ValueError as e:
            print(e)
        except Exception as e:
            logging.error(f"An error occurred: {e}")
        print("\n--------------------------------------\n")


