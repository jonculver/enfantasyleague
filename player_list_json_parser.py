#! /usr/bin/python
#
# player_list_json_parser.py - May 2013 - Jon Culver
#
# Classes for parsing player data from JSON
#
import re
import logging
import requests
import json

# Glue to get requests to work from within appengine
try:
    from requests_toolbelt.adapters import appengine
    appengine.monkeypatch()
except ImportError:
    pass

from player_list_parser import ParseError, ParsedClub, ParsedPlayer

##############
# PARAMETERS #
##############

logger = logging.getLogger(__name__)


######################
# Player List Parser #
######################


#
# Parser class for player list
#
class PlayerListParser():
    """
    Parse the player list and record the name, position, club, total points
    and injury status
    """

    def parse(self, data):
        for p in data['data']:
            player = ParsedPlayer()
            player.pos = p['original_position']
            player.club = p['club_name']
            first_name = p['player_first_name']
            last_name = p['player_last_name']
            if first_name is not None:
                name = "{} {}".format(first_name[0], last_name)
            else:
                name = last_name
            player.name = name
            player.status = p['player_status']
            player.total = int(p['total'])
            player.reason = None
            player.last_season = 0
            player.player_key = p['id']
            self.players[player.player_key] = player
            logging.info("Parsed {}".format(player))

            if player.club not in self.clubs:
                club = ParsedClub()
                club.name = player.club
                self.clubs[club.name] = club
                logging.info("Parsed {}".format(club))

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

    def byteify(self, input):
        """
        Convert JSON data from unicode to utf-8
        """
        if isinstance(input, dict):
            return {self.byteify(key): self.byteify(value)
                    for key, value in input.iteritems()}
        elif isinstance(input, list):
            return [self.byteify(element) for element in input]
        elif isinstance(input, unicode):
            output = input.encode('utf-8')
            # Fix apostrophes and soft hyphens
            return output.replace("&#039;", "'").replace('\xad', '').replace('\xc2', '')
        else:
            return input
        
    def __init__ (self, debug=False):
        """
        Create a new parser object and parse player list data.

        :param debug: If set then details of the returned HTML and resulting parsing will be printed
        """
        self.players     = {}
        self.clubs       = {}

        login_url = "https://www.fantasyleague.com/login"
        self.url = "https://www.fantasyleague.com/manage/matches/17666/index"
        self.url2 = "https://www.fantasyleague.com/manage/more/players/17666"

        # Create a session, since we'll need to log in, and request the login page
        session = requests.session()
        result = session.get(login_url)

        # Parse the token and post our credentials @@@ This seems like terrible auth
        if result.status_code != 200:
            raise ParseError("Request to {} returned status {}".format(login_url, result.status_code))
        match = re.search('name="_token".*value="(\w*)"', result.text)
        if match is None:
            logger.error("No token found in {}".format(result.text))
            raise ParseError("No token found")
        token = match.group(1)
        logger.info("Found token {}".format(token))

        # Now post our credentials
        payload = {"_token": token,
                   "email": "jpmculver@gmail.com",
                   "password": "enfl2022",
                   "remember": "on"}
        session.post(login_url, data=payload)

        # Now we should be able to retrieve the scores
        logger.info("Requesting data for URL '{}'".format(self.url))
        result = session.get(self.url)

        # ... but we just get an empty page. Extract the csrf token from the header and then make a POST request to
        # get the data we want
        match = re.search('<meta name="csrf-token" content="(\w*)"', result.text)
        csrf_token = match.group(1)
        logger.info("Found CSRF token {}".format(csrf_token))

        session.headers.update({"Accept": "application/json, text/javascript, */*; q=0.01",
                                "Accept-Encoding": "gzip, deflate",
                                "Referer": self.url,
                                "X-CSRF-TOKEN": csrf_token})
        result = session.post(self.url2)
        if result.status_code != 200:
            raise ParseError("Request to {} returned status {}".format(login_url, result.status_code))

        # Hopefully we have some data
        try:
            data = self.byteify(json.loads(result.content))
        except Exception as e:
            logger.error("Failed to decompress or load JSON data with encoding {} from {}: {}".format(result.encoding,
                                                                                                      result.content,
                                                                                                      e))
            raise e
        if debug:
            print(data)
        logger.info("Parsing JSON")
        self.parse(data)
        logger.info(
            "Parsing complete. {} players found, {} clubs found".format(
            len(self.players), len(self.clubs)))


if __name__ == '__main__':
    """
    Run the parsers and print the results
    """
    logging.basicConfig()
    logging.root.setLevel('DEBUG')
    parser = PlayerListParser(debug=True)


