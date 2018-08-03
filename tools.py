#! /usr/bin/python
#
# tools.py - May 2013 - Jon Culver
#
# Functions for performing various administration tasks
#
import ff
import ffparser
import ffdb
import logging

##############
# PARAMETERS #
##############

    
###############
# FUNCTIONS   #
###############

def printlog (string, log=None):
    """ Log a message to the given buffer or print it """
    logging.debug(string)
    if log != None:
        log.append(string)
    else:
        print(string)

def update_player_scores (season=None, log=None, pos=None):
    """
    Update scores for all players in the database.
     Argument: log - if specified then messages will be added to this array
               pos - if specified then only scores for this player will be 
                     updated
    """
    if season == None:
        year   = ffdb.FFDBSeason.current_season()
        season = ffdb.FFDBSeason.load(year)
    try:
        parser = ffparser.FFParser(season)
        result = parser.parse_player_list()
    except Exception as e:
        printlog("Failed to parse player list: {}".format(str(e)), log)
        raise e
    else:
        printlog(result, log)


def update_team_scores (season=None, log=None):
    """ 
    Update the scores for all teams and the players in those teams
    """
    year = ffdb.FFDBSeason.current_season()
    if season == None:
        season = ffdb.FFDBSeason.load(year)
    week = season.current_week()

    # Get a list of teams and create dictionaries for the new points they've
    # scored and missed
    query = ffdb.FFDBTeam.query().filter(ffdb.FFDBTeam.year==year)
    teams = []
    new_scored = {}
    new_missed = {}
    for team in query:
        teams.append(team)
        new_scored[team.userid] = 0
        new_missed[team.userid] = 0
        
    # Update the scores for all players in all teams
    query = ffdb.FFDBTeamPlayer.query().filter(ffdb.FFDBTeamPlayer.year==year)
    for player in query:
        update = False
        # Temporary code to remove leading whitespace from club strings
        if player.club != player.club.strip():
            player.club = player.club.strip()
            update = True
        if player.current_club != player.current_club.strip():
            player.current_club = player.current_club.strip()
            update = True
        old_score = player.get_total_points()
        old_miss = player.get_total_missed()
        player.update_score()
        new_score = player.get_total_points()
        new_miss = player.get_total_missed()
        if player.userid not in new_scored:
            # Handle the hopefully not-to-be-repeated case where user error 
            # leaves a TeamPlayer object in the database without a 
            # corresponding team
            printlog("UserID not recognised for {}".format(str(player)), log) 
        elif old_score != new_score:
            printlog("Updated score {} -> {} for {}".format(old_score, 
                                                            new_score,
                                                            str(player)), log)
            new_scored[player.userid] += (new_score - old_score)
            update = True
        elif old_miss != new_miss:
            printlog("Updated missed {} -> {} for {}".format(old_miss,
                                          new_miss, str(player)), log)
            new_missed[player.userid] += (new_miss - old_miss)
            update = True
        if update:
            player.save()

    # Now sort the teams by their total score including the new scores
    def by_total_score (team):
        """ Sort function for sorting by total score """
        return team.get_total_score() + new_scored[team.userid]

    teams.sort(key=by_total_score, reverse=True)

    # Finally update the teams with their new score and position in the league
    for i, team in enumerate(teams):
        printlog("Team for {} scored {}, missed {}, position {}".format(
                     team.manager, new_scored[team.userid],
                     new_missed[team.userid], i), log)
        team.set_points_and_pos(week, new_scored[team.userid],
                                new_missed[team.userid], i)
        team.save()



def weekly_update (season=None, log=None):
    """ 
    Perform all weekly updates. This should be run at the start of the
    week. 
    """
    year = ffdb.FFDBSeason.current_season()
    if season == None:
        season = ffdb.FFDBSeason.load(year)
    week = season.current_week()
    printlog("Performing update for week {}".format(week), log)

    # Update the squad numbers for all players in all teams
    query = ffdb.FFDBTeamPlayer.query().filter(ffdb.FFDBTeamPlayer.year==year)

    for player in query:
        # If this player hasn't been updated yet this week then update the
        # squad number. 
        if len(player.weeks) < week + 1:
            # Only print if something changed but update anyway to create the
            # entry in the weeks array.
            if player.get_current_squad_num() != player.get_next_squad_num():
                printlog("Updating squad num {} -> {} for {}".format(
                         player.get_current_squad_num(),
                         player.get_next_squad_num(), str(player)), log)
            player.update_squad_num(week)
            assert len(player.weeks) == week + 1
            player.save()

    # Now update the fixtures for all clubs
    parser=ffparser.FFParser(season)
    parser.parse_fixtures()
    printlog("Fixtures updated", log)

def clear_teamplayer_scores (season=None, log=None):
    """
    Move all points scored by every player in everyone's team to 'missed' and
    reset the team scores appropriately. This fixes up problems that occur if
    the auction takes place after the season has started.
    """
    year = ffdb.FFDBSeason.current_season()
    if season == None:
        season = ffdb.FFDBSeason.load(year)

    # Find all the TeamPlayer entries and move all their points to be missed
    query = ffdb.FFDBTeamPlayer.query().filter(ffdb.FFDBTeamPlayer.year==year)

    for player in query:
        for week in player.weeks:
            week.total_missed += week.total_points
            week.total_points = 0
        player.save()

    # Find all the Team entries and reset all their scores
    query = ffdb.FFDBTeam.query().filter(ffdb.FFDBTeam.year==year)
    for team in query:
        for week in team.weeks:
            week.total_missed += week.total_points
            week.total_points = 0
        team.save()




def set_player_score (player_key, new_score, week=None, log=None):
    """ Set the total score for a player. Used for testing purposes """
    year = ffdb.FFDBSeason.current_season()

    if week == None:
        season = ffdb.FFDBSeason.load(year)
        week = season.current_week()
    
    playerList = ff.FFPlayerList(year=year,player_key="oscar")
    player = playerList.find_player(player_key)
    if player == None:
        printlog("Unable to find player {}".format(player_key))
    else:
        printlog("Setting score for {} in week {} from {} to {}".format(
                            player.name, week, player.total_score, new_score))

    player.db_entry.set_total_score(week, new_score)
    player.db_entry.save()

def remove_all_players (year):
    """ 
    Remove all player entries for a particular year from the data store. Used
    to clean up old seasons manually.
    """
    player_list = ff.FFPlayerList(year)
    removed = 0
    for player in player_list:
        player.db_entry.key.delete()
        removed += 1

    printlog("Removed {} players for season {} from the datastore".format(
             removed, year)) 

def set_player_score_week (player_key, week, score):
    """
    Set the score for a player in a given week. This does not update anything
    except the player entry itself.

    Arguments:
        player_key:
            The player to update
        week:
            The week to update
        score:
            The new score to set

    """
    year = ffdb.FFDBSeason.current_season()
    player = ff.FFPlayerList(year, player_key=player_key).find_player(
                                                player_key=player_key)
    if player == None:
        printlog("Unable to find player '{}'".format(player_key))
    else:
        # Update the player score for the week. The remaining data should be 
        # fine.
        player.db_entry.week_scores[week] = score
        player.db_entry.save()
        printlog("Updated score for {} in week {} to {}".format(player_key,
                                                                week, score))



###############
# MAIN SCRIPT #
###############

if __name__ == '__main__':
    update_season()
