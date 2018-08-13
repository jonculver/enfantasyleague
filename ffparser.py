#! /usr/bin/python
#
# ff_parsers.py - May 2013 - Jon Culver
#
# Classes for parsing HTML and updating season data
#

import ffdb
import logging
from google.appengine.ext import ndb
from player_list_parser import PlayerListParser
from fixture_list_parser import FixtureListParser

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
                

    def parse_player_list (self, save=True):
        """
        Create dictionaries of players and clubs from the player list and
        then update the entries in the DB.

        Arguments:
            save:
                Whether or not to save the update

        """
        # Read and parse the current list of players then convert them to database entries (This is not done by the
        # parsers themselves to keep them agnostic of any AppEngine specific classes)
        parser = PlayerListParser()
        parsed_players = parser.get_players()
        for key, player in parsed_players.items():
            db_entry = ffdb.FFDBPlayer(year       = self.season.year,
                                       player_key = key,
                                       pos        = player.pos,
                                       club       = player.club,
                                       url        = player.url,
                                       status     = player.status,
                                       reason     = player.reason,
                                       name       = player.name,
                                       last_season = player.last_season)
            if db_entry.status == None:
                db_entry.status = ffdb.FFDBPlayer.FIT
            if player.total:
                db_entry.set_total_score(self.week, player.total)
            self.players[key] = db_entry

        parsed_clubs = parser.get_clubs()
        for key, club in parsed_clubs.items():
            self.clubs[key] = ffdb.FFDBClub(year = self.season.year,
                                            abr = key,
                                            url = club.url)

        # Query the datastore to find the existing entries for players
        filters = [ndb.AND(ffdb.FFDBPlayer.year==self.season.year)]
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
        pass


