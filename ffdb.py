#! /usr/bin/python
#
# ff_db.py - May 2013 - Jon Culver
#
# Fantasy Football Persistent Data Store
#
import copy
import logging
from datetime import datetime
from datetime import timedelta
from datetime import date

from google.appengine.ext import ndb

class FFDBEntry(ndb.Model):

    def __str__ (self):
        return str(self.key)

    def update_properties (self, properties):
        """ 
        Check whether the value of the supplied properties matches the current
        value and if not update it. If the new value is 'None' then this field
        will be ignored.
          Argument: properties. A dictionary of {key:value} pairs
          Return: True if any value changed and false otherwise
        """
        changed = False
        for field, new in properties.items():
            old = self.to_dict()[field]
            if new != None and new != old:
                logging.debug("{}. {} changed from {} to {}".format(
                                                  str(self), field, old, new))
                changed = True
            else:
                #This field hasn't changed or is 'None'. Remove it from the
                #dictionary prior to updating the entry
                del properties[field]

        if changed:
            self.populate(**properties)
        return changed
            

###############################################################################
# SEASON                                                                      #
###############################################################################
class FFDBSeason(FFDBEntry):
    """Models a football season """
    year          = ndb.StringProperty(required=True)
    start         = ndb.DateProperty(indexed=False, required=True)
    end           = ndb.DateProperty(indexed=False, required=True)
    enableUpdates = ndb.IntegerProperty(indexed=False)

    @staticmethod
    def get_key(year):
        return ndb.Key('FFDBSeason', year)

    @staticmethod
    def string_to_date (mydate):
        """
        Convert a string in dd/mm/yy format to a date object
        """
        dt = datetime.strptime(mydate,"%d/%m/%y")
        return(date(dt.year, dt.month, dt.day))

    @staticmethod
    def date_to_string (mydate):
        """
        Convert a date object to a string in dd/mm/yy format
        """
        return mydate.strftime('%d/%m/%y')

    @staticmethod
    def current_season ():
        """
        Find the current date and work out the appropriate string for the 
        current season.
        """
        current_date = date.today()
        if current_date.month >= 7:
            # From July onwards use the current year
            year = str(current_date.year)
        else:
            # From Jan to June use the previous year
            year = str(current_date.year - 1)

        return year

    @staticmethod
    def load (year=None):
        """
        Return a season object for a given year, or the current season if None
        """
        myyear = year if year != None else FFDBSeason.current_season()
        return FFDBSeason.get_key(myyear).get()

    def save (self):
        """
        Set the key for this item and save it. Note that the key cannot simply
        be set at create time due to a warning in the Google App engine
        documentation:
        'Note: If you override the constructor in a Model subclass, beware 
         that the constructor is also called implicitly in some cases, and be 
         sure that you support those calls. When an entity is read from the 
         Datastore, an empty entity is first created by calling the 
         constructor without arguments, after which the key and property 
         values are set one by one.' 
        """
        self.key = self.get_key(self.year)
        self.put()

    def date_to_week (self, date):
        """
        Return the week of the season within which the specified date lies. 
        The first day of the season is the start of week 1
          Arg: date - the date to find the week of. Either a string in
                      dd/mm/yy format or a date object
        """
        try:
            # Try parsing the date in case it is a string
            mydate = self.string_to_date(date)
        except TypeError:
            mydate = date

        delta = mydate - self.start
        week = delta.days //7 + 1

        assert (week > 0 and week < 52)
        return week  

    def total_weeks (self):
        """ Return the number of weeks in the season """
        return (self.date_to_week(self.end) + 1)

    def current_week (self):
        """ Return the week we are currently in """
        today = date.today()
        if today < self.start:
            return 0
        elif today > self.end:
            return self.total_weeks() + 1
        else:
            return self.date_to_week(today)

###############################################################################
# TEAMS                                                                       #
###############################################################################

class FFDBTeamWeek(FFDBEntry):
    """Data for a team in a given week in the season"""
    total_points = ndb.IntegerProperty()
    total_missed = ndb.IntegerProperty()
    position     = ndb.IntegerProperty()

class FFDBTeam(FFDBEntry):
    """Data for a team in the FF league"""
    year        = ndb.StringProperty(required=True)
    manager     = ndb.StringProperty(required=True)
    userid      = ndb.StringProperty(required=True)
    name        = ndb.StringProperty(required=True)
    funds       = ndb.FloatProperty(required=True)
    #@@@players     = ndb.StringProperty(repeated=True)
    # The total score is derived from the weekly data and used in queries
    total_score = ndb.ComputedProperty(lambda self: self.get_total_score())
    weeks       = ndb.StructuredProperty(FFDBTeamWeek, repeated=True)

    @staticmethod
    def get_key(year, userid):
        return ndb.Key('FFDBTeam', '{}-{}'.format(year, userid))

    @staticmethod
    def load (year, userid):
        return FFDBTeam.get_key(year, userid).get()

    def save (self):
        self.key = self.get_key(self.year, self.userid)
        self.put()

    def set_points_and_pos (self, week, diff_scored=0, diff_missed=0, 
                            position = None):
        """
        Set the team score and league position in the array entry for the 
        given week, filling in any missing entries as required. Setting data
        for previous weeks is not allowed.
        """
        assert(week >= len(self.weeks) - 1)
        if len(self.weeks) == 0:
            self.weeks.append(FFDBTeamWeek(total_points=0, total_missed=0,
                                           position=0))
        while len(self.weeks) - 1 < week:
            self.weeks.append(copy.deepcopy(self.weeks[-1]))
        self.weeks[week].total_points += diff_scored
        self.weeks[week].total_missed += diff_missed
        if position != None:
            self.weeks[week].position = position

    def update (self, name=None, funds_diff=0):
        """
        Change the properties of this team. Return True if anything changed
        or False otherwise
        """
        return self.update_properties({"name": name,
                                       "funds": self.funds + funds_diff})

    def __sanitize_week (self, week):
        """
        Check that the provided week is within the weeks array. If not use
        the last value in the array
        """
        if week == None or week >= len(self.weeks):
            return -1
        else:
            return week

    def get_total_score (self, week=None):
        wk = self.__sanitize_week(week)
        if len(self.weeks) > 0:
            return self.weeks[wk].total_points
        else:
            return 0

    def get_total_missed (self, week=None):
        wk = self.__sanitize_week(week)
        return self.weeks[wk].total_missed

    def get_week_score (self, week=None):
        wk = self.__sanitize_week(week)
        if wk >= len(self.weeks):
            # No score for current week
            return 0
        elif len(self.weeks) <= 1:
            # Score in or before the first week
            return self.get_total_score(0)
        else:
            # Difference between last two weeks
            return self.weeks[wk].total_points - self.weeks[wk-1].total_points


###############################################################################
# TEAMPLAYERS                                                                 #
###############################################################################

class FFDBTeamPlayerWeek(FFDBEntry):
    """Data for a player within a team in a given week"""
    week_points  = ndb.IntegerProperty()
    total_points = ndb.IntegerProperty()
    total_missed = ndb.IntegerProperty()
    squad_num    = ndb.IntegerProperty()

    def update_score (self, week_points):
        """ 
        Update the points or missed value as appropriate depending on whether
        the player is in the team or a sub (or neither)
        """
        # Check what has changed, if anything since the scores were last 
        # updated in this week. This function needs to be idempotent.
        if week_points != self.week_points:
            difference = week_points - self.week_points
            self.week_points = week_points
            if self.squad_num >= 0 and self.squad_num < 11:
                self.total_points += difference
            elif self.squad_num > 0:
                self.total_missed += difference

class FFDBTeamPlayer(FFDBEntry):
    """Data for a player within a specific team"""
    year         = ndb.StringProperty(required=True)
    manager      = ndb.StringProperty(required=True)
    userid       = ndb.StringProperty(required=True)
    player_key   = ndb.StringProperty(required=True)
    name         = ndb.StringProperty(required=True)
    instance     = ndb.IntegerProperty(required=True)
    club         = ndb.StringProperty(required=True)
    pos          = ndb.StringProperty(required=True)
    url          = ndb.StringProperty()
    price        = ndb.FloatProperty()
    current_club = ndb.StringProperty()
    # squad_num shows the position of this player within the team. 
    # -1 indicates the player is not in the team. Note that this value is 
    # really indicating the position the player will have in the following 
    # week. The current number is contained in the week structure
    squad_num    = ndb.IntegerProperty()
    weeks        = ndb.LocalStructuredProperty(FFDBTeamPlayerWeek, 
                                               repeated=True)

    @staticmethod
    def get_key(year, userid, player_key, instance):
        return ndb.Key('FFDBTeamPlayer', '{}-{}-{}{}'.format(
                               year, player_key, userid,
                               instance if instance != 0 else ""))

    @staticmethod
    def load (year, userid, player_key, instance):
        return FFDBTeamPlayer.get_key(year, userid, player_key, instance).get()

    def save (self):
        self.key = self.get_key(self.year, self.userid, self.player_key,
                                self.instance)
        self.put()

    def __sanitize_week (self, week):
        """
        Check that the provided week is within the weeks array. If not use
        the last value in the array
        """
        if week == None or week >= len(self.weeks):
            return -1
        else:
            return week
    
    def get_total_points (self, week=None):
        """ 
        Return the total number of points this player has scored for this team
        """
        wk = self.__sanitize_week(week)
        return self.weeks[wk].total_points

    def get_week_points (self, week=None):
        """ Return the number of points scored in a given week """
        if week >= len(self.weeks):
            # No points for this week
            return 0
        elif week == 0 or len(self.weeks) == 1:
            # Points for first week
            return self.get_total_points(0)
        else:
            # Difference between last two weeks
            wk = self.__sanitize_week(week)
            return self.weeks[wk].total_points - self.weeks[wk-1].total_points

    def get_total_missed (self, week=None):
        """ Return the total number of missed points"""
        wk = self.__sanitize_week(week)
        return self.weeks[wk].total_missed

    def get_week_missed (self, week=None):
        """ Return the number of points missed this week """
        if week >= len(self.weeks):
            # No points for this week
            return 0
        elif week == 0 or len(self.weeks) == 1:
            # Points for first week
            return self.get_total_missed(0)
        else:
            # Difference between last two weeks
            wk = self.__sanitize_week(week)
            return self.weeks[wk].total_missed - self.weeks[wk-1].total_missed
       
    def get_current_squad_num (self, week=None):
        """ The position in the team the player is currently in """
        wk = self.__sanitize_week(week)
        return self.weeks[wk].squad_num

    def get_next_squad_num (self):
        """ The position the player will have next week """
        return self.squad_num

    def update_squad_num (self, week):
        """
        Update the squad number for the current week in the season. This has
        the effect of activating any substitutions made in the previous week.
        """
        # Not allowed to update the squad number in anything other than the 
        # last element in the array
        assert week >= len(self.weeks) - 1

        # Make sure the list of week data has at least one entry in it
        if len(self.weeks) == 0:
            tpw = FFDBTeamPlayerWeek()
            tpw.total_points = 0
            tpw.total_missed = 0
            tpw.week_points  = 0
            tpw.squad_num    = -1
            self.weeks.append(tpw)

        # Fill in any missing weeks by copying the previous object.
        while len(self.weeks) <= week:
            tpw = copy.deepcopy(self.weeks[-1])
            # Make sure week points is initialised to zero
            tpw.week_points = 0
            self.weeks.append(tpw)

        # Update the position in the specified week to match the current value
        self.weeks[-1].squad_num = self.squad_num


    def update_score (self):
        """ 
        Update the score for this teamplayer using the data from the 
        corresponding player object. It is assumed that new entries are added
        to the 'weeks' array using update_squad_num and this function simply
        updates the most recent element in the array.
        """
        week = len(self.weeks) - 1
        player = FFDBPlayer.load(self.year, self.player_key)
        # Update the player score assuming he is still in the team. (If there 
        # are matches just after the auction then the new players should score
        # points instead but the squad number in the week object won't have
        # been updated.)
        if player != None and self.squad_num >= 0:
            self.weeks[week].update_score(player.get_week_score(week))
            
    def update_club (self, club):
        """ 
        Update the current_club field with a new value
        """
        return self.update_properties({"current_club": club})

###############################################################################
# PLAYERS                                                                     #
###############################################################################

class FFDBPlayer(FFDBEntry):
    """Models a player over the course of a season"""

    #Possible positions
    GK = "GK"
    FB = "FB"
    CB = "CB"
    M  = "MF"
    S  = "ST"
    
    # Possible player status values
    FIT           = "Fit"
    INJURED       = "Injured"
    SUSPENDED     = "Suspended"
    DOUBTFUL      = "Doubtful"
    INELIGABLE    = "Ineligable"
    LFT           = "Late Fitness Test"
    INTERNATIONAL = "International"

    year        = ndb.StringProperty(required=True)
    player_key  = ndb.StringProperty(required=True)
    name        = ndb.StringProperty(indexed=False, required=True)
    pos         = ndb.StringProperty(choices=[GK, FB, CB, M, S], required=True)
    club        = ndb.StringProperty(required=True)
    status      = ndb.StringProperty(choices=[FIT, INJURED, SUSPENDED,
                                              DOUBTFUL, INELIGABLE, LFT,
                                              INTERNATIONAL])
    reason      = ndb.StringProperty(indexed=False)
    last_season = ndb.IntegerProperty()
    url         = ndb.StringProperty()
    week_scores = ndb.IntegerProperty(repeated=True)

    @staticmethod
    def get_key(year, player_key):
        return ndb.Key('FFDBPlayer', '{}-{}'.format(year, player_key))

    @staticmethod
    def load (year, player_key):
        return FFDBPlayer.get_key(year, player_key).get()

    def save (self):
        self.key = self.get_key(self.year, self.player_key)
        if self.last_season == None:
            self.last_season = 0
        self.put()

    def update (self, player):
        """ 
        Copy fields from another FFDBPlayer object. The total score cannot be 
        updated in tihs way and set_total_score must be used instead
          Return: True if anything changed or False othewise
        """
        return self.update_properties({"player_key": player.player_key,
                                       "name": player.name,
                                       "pos": player.pos,
                                       "club": player.club,
                                       "status": player.status,
                                       "reason": player.reason,
                                       "url": player.url,
                                       "last_season": player.last_season})

    def __sanitize_week (self, week):
        """
        Check that the provided week is within the weeks array. If not use
        the last value in the array
        """
        if week == None or week >= len(self.week_scores):
            return -1
        else:
            return week

    def get_total_score (self, week=None):
        """
        Return the value in the scores array for the given week (or the 
        latest week if None is specified). If the array is empty return 0
        """
        score = 0
        wk = self.__sanitize_week(week)
        if len(self.week_scores) > 0:
            score = self.week_scores[wk]
        return score

    def get_week_score (self, week=-1):
        """
        Return the points scored by the player in a given week (or in the 
        current week, if none is specified)
        """
        score = 0
        if week >= len(self.week_scores):
            # No score for the current week
            pass        
        elif week == 0 or len(self.week_scores) == 1:
            # Current week is the only week
            score = self.week_scores[0]
        else:
            # Take the difference between the last two weeks 
            wk = self.__sanitize_week(week)
            score = self.week_scores[wk] - self.week_scores[wk - 1]
        return score    
        
    def get_week_count (self):
        """ Return the number of elements in the per-week score list """
        return len(self.week_scores)

    def set_total_score (self, week, score):
        """
        Set the score in the array entry for the current week, filling in
        any missing entries as required
        """
        if len(self.week_scores) == 0:
            self.week_scores.append(0)
        while len(self.week_scores) - 1 < week:
            self.week_scores.append(copy.deepcopy(self.week_scores[-1]))
        self.week_scores[week] = score

    def mark_ineligable (self):
        """
        Mark this player as no longer eligable because it doesn't appear in
        the player list
        """
        self.status = self.INELIGABLE
        self.reason = "Not in player list"
        

###############################################################################
# CLUBS                                                                       #
###############################################################################

class FFDBClub(FFDBEntry):
    """Data for a football club"""
    year  = ndb.StringProperty()
    abr   = ndb.StringProperty()
    name  = ndb.StringProperty()
    url   = ndb.StringProperty()
    fixtures = ndb.StringProperty(repeated=True)

    @staticmethod
    def get_key(year, abr):
        return ndb.Key('FFDBClub', '{}-{}'.format(year, abr))

    @staticmethod
    def load (year, abr):
        return FFDBClub.get_key(year, abr).get()

    def save (self):
        self.key = self.get_key(self.year, self.abr)
        self.put()

    def update (self, club):
        """
        Update this entry from data in another entry. 
          Return: True if anything changed or False otherwise
        """
        return self.update_properties({"name": club.name,
                                       "url":  club.url})
    
    def replace_fixtures (self, fixtures):
        """
        Replace the current fixture list with the specified list. This is not
        done as part of the 'update' function since it would not be possible 
        to specify 'None' and the fixtures would always get overwritten.
        """
        return self.update_properties({"fixtures": fixtures})
            
    def add_fixture (self, fixture):
        """
        Add a new fixture to the current list
        """                                                                                                                                      
        self.fixtures.append(fixture)

