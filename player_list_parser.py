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
        self.total = None
        self.reason = None
        self.last_season = None
        self.player_key = None

    def __str__(self):
        return "{} {} {} {} {} {}".format(self.player_key, self.name, self.pos,
                                          self.club, self.status, self.total if self.total else self.last_season)


class ParsedClub():
    """
    Properties parsed for a club
    """
    def __init__(self):
        self.url = None
        self.name = None

    def __str__(self):
        return "{} {}".format(self.name, self.url)

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


    def __parse(self, s):
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

    def get_players(self):
        """
        Return a list of ParsedPlayer objects corresponding to the players found in the HTML

        """
        return self.players

    def get_clubs(self):
        """
        Return a list of ParsedClub objects corresponding to the clubs found during parsing

        """
        return self.clubs
        
    def __init__ (self, debug=False):
        """
        Create a new parser object and parse player list data.

        :param debug: If set then details of the returned HTML and resulting parsing will be printed
        """
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
            self.__parse(f.read())
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
        if self.curr_player.player_key != None:
            logging.info("Parsed {}".format(self.curr_player))
            self.players[self.curr_player.player_key] = self.curr_player
        if self.curr_club.name != None and self.curr_club.name not in self.clubs:
            logging.info("Parsed {}".format(self.curr_club.name))
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
                club_abr = data.strip()
                self.curr_club.name = club_abr
                self.curr_player.club = club_abr
            elif self.curr_col == 10:
                # Store this value in the 'last season' field. If there is a
                # further column then clear it again since it will be monthly
                # points instead
                self.curr_player.last_season = int(data)
            elif self.curr_col == 11:
                self.curr_player.total = int(data)
                self.curr_player.last_season = None


if __name__ == '__main__':
    """
    Run the parsers and print the results
    """
    logging.basicConfig()
    logging.root.setLevel('DEBUG')
    parser = PlayerListParser(debug=True)


