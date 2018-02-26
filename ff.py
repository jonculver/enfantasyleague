#! /usr/bin/python
#
# ff.py - May 2013 - Jon Culver
#
# Controller classes which retrieve data from the data store in ffdb.py and 
# prepare it for display on the web site
#

from datetime import datetime
from datetime import timedelta
from datetime import date
from collections import OrderedDict
from random import choice
from itertools import chain 
import re
import logging

import ffdb

from google.appengine.ext import ndb

class TeamError(Exception):
    pass

##############
# Parameters #
##############

STARTING_FUNDS = 100
TEAM_NAMES = ["United", "Hotspur", "Albion", "Rovers", "Athletic", "Rangers"]

##############
# Team       #
##############

class FFTeamPlayer(object):
    """Representation of a player within a team"""

    def __init__ (self, db_entry=None, player=None, team=None, price=0, 
                  name=None, club=None, squad_num=0, instance=0):
        """
        Create a new FFTeamPlayer object. There are 3 options for initialising
        this object:
            1. From a FFDBTeamPlayer object passed in to db_entry (if reading
               from the datastore.)
            2. From a FFPlayer, FFTeam and price (if adding a new player to a
               team). This will create a corresponding datastore entry.
            3. Using the 'name' and 'club' fields (if creating a temporary 
               entry)
        """
        self.db = db_entry
        self.name = name
        self.player_key = name
        self.club = club
        self.current_club = club
        self.pos = "--"
        self.manager = "None"
        self.total_score = 0
        self.total_missed = 0
        self.week_score = 0
        self.week_missed = 0
        self.price = price
        self.squad_num = squad_num
        self.url = ""
        self.in_team = squad_num >= 0 and squad_num < 11
        self.is_sub = squad_num >= 11
        self.fixtures = ""

        if db_entry == None and player != None:
            # Create a new db structure and save it
            self.db              = ffdb.FFDBTeamPlayer()
            self.db.year         = player.year
            self.db.manager      = team.manager
            self.db.userid       = team.userid
            self.db.player_key   = player.player_key
            self.db.name         = player.name
            self.db.instance     = instance
            self.db.club         = player.club
            self.db.current_club = player.club
            self.db.pos          = player.pos
            self.db.price        = price
            self.db.squad_num    = squad_num
            self.db.url          = player.url
            # Update the instance number if this player has already been in
            # the team previously
            for explayer in team.explayers:
                if player.player_key == explayer.player_key:
                    self.db.instance += 1
            # Set the squad number for the current week
            season = ffdb.FFDBSeason.load(team.year)
            self.db.update_squad_num(season.current_week())
            # Save this new item in the data store
            self.db.save()

        if db_entry != None:
            self.name = db_entry.name
            self.player_key = db_entry.player_key
            self.club = db_entry.club
            self.current_club = db_entry.current_club
            self.pos = db_entry.pos
            self.manager = db_entry.manager
            self.price = db_entry.price
            self.total_score = db_entry.get_total_points()
            self.total_missed = db_entry.get_total_missed()
            self.week_score = db_entry.get_week_points()
            self.week_missed = db_entry.get_week_missed()
            self.squad_num = db_entry.get_next_squad_num()
            self.url = db_entry.url
            self.in_team = (db_entry.get_current_squad_num() >= 0 and 
                            db_entry.get_current_squad_num() < 11)
            self.is_sub = db_entry.get_current_squad_num() >= 11

        self.safemgr = FFTeam.mgr_to_safemgr(self.manager)
        # Set the status and reason from the FFplayer object or by looking
        # up the entry in the data store. This is also used to update the
        # current_club field if necessary.
        if player != None and db_entry != None:
            self.status = player.status
            self.reason = player.reason
        elif db_entry == None:
            # This is a temporary entry. Mark as ineligable
            self.status = ffdb.FFDBPlayer.INELIGABLE
            self.reason = "Placeholder"
        else:
            # If we don't have enough informtion to fill in the status and
            # reason then leave them blank for now. They will be filled in
            # later if anyone needs them
            self.status = None
            self.reason = None
 
    def __str__ (self):
        return "{} {}. {} {} {}".format(self.manager, self.squad_num, 
                                        self.pos, self.club, self.name)

    def _find_status_reason (self):
        """
        Look up the status and reason from the player DB entry
        """
        player = ffdb.FFDBPlayer.load(self.db.year, self.player_key)
        if player != None:
            self.status = player.status
            self.reason = player.reason
            # Update the player's current club if necessary.
            if self.db.update_club(player.club):
                self.db.save()

    def week_score_string (self):
        """ 
        Return the week score in the format "(+/-X)" or empty string for 0 
        """
        string = ""
        if self.week_score > 0:
            string = "(+{})".format(self.week_score)
        elif self.week_score < 0:
            string = "({})".format(self.week_score)

        return string

    def get_status (self):
        """
        Return the player status, looking it up if necessary
        """
        if self.status == None:
            self._find_status_reason()
        return self.status

    def get_reason (self):
        """
        Return the player status, looking it up if necessary
        """
        if self.reason == None:
            self._find_status_reason()
        return self.reason

    def status_image (self):
        """ Return the image corresponding to this player's status"""
        if self.status == None:
            self._find_status_reason()
        return "images/{}.png".format(self.status)

    def update_squad_num (self, new):
        """ Update the squad number here and in the database """
        self.squad_num = new
        # If this isn't a null entry then update the DB
        if self.db != None:
            self.db.squad_num = new
            self.db.save()

    def remove_from_db (self):
        """ Remove the database entry for this player """
        if self.db != None:
            self.db.key.delete()
            self.db = None

    def set_fixtures (self, fixtures):
        """ 
        Update the fixtures for this player. This is not done by default
        to avoid incurring a potentially unnecessary database query
        """
        self.fixtures = fixtures

    def get_properties (self):
        """ Return properties of this player as a hash table """
        return ({'name' : self.name,
                 'player_key' : self.player_key,
                 'pos' : self.pos,
                 'club' : self.club,
                 'current_club' : self.current_club,
                 'manager' : self.manager,
                 'price' : self.price,
                 'total_score' : self.total_score,
                 'week_score_str' : self.week_score_string(),
                 'total_missed' : self.week_missed,
                 'week_missed' : self.week_missed,
                 'squad_num' : self.squad_num,
                 'fixtures' : self.fixtures})


class FFTeam(object):
    """Representation of a team within the FF League"""

    # Number of players in a team including subs
    SQUADSIZE=17

    # For each position, list the possible squad numbers in the order in which
    # they should be filled in. Leave numbers which have two possibilities 
    # until last to make the decision about whether or not a new player can
    # be added as simple as possible
    preferred_pos = OrderedDict([(ffdb.FFDBPlayer.GK, [0]),
                                 (ffdb.FFDBPlayer.FB, [1,2]),
                                 (ffdb.FFDBPlayer.CB, [3,4,5]),
                                 (ffdb.FFDBPlayer.M, [6,7,8,5,9]),
                                 (ffdb.FFDBPlayer.S, [10,9])])

    def __init__ (self, year, userid=None, db_entry=None, manager=None, 
                  name=None, position=0, populate=True, create=False):
        """
        Create a new FFTeam object.
        Arguments:
            year - the year to associate this object with
            userid - the user that owns this team. Either this or 'manager'
                     must be specified.
            db_entry - the datastore entry for this team if known. If None then
                       the function will attempt to look it up and otherwise 
                       create a new entry
            manager - the name of the manager. Can be used instead of userid to
                      look up the team, or required if creating a new db entry
            name - the name of the team, only required if creating a new db 
                   entry
            position - the current position of this team in the league
            populate - whether or not to load the players in this team. 
                       (Optimisation to reduce database reads)
            create - whether or not to create a datastore entry if one cannot
                     be found. If this is False and one cannot be found then
                     and exception is raised.
        """
        self.db = db_entry

        if self.db == None and userid != None:
            # Load this team from the data store
            self.db = ffdb.FFDBTeam.load(year, userid)

        if self.db == None and manager != None:
            # Try looking up the team by manager
            query = ffdb.FFDBTeam.query().filter(ndb.AND(
                                              ffdb.FFDBTeam.year==year,
                                              ffdb.FFDBTeam.manager==manager))
            teams = query.fetch(1)

            if len(teams) == 1:
                self.db = teams[0]
            else:
                # The value passed in may be a 'safemgr' which isn't stored in 
                # the DB, and if they differ then the above query will fail.
                # Fall back to querying all teams and looking for a match.
                query = ffdb.FFDBTeam.query().filter(ffdb.FFDBTeam.year==year)
                for team in query:
                    if FFTeam.mgr_to_safemgr(team.manager) == manager:
                        self.db = team
                        break

        if self.db == None and create:
            # No entry in the store either. Create a new one and save it
            self.db = ffdb.FFDBTeam(year=year, userid=userid, manager=manager, 
                                    name=name, funds=STARTING_FUNDS)
            if name == None:
                self.db.name = "{} {}".format(manager, choice(TEAM_NAMES))

            self.db.save()
        elif self.db == None:
            # No entry and not creating one. This isn't allowed.
            raise KeyError("No database entry for userid '{}', "\
                           "mgr '{}'".format(userid, manager))

        #Properties displayed on the website
        self.userid = self.db.userid
        self.year = year
        self.manager = self.db.manager
        self.safemgr = self.mgr_to_safemgr(self.manager)
        self.name = self.db.name
        self.funds = self.db.funds
        self.week_score = self.db.get_week_score()
        self.total_score = self.db.get_total_score()
        self.position = position
        self.players = []
        self.explayers = []

        if populate or create:
            self.populate_players()



    def __str__ (self):
        return str(self.db) + "\n  " + "\n  ".join(
                                      [str(p) for p in self.players])

    def __iter__ (self):
        """ Iterate the players currently in the team including subs """
        for player in self.players:
            yield player

    def allplayers (self):
        """ Iterate through all players including ex-players """
        for player in chain(self.players, self.explayers):
            yield player

    @staticmethod
    def mgr_to_safemgr (manager):
        """ 
        Return the corresponding safemgr string for given manager. This
        function is idempotent and safe to use on safemgr strings too.
        """
        # Create a version of the manager name that only contains alphanumeric
        # characters. This is useful for including in 'id' fields in html for
        # example.
        if manager == None:
            return None
        else:
            return re.sub(r'\W+', '', manager)

    @staticmethod
    def is_sub (squad_num):
        """
        Return True if the squad number corresponds to a substitute
        """
        return squad_num > 10

    @staticmethod
    def valid_position_list (squad_num):
        """
        Return a list of the possible positions that are allowed for a given
        0-based squad number
        """
        pos_list = []
        for k,v in FFTeam.preferred_pos.items():
            if FFTeam.is_sub(squad_num) or squad_num in v:
                pos_list.append(k)
        return pos_list

    def get_properties (self):
        """ Return properties of this team as a hash table """
        return({'manager' : self.manager,
                'safemgr' : self.safemgr,
                'name' : self.name,
                'funds' : self.funds,
                'week_score_str' : self.week_score_string(),
                'total_score' : self.total_score,
                'players' : [p.get_properties() for p in self.players],
                'explayers' : [p.get_properties() for p in self.explayers]})

    def _create_empty_player (self, squad_num):
        return FFTeamPlayer(name="None", club = "NON", squad_num=squad_num)

    def _is_empty (self, player):
        """ 
        Return True if the specified player or squad number is the None player 
        """
        empty = False
        try:
            # Try assuming we have been passed a player object
            empty = player.name == "None"
        except AttributeError:
            # Try assuming a squad number
            empty = self.players[player].name == "None"

        return empty

    def populate_player (self, teamplayer):
        """
        Add a player to this team given a teamplayer object
        """
        # Make sure the team has players in every entry in the squad
        self.fill_squad()

        if teamplayer.manager == self.manager:
            # If the player is in the squad then add them to the right place
            # in the array. Otherwise add to the list of ex-players. Use the
            # next_squad_num so that players in the process of being 
            # transferred out are correctly added to the ex-players list.
            sn = teamplayer.db.get_next_squad_num()
            if sn >= 0 and sn < self.SQUADSIZE:
                assert(self.players[sn].name == "None") 
                self.players[sn] = teamplayer
            else:
                self.explayers.append(teamplayer)

    def fill_squad (self):
        """ Fill any unused spaces in the squad with empty players """
        if len(self.players) < self.SQUADSIZE:
            for i in range(len(self.players), self.SQUADSIZE):
                self.players.append(self._create_empty_player(i))

    def populate_players (self):
        """ Fill in the players and explayers array from a datastore query """
        self.players = []
        self.explayers = []
        
        # Query the players in the team
        query = ffdb.FFDBTeamPlayer.query().filter(ndb.AND(
                                  ffdb.FFDBTeam.year==self.year,
                                  ffdb.FFDBTeam.userid==self.userid))
        
        for player in query:
            entry = FFTeamPlayer(db_entry=player)
            self.populate_player(entry)

        # Make sure the team has players in every entry in the squad
        self.fill_squad()

    def populate_fixtures (self, clubs=None):
        """
        Populate the fixtures for all players in the squad
        """
        # Look up all the clubs if they haven't been provided
        if clubs == None:
            query = ffdb.FFDBClub.query(ffdb.FFDBTeam.year==self.db.year)
            clubs = {club.abr : club for club in query}
            
        for player in self:
            if player.current_club != "NON":
                player.set_fixtures(",".join(clubs[player.current_club].fixtures))

    def week_score_string (self):
        """ 
        Return the week score in the format "(+/-X)" or empty string for 0 
        """
        string = ""
        if self.week_score > 0:
            string = "(+{})".format(self.week_score)
        elif self.week_score < 0:
            string = "({})".format(self.week_score)

        return string

    def update_funds (self, diff):
        """ 
        Add the difference to the funds for this team and update the datastore
        """
        self.funds += diff
        if self.funds < 0:
            self.funds = 0
        self.db.funds = self.funds
        self.db.save()

    def club_free (self, club):
        """
        Return True if there is space in the team for another player from the
        specified club. There is always space for NON players.
        """
        matches = 0
        for p in self.players:
            if p.club == club:
                matches += 1
        return matches < 2 or club == "NON"

    def __sub_free (self, max_squad_num=SQUADSIZE):
        """
        Return True if there is a spare sub space less than specified max
        squad number
        """
        if max_squad_num >11:
            for p in self.players[11:max_squad_num]:
                if self._is_empty(p):
                    return True
        return False

    def _can_swap_two (self, n1, n2):
        """
        Return True if a 2-way swap between two players is valid, False 
        otherwise. The no-op swap is treated as not allowed.
        """
        pos1 = self.players[n1].pos
        pos2 = self.players[n2].pos
        valid = False
        if n1 == n2:
            # Return False for no-op swaps to avoid wasting time doing nothing
            valid = False
        elif pos1 == pos2:
            # If the positions are the same then the swap is valid
            valid = True
        elif ((pos1 == "--" or pos1 in self.valid_position_list(n2)) and 
              (pos2 == "--" or pos2 in self.valid_position_list(n1))):
            # Each position is valid in the location of the other so the swap
            # is valid. (Null entries can be shifted anywhere)
            valid = True

        return valid

    def _find_pivot (self, n1, n2):
        """
        If a 3-way swap between these two positions is possible then return 
        the intermediate position they both swap with. Otherwise return -1
        """
        # Always try swapping the lower of the two positions with the pivot to
        # avoid leaving the pivot in a sub slot during a substitution.
        low = min(n1, n2)
        high = max(n1, n2)
        pivot = -1
        p = self.players
        # Only slots 5 and 9 accept players from multiple positions and are 
        # thus candidates for a 3-way swap
        for temp in [5, 9]:
            if self._can_swap_two(low, temp):
                # Switch positions for the first half of a 3-way swap in order
                # to check if the second half is valid. Change them back
                # afterwards.
                p[low], p[temp] = p[temp], p[low]
                if self._can_swap_two(temp, high):
                    pivot = temp
                p[low], p[temp] = p[temp], p[low]
        return pivot

    def swap_players (self, n1, n2):
        """
        Swap the positions of two players in the team. This may result in a 
        3-way swap if necessary. Raises TeamError on failure.
        """
        def swap_two (s1, s2):
            """ switch position of two players """
            self.players[s1].update_squad_num(s2)
            self.players[s2].update_squad_num(s1)
            self.players[s1], self.players[s2] = self.players[s2], self.players[s1]

        done = False
        if self._can_swap_two(n1, n2):
            # 2-way swap is allowed
            swap_two(n1, n2)
            done = True
        else:
            pivot = self._find_pivot(n1, n2)
            if pivot != -1:
                low = min(n1, n2)
                high = max(n1, n2)
                swap_two(low, pivot)
                swap_two(pivot, high)
                done = True

        if not done:
            raise TeamError(
                     "Swapping players {} ({}) and {} ({}) invalid".format(
                              n1, self.players[n1].pos,
                              n2, self.players[n2].pos))


    def can_swap (self, n1, n2):
        """
        Return true if the players in these positions can be swapped, 
        potentially with the help of a 3rd position
        """
        return self._can_swap_two(n1, n2) or self._find_pivot(n1, n2) != -1

    def can_sub(self, n1, n2):
        """
        Return True if the two numbers given form a valid substitution. i.e.
          - they are a valid swap
          - one is in the team and the other is on the bench
          - neither of them are empty
        """
        return (self.can_swap(n1, n2) and 
                min(n1, n2) < 11 and max(n1, n2) >= 11 and
                not self._is_empty(max(n1,n2)))

    def find_free_squad_num (self, pos, max_squad_num=SQUADSIZE):
        """
        Return the position first free place where a player in this position
        can be added. Raise TeamError if there isn't one.
        """
        squad_num = -1

        # Check if any of the positions in the team are
        # still available
        for i in self.preferred_pos[pos]:
            if self._is_empty(i):
                squad_num = i
                break

        if squad_num == -1:
            # Because positions 5 and 9 can both accept midfielders or another
            # position, try switching any empty CB, M or S slots with 
            # whichever of these are applicable for the position we are adding.
            # (Note that it's possible to construct a scenario where almost
            # any swap may work, e.g. if a player is removed from a CB slot it
            # may be valid to fill that slot with a S by performing a 3-way
            # swap with slot 9. So just try everything and see if it works)
            temp_pos_list = None
            if pos == ffdb.FFDBPlayer.CB:
                temp_pos_list = [5]
            elif pos == ffdb.FFDBPlayer.M:
                temp_pos_list = [5,9]
            elif pos == ffdb.FFDBPlayer.S:
                temp_pos_list = [9]

            if temp_pos_list != None:
                # Try swapping any empty CB, M, S slots with those in the list
                for i in range(3, 11):
                    if self._is_empty(i):
                        for temp_pos in temp_pos_list:
                            try:
                                self.swap_players(i, temp_pos)
                            except TeamError:
                                pass
                            else:
                                squad_num = temp_pos
                                break
                    if squad_num != -1:
                        break

        if squad_num == -1:
            # Failing that try a sub spot
            for i in xrange(11, max_squad_num):
                if self._is_empty(i):
                    squad_num = i
                    break

        if squad_num == -1:
            # Still no good. Not a valid operation
            raise TeamError("No space for {} in team".format(pos))

        return squad_num


    def add_player (self, player, price, max_squad_num=SQUADSIZE, 
                    check_clubs=True):
        """ 
        Add a FFPlayer object to this team. Raises TeamError on failure 
        Arguments:
            player - the FFPlayer object to add
            price - the amount to deduct from funds
            max_squad_num - the maximum squad number this player can have e.g.
                            whether or not he must go in the first 12 for the
                            purposes of the auction.
            check_clubs - whether to verify that the team has space for a 
                          player from this club. It may be allowed to have more
                          than two when, for example, replacing a NON-player
                          with their valid counterpart.
        """

        if self.funds - price < 0 and self.funds - price > -0.1:
            # Weird float issue means that two numbers ostensibly the same do
            # not match and spending all your money is impossible
            self.funds = price

        if self.funds < price:
            raise TeamError("Player costs {} but only {} available".format(
                                     price, self.funds))

        if check_clubs and not self.club_free(player.club):
            raise TeamError("No slots free for club '{}'".format(player.club))

        squad_num = self.find_free_squad_num(player.pos,
                                             max_squad_num=max_squad_num)

        # Check if this player has already been in the team and if so create
        # a new instance
        instance = 0
        while ffdb.FFDBTeamPlayer.load(self.year, self.userid,
                                       player.player_key, instance) != None:
            instance += 1

        # Create a new object and store it in the datastore
        self.players[squad_num] = FFTeamPlayer(player=player, team=self, 
                                               price=price, 
                                               squad_num=squad_num)
        # Update the player to indicate they now belong to this manager
        player.set_manager(self.manager)
        # Update the funds of this manager
        self.update_funds(-price)
        return squad_num

    def remove_player (self, squad_num, undo=False):
        """ 
        Remove a player with the specified squad number from the team.
        Arg: undo - if True then remove the player and refund the money.
                    otherwise move them to the ex-players list
        """
        player = self.players[squad_num]
        if self._is_empty(player):
            # Slot is already empty. Nothing to do
            return
        elif undo:
            self.update_funds(player.price)
            player.remove_from_db()
        else:
            player.update_squad_num(-1)
            self.explayers.append(player)
        self.players[squad_num] = self._create_empty_player(squad_num)

    def get_player (self, player_key):
        """
        Return the entry for the specified player if it exists in the team or
        None otherwise
        """
        for p in self.players:
            if p.player_key == player_key:
                return p
        return None

##############
# League     #
##############


class FFLeague(object):
    """Representation of the current state of the league"""
    def __init__ (self, year, populate_teams=True):
        """
        Create a new league instance, loading all the teams that comprise it
        Arguments:
            populate_teams - whether or not to load the players in each team
        """
        self.year = year
        self.season = ffdb.FFDBSeason.load(year)

        # Initialise the enableUpdates field if it hasn't been set yet.
        if self.season != None and self.season.enableUpdates == None:
            self.season.enableUpdates = 1
            self.season.save()
        
        # Use an ordered dict such that the teams remain in the order we enter
        # them, which will be in decending order of total score
        self.teams = OrderedDict()
        query = ffdb.FFDBTeam.query().order(-ffdb.FFDBTeam.total_score,
                                            -ffdb.FFDBTeam.funds)
        query = query.filter(ffdb.FFDBTeam.year==year)

        for i, team in enumerate(query):
            self.teams[team.manager] = FFTeam(year=year, userid=team.userid,
                                              db_entry=team, position=i+1,
                                              populate=False)

        # Now query all the teamplayers and add them to the respective teams
        # (cuts down on DB queries vs letting each team do this itself).
        if populate_teams:
            query = ffdb.FFDBTeamPlayer.query()
            #.filter(ffdb.FFDBTeamPlayer.year==year)
        
            for dbtp in query:
               tp = FFTeamPlayer(db_entry=dbtp)
               self.teams[tp.manager].populate_player(tp)
            # Fill in any gaps with empty players   
            for team in self.teams.values():
                team.fill_squad()


    def __iter__ (self):
        """ Iterate the teams in this league """
        for team in self.teams.values():
            yield team

    def __str__ (self):
        """ String representation of this league """
        return "League {} contains {} teams".format(self.year, 
                                                    len(self.teams))

    @staticmethod
    def create_season (start, end):
        """ 
        Create a new season object with the given start and end dates. Raises 
        TeamError on error 
        """
        # First check there is no existing league object for the current year
        year = ffdb.FFDBSeason.current_season()
        season = ffdb.FFDBSeason.load(year)
        if season != None:
            raise TeamError("League already exists for year {}".format(year))

        # Make sure the start and end strings are valid
        dates = {start:None, end:None}
        
        for date in dates:
            try:
                dates[date] = ffdb.FFDBSeason.string_to_date(date)
            except (TypeError, ValueError):
                raise TeamError("Invalid date {}".format(date))

        # Make sure the league starts on a Friday
        if dates[start].weekday() != 4:
            raise TeamError("League must start on the Friday before first fixture")

        # Create a new season object
        season = ffdb.FFDBSeason()
        season.year  = year
        season.start = dates[start]
        season.end   = dates[end]
        season.enableUpdates = 1
        season.save()

    @staticmethod
    def club_list (year):
        query = ffdb.FFDBClub.query().filter(ffdb.FFDBTeam.year==year)
        return [club.abr for club in query]

    @staticmethod
    def pos_list ():
        return [ffdb.FFDBPlayer.GK, ffdb.FFDBPlayer.FB, ffdb.FFDBPlayer.CB,
                ffdb.FFDBPlayer.M, ffdb.FFDBPlayer.S]

    def get_team (self, manager=None, userid=None):
        """ 
        Look up a team based on a manager or userid. The manager value 
        may be a safemgr instead
        """
        team = None
        # sufficient to compare safemgr values since we verify that there are
        # no duplicates when creating teams. 
        safemgr = FFTeam.mgr_to_safemgr(manager)
        for v in self.teams.values():
            if safemgr != None and safemgr == v.safemgr:
                team = v
                break
            elif userid != None and userid == v.userid:
                team = v
                break
        return team

    def current_week (self):
        return self.season.current_week()

    

###############
# Player List #
###############

class FFPlayer(object):
    """
    Representation of an entry in the player list ready for display on the
    website
    """
    def __init__ (self, db_entry, manager=None):
        """ Create a new player from a FFDBPlayer object """
        self.db_entry = db_entry
        self.year        = db_entry.year
        self.player_key  = db_entry.player_key
        self.name        = db_entry.name
        self.pos         = db_entry.pos
        self.club        = db_entry.club
        self.last_season = db_entry.last_season
        self.total_score = db_entry.get_total_score()
        self.url         = ("http://www.fantasyleague.com/Pro/Stats/Player/" +
                            "{}.aspx".format(db_entry.url))
        self.img_url     = ("http://www.fantasyleague.com/sharedassets/" + 
                            "images/players/{}.jpg".format(db_entry.url))
        self.status      = db_entry.status
        self.reason      = db_entry.reason
        self.manager     = manager
        self.teamplayers = []

    def __str__ (self):
        return "{} - {}pts".format(self.name, self.total_score)

    def get_properties (self):
        """ Return properties of this player as a hash table """
        return ({'year' : self.year,
                 'player_key' : self.player_key, 
                 'name' : self.name,
                 'pos' : self.pos,
                 'club' : self.club,
                 'last_season' : self.last_season,
                 'score' : self.total_score,
                 'url' : self.url,
                 'img_url' : self.img_url,
                 'status' : self.status,
                 'reason' : self.reason,
                 'manager' : self.manager})

    def status_image (self):
        """ Return the image corresponding to this player's status"""
        return "images/{}.png".format(self.status)

    def set_manager (self, manager):
        """ 
        Change the manager this player belongs to 
        """
        if self.manager != manager:
            self.manager = manager
            

class FFPlayerList(object):
    """ Representation of the player list ready for display on the website """
    def __init__ (self, year, pos=None, club=None, unowned=False,
                  player_key=None):
        """ 
        Create a new player list object by querying the data store to find a 
        list of players matching the specified criteria
        """
        self.players = {}
        query = ffdb.FFDBPlayer.query().order(ffdb.FFDBPlayer.club)
        filters = []
        filters.append(ndb.AND(ffdb.FFDBPlayer.year == year))
        if pos != None:
            filters.append(ndb.AND(ffdb.FFDBPlayer.pos == pos))
        if club != None:
            filters.append(ndb.AND(ffdb.FFDBPlayer.club == club))
        if player_key != None:
            filters.append(ndb.AND(ffdb.FFDBPlayer.player_key == player_key))

        query = query.filter(ndb.AND(*filters))
        for player in query:
            self.players[player.player_key] = FFPlayer(player)

        # Find managers who own or have owned each player. If anyone 
        # currently owns the player and 'unowned' is set then remove them
        # from the list
        if player_key != None:
            # Only one player requested. Simply query for Teamplayers with
            # this key
            tpquery = ffdb.FFDBTeamPlayer.query().filter(ndb.AND(
                             ffdb.FFDBTeamPlayer.year == year,
                             ffdb.FFDBTeamPlayer.player_key == player_key))
        else:
            # More than one player. Search for all TeamPlayer objects. Note
            # that although we can safely filter by position since that 
            # doesn't change we cannot filter by club since that may differ
            # between the teamplayer and player objects. Therefore we may get
            # more results here than in the previous filter.
            filters = []
            filters.append(ndb.AND(ffdb.FFDBTeamPlayer.year == year))
            if pos != None:
                filters.append(ndb.AND(ffdb.FFDBTeamPlayer.pos == pos))
            tpquery = ffdb.FFDBTeamPlayer.query().filter(ndb.AND(*filters))

        for tp in tpquery:
            if tp.player_key in self.players:
                player = self.players[tp.player_key] 
                player.teamplayers.append(FFTeamPlayer(db_entry=tp))
                if tp.get_next_squad_num() >= 0:
                    # Player is currently in the squad
                    player.manager = tp.manager
                    if unowned:
                        del self.players[tp.player_key]

    def __iter__ (self):
        for player in self.players.values():
            yield player

    def list_names (self):
        """ Output a list of player names """
        for player in self.players:
            yield player.name

    def find_player (self, player_key):
        """ Return data for the specified player """
        if player_key in self.players:
            return self.players[player_key]
        else:
            return None
