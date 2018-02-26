#! /usr/bin/python
#
# ff_parsers.py - May 2013 - Jon Culver
#
# Classes for parsing HTML and updating season data
#
import re
import urllib2
import sgmllib
import logging
from datetime import date
from datetime import datetime
from datetime import timedelta
import dateutil.parser
from httplib import HTTPException

##############
# PARAMETERS #
##############

logger = logging.getLogger(__name__)

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
              

######################
# Player List Parser #
######################

class ParsedPlayer():
    """
    Properties parsed for a player
    """
    def __init__(self):
        self.url = None
        self.pos = None
        self.club = None
        self.status = None
        self.name = None
        self.player_id = None
        self.total = None
        self.reason = None
        self.last_season = None

    def __str__(self):
        return "{} {} {} {} {} {}".format(self.player_id, self.name, self.pos,
                                          self.club, self.status, self.total)


class ParsedClub():
    """
    Properties parsed for a club
    """
    def __init__(self):
        self.url = None
        self.name = None
        self.fixtures = None

    def __str__(self):
        return "{} {}".format(self.name, self.fixtures)

#
# Parser class for player list
#
class PlayerListParser(sgmllib.SGMLParser):
    """
    Parse the player list and record the name, position, club, total points
    and injury status
    """

    # Mapping from position name in HTML to abbreviation
    positions = {"pos pos-G":"GK",
                 "pos pos-F":"FB",
                 "pos pos-C":"CB",
                 "pos pos-M":"M",
                 "pos pos-S":"S"}
                  
    status = {"right playerstatus doubtful":"Doubtful",
              "right playerstatus latefitnesstest":"LateFitnessTest",
              "right playerstatus suspended":"Suspended",
              "right playerstatus injured":"Injured",
              "right playerstatus ineligible":"Ineligable"}

    bad_suffixes = ["-[a-z]{2}\d{4}", # e.g. fr1011 or cl1011
                    "-champ",
                    "-prem",
                    "-epl",
                    "-dom",
                    "-999",
                    "-"]


    def parse(self, s):
        "Parse the given string 's'."
        logger.debug("Parsing string of length {}".format(len(s)))
        print(s)
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
        self.curr_player = ParsedPlayer()
        self.curr_club   = ParsedClub()
        self.curr_col    = 0
        
    def __init__ (self, debug=False):
        sgmllib.SGMLParser.__init__(self, verbose=0 if not debug else 1)

        self.players     = {}
        self.clubs       = {}
        self.in_table    = False
        self.td          = False
        self.a           = False
        self.__reset()

        self.url = "http://www.fantasyleague.com/Pro/Stats/"\
                          "playerlist.aspx?dpt={}".format("All")

        user_agent = 'Mozilla/5.0 (Windows NT 6.1; Win64; x64) ' \
                     'AppleWebKit/537.36 (KHTML, like Gecko) ' \
                     'Chrome/64.0.3282.167 Safari/537.36'
        headers = {'User-Agent': user_agent}
        req = urllib2.Request(self.url, headers=headers)

        logger.info("Requesting data for URL '{}'".format(self.url))
        try:
            f = urllib2.urlopen(req)
            logger.info("Parsing HTML")
            self.parse(f.read())
            f.close()
        except HTTPException as e:
            raise ParseError("Failed to read HTML: {}".format(str(e)))

        logger.info(
            "Parsing complete. {} players found, {} clubs found".format(
            len(self.players), len(self.clubs)))


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
        logging.info("Parsed {}".format(self.curr_player))
        if self.curr_player.player_key != None:
            self.players[self.curr_player.player_key] = self.curr_player
        if self.curr_club.name != None and self.curr_club.name not in self.clubs:
            self.clubs[self.curr_club.name] = self.curr_club
                                                                      
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
                        self.curr_club.url = value

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
                self.curr_club.name = data
                self.curr_player.club = data
            elif self.curr_col == 10:
                # Store this value in the 'last season' field. If there is a
                # further column then clear it again since it will be monthly
                # points instead
                self.curr_player.last_season = int(data)
            elif self.curr_col == 11:
                self.curr_player.total = int(data)
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

        logger.info("Fixture start date: {}, end date: {}".format(
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
                    clubs[abr] = ParsedClub()
                    clubs[abr].name = abr
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


if __name__ == '__main__':
    """
    Run the parsers and print the results
    """
    logging.basicConfig()
    logging.root.setLevel('DEBUG')
    parser = PlayerListParser(debug=True)


