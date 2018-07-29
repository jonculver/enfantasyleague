#! /usr/bin/python
#
# fixture_list_parser.py - July 2018 - Jon Culver
#
# Classes for parsing HTML and updating fixtures
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

    def __init__(self, clubs):
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
        self.end_date = date.today() + timedelta(days=(days_to_fri + 6))

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

    def start_h2(self, attributes):
        """
        Parse a <h2> tag. Set that we are within one
        """
        self.h2 = True

    def end_h2(self):
        """
        Parse a </h2> tag. Set that we are no longer within one
        """
        self.h2 = False

    def start_a(self, attributes):
        """
        Parse <a> tag.
        """

        def find_club(name, clubs):
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
                                logging.info("Parsed fixture: {} - {} v " \
                                             "{}".format(
                                    self.current_date.strftime("%d %b"),
                                    home_club.abr, away_club.abr))
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
    parser = FixtureListParser(debug=True)
