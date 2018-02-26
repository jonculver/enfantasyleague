#! /usr/bin/python
#
# ff_parsers.py - May 2013 - Jon Culver
#
# Classes for parsing HTML and updating season data
#

import ffdb
import urllib2, sgmllib, re
import logging
from datetime import date
from datetime import datetime
from datetime import timedelta
import dateutil.parser
from httplib import HTTPException
from google.appengine.ext import ndb

##############
# PARAMETERS #
##############

# Turn on debugging
debug = False

# Mapping from club name to abbreviation
club_abr = {"arsenal":"ARS",
            "aston-villa":"AV",
            "burnley":"BUR",
            "afc-bournemouth":"BOU",
            "cardiff-city":"CAR",
            "chelsea":"CHE",
            "crystal-palace":"CP",
            "everton":"EVE",
            "fulham":"FUL",
            "hull-city":"HUL",
            "leicester-city":"LEI",
            "liverpool":"LIV",
            "manchester-city":"MC",
            "middlesbrough":"MID",
            "manchester-united":"MU",
            "newcastle-united":"NEW",
            "norwich-city":"NOR",
            "queens-park-rangers":"QPR",
            "southampton":"SOT",
            "stoke-city":"STO",
            "sunderland":"SUN",
            "swansea-city":"SWA",
            "tottenham-hotspur":"TOT",
            "watford":"WAT",
            "west-bromwich-albion":"WBA",
            "west-ham-united":"WH"}



###########
# Classes #
###########

class ParseError(Exception):
    pass

class FFParser(object):
    """
    This class provides methods for parsing data from websites and making the
    appropriate updates to the season data
    """

    def __init__ (self, season):
        """
        Create a new parser object. 
        """
        self.season  = season
        self.week    = self.season.current_week()
        self.players = {}
        self.clubs   = {}
        
    def update_player (self, player, existing, save=True):
        """ 
        Update an existing database entry.
        Return: True if the player was updated or False if there was no change
        """
        # Temporary code to fix club data:
        if player.club != player.club.strip():
            player.club = player.club.strip()
        changed = existing.update(player)
        if existing.get_total_score() != player.get_total_score():
            changed = True
            existing.set_total_score(self.week, player.get_total_score())
        if changed and save:
            existing.save()
        return changed
        
    def add_or_update_club (self, club, update_fixtures=False):
        """ 
        Attempt to load entry from the db and update it. Otherwise add it.
        Return True if the club was updated or False if there was no change
        Arguments: club - the dummy entry to copy data from
                   update_fixtures - flag indicating whether to update fixtures
        """
        myclub = ffdb.FFDBClub.load(self.season.year, club.abr)
        changed = False
        if myclub == None:
            # Use the new entry. Make sure it has a valid year
            myclub = club
            myclub.year = self.season.year
            changed = True
        else:
            # Update the existing entry
            changed = myclub.update(club)
            if update_fixtures:
                changed = myclub.replace_fixtures(club.fixtures) or changed
            
        if changed:
            myclub.save()
        return changed
                

    def parse_player_list (self, pos="All", classic=False, save=True):
        """
        Create dictionaries of players and clubs from the player list and
        then update the entries in the DB.

        Arguments:
            pos:
                The position to query for. By default all positions.
            classic:
                Whether or not to use the classic site instead of the pro one
            save:
                Whether or not to save the update

        """
        # Clear any existing parsed player data
        self.players = {}

        # Set up the number used in the URL to query players
        if pos == ffdb.FFDBPlayer.GK:
            pos_num = 1
        elif pos == ffdb.FFDBPlayer.FB:
            pos_num = 2
        elif pos == ffdb.FFDBPlayer.CB:
            pos_num = 3
        elif pos == ffdb.FFDBPlayer.M:
            pos_num = 4
        elif pos == ffdb.FFDBPlayer.S:
            pos_num = 6
        else:
            pos_num = 0

        if classic:
            player_list = "http://www.fantasyleague.com/Classic/Stats/"\
                          "playerlist.aspx?dpt={}".format(pos_num)
        else:
            player_list = "http://www.fantasyleague.com/Pro/Stats/"\
                          "playerlist.aspx?dpt={}".format(pos_num)

        # Attempt to parse the data first and only perform an update if the
        # parsing is all completed to avoid partial updates
        if classic:
            parser = PlayerListParserClassic(self.season.year, self.week,
                                             self.players, self.clubs)
        else:
            parser = PlayerListParser(self.season.year, self.week, 
                                      self.players, self.clubs)

        logging.info("Requesting data for URL '{}'".format(player_list))

        user_agent = 'Mozilla/5.0 (Windows NT 6.1; Win64; x64) ' \
                     'AppleWebKit/537.36 (KHTML, like Gecko) ' \
                     'Chrome/64.0.3282.167 Safari/537.36'
        headers = {'User-Agent': user_agent}
        req = urllib2.Request(player_list, headers=headers)

        try:
            f = urllib.urlopen(req)
            logging.info("Parsing HTML")
            parser.parse(f.read())
            f.close()
        except HTTPException as e:
            raise ParseError("Failed to read HTML: {}".format(str(e)))

        logging.info(
                 "Parsing complete. {} players found for position {}".format(
                 len(self.players), pos))
        # Query the datastore to find the existing entries for players
        filters = [ndb.AND(ffdb.FFDBPlayer.year==self.season.year)]
        if pos != "All":
            filters.append(ndb.AND(ffdb.FFDBPlayer.pos==pos))
        existing = {p.player_key:p for p in ffdb.FFDBPlayer.query().filter(
                                                         ndb.AND(*filters))}
        logging.info("Found {} players in datastore".format(len(existing)))

        # Update the players we found
        p_changed = 0
        p_added = 0
        for key, player in self.players.items():
            if key in existing:
                #Update the existing entry
                if self.update_player(player, existing[key], save=save):
                    p_changed += 1
            else:
                #Save this new entry in the data store
                if save:
                    player.save()
                p_added += 1

        logging.info("{} player entries updated, {} added".format(p_changed,
                                                                   p_added))
        # Update any players we didn't find
        notfound = 0
        for key, player in existing.items():
            if key not in self.players:
                notfound += 1
                player.mark_ineligable()
                if save:
                    player.save()
            
        logging.info("{} missing players updated".format(notfound))
        # Update the clubs
        c_changed = 0
        for club in self.clubs.values():
            if self.add_or_update_club(club):
                c_changed += 1
        logging.info("{} of {} clubs updated".format(c_changed, 
                                                      len(self.clubs)))

        # Update the season, to indicate that the update is complete
        self.season.save()

        # Log the result
        logging.info("Update complete")
        return ("Successfully parsed data for {} players. {} required "\
                "updates. {} players in database were not found".format(
                    len(self.players), p_changed, notfound))

    def parse_fixtures (self):
        """
        Create dictionaries of clubs and fixtures in the next week.
        """
        fixture_url = "http://www.bbc.co.uk/sport/football/"\
                      "premier-league/fixtures"
        
        parser = FixtureListParser(self.clubs)

        logging.info("Requesting data for URL '{}'".format(fixture_url))
        retries = 0
        parsed = False
        error = ""
        while retries < 5 and not parsed:
            try:
                f = urllib.urlopen(fixture_url)
                logging.info("Parsing HTML")
                parser.parse(f.read())
                f.close()
                parsed = True
            except HTTPException as e:
                logging.error("Failed to read HTML. {} retries remaining. "\
                              "error: '{}'".format(5-retries, e))
                retries += 1
                error = str(e)

        if not parsed:
            raise ParseError("Failed to read HTML: {}".format(str(error)))

        logging.info("Parsing complete after {} retries".format(retries))
        c_changed = 0
        for club in self.clubs.values():
            if self.add_or_update_club(club, update_fixtures=True):
                c_changed += 1
        logging.info("fixtures for {} of {} clubs updated".format(c_changed, 
                                                          len(self.clubs)))

        
              

######################
# Player List Parser #
######################

#
# Parser class for player list
#
class PlayerListParser(sgmllib.SGMLParser):
    """
    Parse the player list and record the name, position, club, total points
    and injury status
    """

    # Mapping from position name in HTML to abbreviation
    positions = {"pos pos-G":ffdb.FFDBPlayer.GK,
                 "pos pos-F":ffdb.FFDBPlayer.FB,
                 "pos pos-C":ffdb.FFDBPlayer.CB,
                 "pos pos-M":ffdb.FFDBPlayer.M,
                 "pos pos-S":ffdb.FFDBPlayer.S}
                  
    status = {"right playerstatus doubtful":ffdb.FFDBPlayer.DOUBTFUL,
              "right playerstatus latefitnesstest":ffdb.FFDBPlayer.LFT,
              "right playerstatus suspended":ffdb.FFDBPlayer.SUSPENDED,
              "right playerstatus injured":ffdb.FFDBPlayer.INJURED,
              "right playerstatus ineligible":ffdb.FFDBPlayer.INELIGABLE}

    bad_suffixes = ["-[a-z]{2}\d{4}", # e.g. fr1011 or cl1011
                    "-champ",
                    "-prem",
                    "-epl",
                    "-dom",
                    "-999",
                    "-"]


    def parse(self, s):
        "Parse the given string 's'."
        self.feed(s)
        self.close()

        # Sanity check the results to make sure we've actually parsed a 
        # sensible number of players and the right number of clubs. (Note that
        # we may only be parsing players from one position)
        if len(self.clubs) != 20:
            raise ParseError("Expected 20 clubs, saw {}".format(
                                                          len(self.clubs)))
        elif len(self.players) < 40:
            raise ParseError("Expected >40 players, saw {}".format(
                                                          len(self.players)))

    def __reset (self):
        self.curr_player   = ffdb.FFDBPlayer(year   = self.year,
                                             status = ffdb.FFDBPlayer.FIT,
                                             reason = "")
        self.curr_club_url = None
        self.curr_col      = 0
        
    def __init__ (self, year, week, players, clubs):
        sgmllib.SGMLParser.__init__(self, verbose=0 if not debug else 1)

        self.year        = year
        self.week        = week
        self.players     = players
        self.clubs       = clubs
        self.in_table    = False
        self.td          = False
        self.a           = False
        self.__reset()

    def start_div (self, attributes):
        """
        Parse a <div> tag. Loads of useful stuff in these
        """
        for name, value in attributes:
            if name == "id":
                # This is the start of a new element of the page. If it is the
                # player list then we must start caring about everything else,
                # if not then we should stop caring.
                if value == "playerlist":
                    self.in_table = True
                else:
                    self.in_table = False
            elif self.in_table:
                if name == "class":
                    # Check if the class matches a position or a status and 
                    # if so, update appropriately
                    if value in self.positions:
                        self.curr_player.pos = self.positions[value]
                    elif value in self.status:
                        self.curr_player.status = self.status[value]
                if name == "title":
                    # This is the alt-text for an injury
                    self.curr_player.reason = value

    def start_tr (self, attributes):
        """
        Parse <tr> tag. Reset the player attributes to default
        """
        self.__reset()

    def end_tr (self):
        """
        Parse a </tr> tag. Save the player details if any.
        """
        if self.curr_player.player_key != None:
            self.players[self.curr_player.player_key] = self.curr_player
                                                                      
    def start_td (self, attributes):
        """
        Parse <td> tag
        """
        self.td = True

    def end_td (self):
        """
        Parse </td> tag. Increment the column position
        """
        self.td = False
        self.curr_col += 1

    def start_a (self, attributes):
        """
        Parse <a> tag. Record the URL for players (column 1) and clubs
        (column 4). For players we also need to use part of the URL as the
        key since the name is not unique.
        """
        self.a = True
        if self.in_table:
            for name, value in attributes:
                if name == "href":
                    if self.curr_col == 1:
                        # Player URL
                        m = re.match('.*/Stats/Player/(.*)\.aspx', value)
                        key = m.group(1).lower().strip()
                        self.curr_player.url = key
                        #Strip out the suffixes we don't want
                        for suffix in self.bad_suffixes:
                            regex = '{}$'.format(suffix)
                            key = re.sub(regex, '', key)
                        self.curr_player.player_key = key

                    elif self.curr_col == 4:
                        # Club URL
                        self.curr_club_url = value

    def end_a (self):
        """
        Parse </a> tag
        """
        self.a = False

    def handle_data(self, data):
        """
        This method is called for all data within HTML tags. What we do 
        depends on which tag we saw last
        """
        if self.in_table and self.td:
            #
            # Columns:
            #   0 - position (handled by div)
            #   1 - name
            #   2 - status (handled by div)
            #   3 - club badge (ignored)
            #   4 - club
            #   5 - played (ignored)
            #   6 - goals  (ignored)
            #   7 - assists (ignored)
            #   8 - clean sheets (ignored)
            #   9 - goals against (ignored)
            #   10 - monthly points if 11 columns OR last-season points if 10
            #   11 - total points
            #
            if self.curr_col == 1 and self.a:
                # Some junk either side of the <a> tag so ignore that
                self.curr_player.name = data
            elif self.curr_col == 4:
                # If we haven't already seen this club then create an
                # entry for it in our dictionary
                if data not in self.clubs:
                    self.clubs[data] = ffdb.FFDBClub(year = self.year,
                                                     abr  = data.strip(),
                                                     url  = self.curr_club_url)
                self.curr_player.club = data
            elif self.curr_col == 10:
                # Store this value in the 'last season' field. If there is a
                # further column then clear it again since it will be monthly
                # points instead
                self.curr_player.last_season = int(data)
            elif self.curr_col == 11:
                self.curr_player.set_total_score(self.week, int(data))
                self.curr_player.last_season = None


class PlayerListParserClassic (PlayerListParser):
    """
    Parser for the classic player list
    """
    def handle_data(self, data):
        """
        This method is called for all data within HTML tags. What we do 
        depends on which tag we saw last
        """
        if self.in_table and self.td:
            #
            # Columns:
            #   0 - position (handled by div)
            #   1 - name
            #   2 - status (handled by div)
            #   3 - club badge (ignored)
            #   4 - club
            #   5 - price (ignored)
            #   6 - chilis (ignored)
            #   7 - played (ignored)
            #   8 - goals  (ignored)
            #   9 - assists (ignored)
            #   10 - clean sheets (ignored)
            #   11 - goals against (ignored)
            #   12 - monthly points if 11 columns OR last-season points if 10
            #   13 - total points
            #
            if self.curr_col == 1 and self.a:
                # Some junk either side of the <a> tag so ignore that
                self.curr_player.name = data
                
            elif self.curr_col == 4:
                # If we haven't already seen this club then create an
                # entry for it in our dictionary
                if data not in self.clubs:
                    self.clubs[data] = ffdb.FFDBClub(year = self.year,
                                                     abr  = data.strip(),
                                                     url  = self.curr_club_url)
                self.curr_player.club = data
            elif self.curr_col == 12:
                # Store this value in the 'last season' field. If there is a
                # further column then clear it again since it will be monthly
                # points instead
                self.curr_player.last_season = int(data)
            elif self.curr_col == 13:
                self.curr_player.set_total_score(self.week, int(data))
                self.curr_player.last_season = None


#######################
# Fixture List Parser #
#######################

#
# Parser class for fixture list
#
class FixtureListParser(sgmllib.SGMLParser):
    """
    Parse the fixture list and record the fixtures coming up in the next
    week for each club.
    """

    def parse(self, s):
        """
        Function requied by sgmllib to initiate parsing
        """
        "Parse the given string 's'."
        self.feed(s)
        self.close()

    def __init__ (self, clubs):
        """
        Create a new parser object
        Argument: clubs - dictionary of clubs to populate
        """
        sgmllib.SGMLParser.__init__(self, verbose=0 if not debug else 1)

        # Work out which range of dates we are interested in. This starts on
        # the Friday after the current date and ends on the following Thursday.
        # If today is a Friday then the start date is today.
        
        # weekday returns day of week where Mon=0 and Sun=6
        # We want Fri=7 down to Thu=1. (10 - weekday % 7 reverses the order 
        # and makes thursday 0.) 
        days_to_fri = ((10 - date.today().weekday()) % 7) + 1

        self.start_date = date.today() + timedelta(days=days_to_fri)
        self.end_date = date.today() + timedelta(days=(days_to_fri+6))

        logging.info("Fixture start date: {}, end date: {}".format(
                                self.start_date.strftime("%A %d %B"),
                                self.end_date.strftime("%A %d %B"))) 

        self.clubs = clubs

        # If the current_date is not None then it indicates that a valid set
        # of fixtures between the start and end date is currently being parsed
        self.current_date = None
        # Whether or not we are within a <h2> tag
        self.h2 = False
        # The club playing at home. Once the away side is encountered the 
        # fixture will be completed and added to the club.
        self.home = None

    def start_h2 (self, attributes):
        """
        Parse a <h2> tag. Set that we are within one
        """
        self.h2 = True

    def end_h2 (self):
        """
        Parse a </h2> tag. Set that we are no longer within one
        """
        self.h2 = False

    def start_a (self, attributes):
        """
        Parse <a> tag.
        """

        def find_club (name, clubs):
            """
            Attempt to convert the name to an abbreviation. If successful
            the look up the club in the dictionary and either return a matching
            object if there is one or create a new one.
            """
            abr = None
            club = None
            try:
                abr = club_abr[name]
            except KeyError:
                logging.error("Failed to find club with name '{}'".format(
                                                                      name))
            if abr != None:
                if abr not in clubs:
                    clubs[abr] = ffdb.FFDBClub(abr=abr, fixtures=[])
                club = clubs[abr]
            return club


        # If we have a valid fixture date then check whether we have a team
        # to add to the fixture.
        if self.current_date != None:
            for name, value in attributes:
                if name == "href":
                    m = re.match('.*/football/teams/(.*)', value)
                    if m != None:
                        key = m.group(1).lower().strip()
                        
                        if self.home == None:
                            # Save this team, ready for use with the away team.
                            self.home = key
                        else:
                            # We already have a home team so complete this 
                            # fixture by looking up both of the clubs and 
                            # adding the current fixture to their fixture 
                            # lists.
                            home_club = find_club(self.home, self.clubs)
                            away_club = find_club(key, self.clubs)

                            if home_club != None and away_club != None:
                                logging.info("Parsed fixture: {} - {} v "\
                                             "{}".format(
                                        self.current_date.strftime("%d %b"),
                                        home_club.abr, away_club.abr ))
                                home_club.add_fixture("{} v {} ({})".format(
                                        self.current_date.strftime("%d %b"),
                                        away_club.abr, "H"))
                                away_club.add_fixture("{} v {} ({})".format(
                                        self.current_date.strftime("%d %b"),
                                        home_club.abr, "A"))
                            # Reset the home team ready for the next fixture
                            self.home = None

    def handle_data(self, data):
        """
        This method is called for all data within HTML tags. What we do 
        depends on which tag we saw last
        """
        if self.h2:
            # For <h2></h2> tags check whether the enclosed date is a valid
            # date and if so, whether it is within the range we are looking
            # for.
            fixture_date = None
            try:
                dt = dateutil.parser.parse(data)
                if dt != None:
                    fixture_date = date(dt.year, dt.month, dt.day)
            except ValueError:
                # This is expected if the data is not a valid date and can
                # simply be ignored.
                pass

            if (fixture_date != None and self.start_date <= fixture_date and 
                                                fixture_date <= self.end_date):
                self.current_date = fixture_date 
            else:
                self.current_date = None



#############################################################################
# Printable Player List Parser                                              #
#                                                                           #
# As it stands this class is not used because the names in the list are not #
# unique                                                                    #
#############################################################################

#
# Parser class for player list
#
#class PrintablePlayerListParser(sgmllib.SGMLParser):
#    """
#    Parse the printable player list and record the name, position, club and
#    points from last season for each player
#    """
#
#    # Mapping from position name in HTML to abbreviation
#    positions = {"Goalkeeper":"GK",
#                 "Fullback":"FB",
#                 "Centreback":"CB",
#                 "Midfielder":"MF",
#                 "Striker":"S"}
#
#    def parse(self, s):
#        "Parse the given string 's'."
#        self.feed(s)
#        self.close()
#
#    def __init__ (self, players, clubs):
#        """
#        Create a new parser object.
#          Arg: players - dictionary to fill in with FFPlayer objects
#          Arg: clubs   - dictionary to fill in with FFClub objects
#        """
#        sgmllib.SGMLParser.__init__(self, verbose=0 if not debug else 1)
#
#        self.players     = players
#        self.clubs       = clubs
#        self.curr_pos    = "GK"
#        self.curr_col    = 0
#        self.curr_name   = ""
#        self.curr_club   = None
#        self.th          = False
#        self.td          = False
#
#    def start_th (self, attributes):
#        """
#        Parse <th> tag. 
#        """
#        self.th = True
#
#    def end_th (self):
#        """
#        Parse </th> tag
#        """
#        self.th = False
#
#    def start_tr (self, attributes):
#        """
#        Parse <tr> tag. Set the column position to 0
#        """
#        self.curr_col = 0
#
#    def start_td (self, attributes):
#        """
#        Parse <td> tag
#        """
#        self.td = True
#
#    def end_td (self):
#        """
#        Parse </td> tag. Increment the column position
#        """
#        self.td = False
#        self.curr_col += 1
#
#    def handle_data(self, data):
#        """
#        This method is called for all data within HTML tags. What we do 
#        depends on which tag we saw last
#        """
#        if self.th:
#            #
#            # Check if the heading is in our position dictionary and if so
#            # update the current position. Otherwise nothing to do
#            #
#            if data in self.positions:
#                self.curr_pos = self.positions[data]
#                if debug:
#                    print "Moving to {}".format(self.curr_pos)
#
#        if self.td:
#            #
#            # Table data consists of one of four columns:
#            #   0 - ID - ignore
#            #   1 - Name - store
#            #   2 - Club - look up in clubs hash and store
#            #   3 - last seasons's points - store and add entry to hash
#            if self.curr_col == 1:
#                self.curr_name = data
#            elif self.curr_col == 2:
#                self.curr_club = data
#                if data not in self.clubs:
#                    self.clubs[data] = ff.FFClub(data)
#            elif self.curr_col == 3:
#                self.players[self.curr_name] = ff.FFPlayer(self.curr_name, 
#                                                           self.curr_pos,
#                                                           self.curr_club, 
#                                                           last_season=data)
#                if debug:
#                    print "Created: {}".format(str(self.players[self.curr_name]))
#
