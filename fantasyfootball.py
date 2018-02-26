import os
import urllib
import logging

from google.appengine.api import users
from google.appengine.ext import ndb
from google.appengine.api import memcache
from collections import OrderedDict
from time import sleep
from itertools import chain

import jinja2
import webapp2
import json
import re
import ff, ffdb
import tools
import gae_mini_profiler.profiler
import time
from gae_mini_profiler.templatetags import TemplateTags
from ffparser import ParseError


JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'])

class Tab (object):
    """ Represents a tab within a ff page """

    def __init__(self, name, html_id, url=None):
        """ 
        Create a new tab with the following propreties:
            name - Display name for the tab
            html_id - the unique ID for this element.
            url - an ajax page which returns html. If not specified then an 
                  internal link is generated using the html_id
        """
        self.name = name
        self.html_id = "tabs-{}".format(html_id)
        self.url = url
        if self.url == None:
            self.url = "#{}".format(self.html_id)

class ToolsTab (Tab):
    """ Extension of Tab for the tools page """

    def __init__ (self, name, html_id, **kwargs):
        """ 
        Create a new tab:
            name - the name of this tab and the tool
            html_id - the ID for this tool
            text - description of the tool
        """
        super(ToolsTab, self).__init__(name, html_id, **kwargs)
        self.tool_id = html_id
       

class FFPage(webapp2.RequestHandler):

    def user_setup (self):
        """
        Set values relating to the current user
        """
        self.user = users.get_current_user()
        if not hasattr(self, 'admin'):
            # Admin may already be set in some cases
            self.admin = False
        if not hasattr(self, 'request') or self.request is None:
            # Not a request so fill in empty strings.
            self.login_url=""
            self.login_linktext=""
        elif self.user != None:
            # A user is logged in so create personalised logout url
            self.login_url = users.create_logout_url(self.request.uri)
            self.login_linktext = "Logout {}".format(self.user.nickname())
            if not self.admin:
                self.admin = users.is_current_user_admin()
        else:
            # No user logged in so create a login url
            self.login_url = users.create_login_url(self.request.uri)
            self.login_linktext = 'Login'

    def common_setup (self, menu_num=0, year=None, league=None, 
                      populate_teams=False):
        """
        Common setup for all HTML pages on the site, including filling in 
        values for the menus and other common elements
        Argument: 
            menu_num - the index of the menu item to open by default
            year - current year, if known, to save looking it up
            league - FFLeague object, if known, to save creating it
            populate_teams - whether or not to load the players in each team
        """
        # Only need to do this once.
        if not hasattr(self, 'template_values'):
            self.template_values = {}
            self.tabs = OrderedDict()

            self.user_setup()
            self.set_value("login_url", self.login_url)
            self.set_value("login_linktext", self.login_linktext)
            self.set_value("admin", self.admin)

            # Make profiling work.
            self.set_value("profiler", TemplateTags())

            # Fill in the league object required by all pages. Read values 
            # from the DB if not provided. Note that populating all teams from 
            # the datastore is very slow (e.g. >10s)
            self.year = year
            if year == None:
                self.year  = self.request.get('year', 
                                          ffdb.FFDBSeason.current_season())
            self.league = league
            if league == None:
                self.league = ff.FFLeague(self.year, 
                                          populate_teams=populate_teams)

            # Create ordered dictionaries for each element in the main menu
            # 0. League. The league table
            league_menu = OrderedDict([("League Table", "./league.html"),
                                       ("Top Scorers", "./allteams.html"),
                                       ("Player List",  "./players.html")])

            # 1. Teams. Details for each team in the league
            teams_menu = OrderedDict()
            for team in self.league:
                teams_menu[team.manager] = "./teams.html?manager={}".format(
                                                  team.safemgr)

            # 2. MyTeam. Substitutions etc.
            myteam_menu = OrderedDict([("Edit Team", "./myteam.html")])

            # 3. Tools
            tools_menu = OrderedDict([("Auction", "./auction.html")])
            if self.admin:
                tools_menu["Admin Tools"] = "./tools.html"

            # 4. Rules
            rules_menu = OrderedDict([("Rules", "./rules.html"),
                                      ("Past Seasons", "./history.html")])

            # Now fill in the details for each menu item
            menu =  OrderedDict([("League", league_menu),
                                 ("Teams", teams_menu),
                                 ("MyTeam", myteam_menu),
                                 ("Tools", tools_menu),
                                 ("Rules", rules_menu)])
            self.set_value("main_menu", menu)
            self.set_value("menu_num", menu_num)

            # Set a default title in case the subclass doesn't set one
            self.set_title()     

    def is_float(self, s):
        """ Return True if the string is a valid float, False otherwise """
        try:
            float(s)
            return True
        except ValueError:
            return False

    def set_value (self, name, value):
        """ Set a value to be used in the HTML template """
        self.template_values[name] = value

    def set_title (self, title = None):
        """ Set the page title for this page"""
        if title != None:
            t = title
        else:
            t = "Fantasy Football"
        self.set_value("title", t)

    def get(self, menu_num=0, populate_teams=False):
        """ Inheritable function for get methods """
        self.common_setup(menu_num, populate_teams=populate_teams)

    def post (self, menu_num=0, populate_teams=False):
        """Inheritable function for post methods"""
        self.common_setup(menu_num, populate_teams=populate_teams)
    
    def render_from_cache (self, cache_name):
        """
        Render the page from the cache if it is present
        Return: True if page was present in cache. False otherwise
        """
        html = memcache.get(cache_name)
        if html != None:
            # Find the user details and rewrite that element on the page
            self.user_setup()
            login_string = "<a class=\"loginurl\" href=\"{}\">{}</a>".format(
                               self.login_url, self.login_linktext)
            output = re.sub('\<a class=\"loginurl\".*\<\/a\>', login_string, 
                            html)
            self.response.write(output)
            return True
        else:
            return False

    def render (self, page_name, cache_name=None, respond=True):
        """
        Either Respond with the HTML output or store it in the specified
        name in the cache or both.
        """
        template = JINJA_ENVIRONMENT.get_template('html/{}'.format(page_name))
        html = template.render(self.template_values)
        if cache_name != None:
            # Want to expire the page at 9am UTC.
            now = time.gmtime()
            seconds_today = (now.tm_hour * 60 * 60) + (now.tm_min * 60)
            seconds_at_nine = 9 * 60 * 60
            expiry = seconds_at_nine - seconds_today
            if expiry < 0:
                expiry += 24 * 60 * 60
            logging.info("Caching page {} to expire in {} seconds".format(
                                            cache_name, expiry))
            memcache.set(cache_name, html, time=expiry)
        if respond:
            self.response.write(html)

    def error (self, error_string):
        """ Display a web page indicating something went wrong """
        self.set_value('error', error_string)
        self.render('error.html')

    def add_tab (self, tab):
        """ Add a new Tab to this page """
        self.tabs[tab.html_id] = tab
        self.set_value('tabs', self.tabs)

class MainPage(FFPage):

    def get (self):
        super(MainPage, self).get()
        self.render("index.html")

class Rules(FFPage):
    """
    League Rules
    """
    def get (self):
        super(Rules, self).get(4)
        self.add_tab(Tab("Basics", "basics"))
        self.add_tab(Tab("Squad", "squad"))
        self.add_tab(Tab("Scoring Points", "points"))
        self.add_tab(Tab("Auction", "auction"))
        self.add_tab(Tab("Sealed Bids", "sealed"))
        self.add_tab(Tab("Transfers", "transfers"))
        self.add_tab(Tab("FAQ", "faq"))
        self.set_title("Rules")
        self.render("rules.html")

class History(FFPage):
    """
    Past Winners etc.
    """
    def get (self):
        super(History, self).get(4)
        self.add_tab(Tab("Hall Of Fame", "winners"))
        self.render("history.html")


class PlayerList(FFPage):
    """
    The main player list page
    """
    def get (self):
        super(PlayerList, self).get(0)
        self.add_tab(Tab("Goalkeepers", "GK", "./playerlisttab.html?pos=GK"))
        self.add_tab(Tab("Fullbacks", "FB", "./playerlisttab.html?pos=FB"))
        self.add_tab(Tab("Centrebacks", "CB", "./playerlisttab.html?pos=CB"))
        self.add_tab(Tab("Midfielders", "M", "./playerlisttab.html?pos=M"))
        self.add_tab(Tab("Strikers", "S", "./playerlisttab.html?pos=S"))
        self.add_tab(Tab("All", "all", "./playerlisttab.html"))
        self.set_title("Player List")
        self.render("base.html")

class PlayerListTab(FFPage):
    """
    HTML for the table in a player list, to be returned in response to an
    ajax query
    """
    TEMPLATE = "player_list_table.html"

    def create_cache_name (self, pos):
        """Return the string to use to store this page in the cache"""
        return "{}.{}".format(self.TEMPLATE, pos)

    def display_page (self, year, pos, respond=True):
        # Don't do the common setup to save time since most of it is not 
        # required.
        self.template_values = {}
        players = ff.FFPlayerList(year, pos=pos)
        self.set_value('players', players)
        self.set_title("Player List")
        self.render(self.TEMPLATE, cache_name=self.create_cache_name(pos),
                    respond=respond)

    def get (self):
        pos  = self.request.get('pos', None)
        year  = self.request.get('year', ffdb.FFDBSeason.current_season())
        if not self.render_from_cache(self.create_cache_name(pos)):
            self.display_page(year, pos)
        

class Player(FFPage):
    """
    Data for an individul player.
    """
    def get (self):
        menu = self.request.get('menu', 0)
        super(Player, self).get(menu)
        player_key = self.request.get('player_key', None)

        if player_key != None:
            player = ff.FFPlayerList(self.year, 
                                     player_key=player_key).find_player(
                                                               player_key)
        else:
            player = None

        if player_key == None:
            self.error("No player specified")
            player = None
        elif player == None:
            self.error("Unable to find player data for '{}'".format(player_key))
        else:
            self.set_value('player', player)
            self.set_value('current_week', self.league.current_week())
            self.add_tab(Tab(player.name, "details"))
            self.render("player.html")


class ViewAllTeams(FFPage):

    TEMPLATE="allteams.html"
    MENU=0

    def display_page (self, respond=True):
        self.set_value("league", self.league)
        self.set_title("Top Scorers")
        self.add_tab(Tab("This Week", "weekly"))
        self.add_tab(Tab("Overall", "overall"))
        self.render(self.TEMPLATE, cache_name=self.TEMPLATE, respond=respond)

    def get (self):
        if not self.render_from_cache(self.TEMPLATE):
            super(ViewAllTeams, self).get(self.MENU, populate_teams=True)
            self.display_page()


class ViewTeams(FFPage):

    def get (self):
        super(ViewTeams, self).get(1)

        manager = self.request.get('manager', None)

        self.set_value('manager', manager)
        self.set_value('team', ff.FFTeam(self.year, manager=manager))

        submenu = OrderedDict()
        for team in self.league:
            # Make sure the manager name is url safe. i.e. no spaces etc.
            submenu[team.manager] = "./teams.html?manager={}".format(
                                                  team.safemgr)

        self.set_value('submenu', submenu)
        self.set_title("Team Sheet")
        self.add_tab(Tab("Team Sheet", "teamsheet"))
        self.add_tab(Tab("Ex-players", "explayers"))
        self.render("teams.html")

class EditTeam(FFPage):  
    def get (self):
        super(EditTeam, self).get(2)

        no_user = self.user == None
        # Allow team creation in week 1 since auction sometimes happens in
        # this week.
        can_create = self.league.current_week() <= 1
        team = None

        self.add_tab(Tab("Substitutions", "subs"))
        self.add_tab(Tab("Change Name", "changename"))
        
        if not no_user:
            # Try and load the team for this userid. There may not be one if
            # the user who is logged in has not entered one.
            try:
                team = ff.FFTeam(self.year, userid=self.user.user_id())
            except KeyError as e:
                team = None
            else:
                if team != None:
                    team.populate_fixtures()

        self.set_value('no_user', no_user)
        self.set_value('can_create', can_create)
        self.set_value('team', team)
        self.set_title("Edit Team")
        self.render("myteam.html")

class AddTeam(FFPage):
    """ Handle the form used to create a new team """

    def validate_name (self, manager, userid):
        """Check that the manager and user are valid"""
        if userid == None:
            raise ValueError("User not logged in")

        if manager == None or manager == '' or manager == "Manager Name":
            raise ValueError("No manager name specified")

        if not manager[0].isalpha():
            raise ValueError(
                 "Manager name '{}' must start with a letter".format(manager))
        if re.search("[^a-zA-Z0-9'\- ]", manager) != None:
            raise ValueError(
           "Manager name can only contain letters, numbers, `'`, `-` or space")

        team = self.league.get_team(manager=manager)
        if team != None:
            raise ValueError("Manager name '{}' already exists".format(
                                                                  manager))

        team = self.league.get_team(userid=userid)
        if team != None:
            raise ValueError("Team already exists for this user")
            
    def post(self):
        super(AddTeam, self).post()
        manager = self.request.get('manager', "")
        year = ffdb.FFDBSeason.current_season()

        try:
            self.validate_name(manager, self.user)
        except ValueError as e:
            self.error(str(e))
        else:
            # Create a new team object or update an existing one
            team = ff.FFTeam(year, self.user.user_id(), manager=manager,
                             create=True)

            # Look up the team in the data store to make sure it is there
            # before redirecting back to the team page
            if team != None:
                temp_team = None
                while temp_team == None:
                    league = ff.FFLeague(year)
                    temp_team = league.get_team(manager=manager)

            self.redirect('/myteam.html')


class Sub(FFPage):
    """ Perform a substitution """

    def post(self):
        super(Sub, self).post()
        manager = self.request.get('manager', "")
        team = ff.FFTeam(self.year, manager=manager)
        sn1 = int(self.request.get('sn1', -1))
        sn2 = int(self.request.get('sn2', -1))

        if team == None:
            self.error("No team found for '{}'", manager)
        elif team.userid != self.user.user_id():
            self.error("Only the owner of this team may update it")
        else:
            try:
                team.swap_players(sn1, sn2)
            except ff.TeamError as e:
                self.error("Error: {}".format(str(e)))
            else:
                #@@@ should loop until datastore update is visible but for now
                # just wait a moment
                sleep(0.5)
                self.redirect('/myteam.html')

class ViewLeague(FFPage):

    TEMPLATE="league.html"
    MENU=0

    def display_page (self, respond=True):
        self.set_value('league', self.league)
        self.set_title("League Table")
        self.render(self.TEMPLATE, cache_name=self.TEMPLATE, respond=respond)

    def get (self):
        if not self.render_from_cache(self.TEMPLATE):
            super(ViewLeague, self).get(self.MENU)
            self.display_page()

class Tools(FFPage):
    """ Admin tools HTML page """
    def get(self):
        super(Tools, self).get(3)
        # Set up the tabs on this page
        self.add_tab(ToolsTab("Update Scores", "update"))
        self.add_tab(ToolsTab("Weekly Update", "weeklyUpdate"))
        self.add_tab(ToolsTab("Add Player", "addPlayer"))
        self.add_tab(ToolsTab("Transfer", "transfer"))
        self.add_tab(ToolsTab("Create New Season", "newSeason"))
        self.add_tab(ToolsTab("Clear Teams", "clearAll"))
        self.add_tab(ToolsTab("Refresh Cache", "refreshCache"))
        self.add_tab(ToolsTab("Toggle Updates", "toggleUpdates"))
        self.add_tab(ToolsTab("Clear Scores", "clearScores"))

        self.set_value("pos_list", ff.FFLeague.pos_list())
        self.set_value("club_list", self.league.club_list(self.year))
        self.set_value("league", self.league)
        self.set_title("Admin Tools")
        self.render("tools.html")

class ToolActions(FFPage):
    """ Perform actions from the tools page """
    def get (self):
        super(ToolActions, self).get(populate_teams=True)
        action = self.request.get('action', None)
        result = ""
        success = False
        log = []
        
        # Select which pages to refresh
        refresh_all = False
        refresh_league = False

        # First any tools that don't require admin privaleges
        if action == "changeTeamName":
            # Change the team name
            manager = self.request.get('manager', None)
            name = self.request.get('name', None)
            team = self.league.get_team(manager=manager)
            if manager == None or name == None:
                result = "Error: Missing manager or team name"
            elif team == None:
                result = "Error: Failed to find team for {}".format(manager)
            elif team.userid != self.user.user_id():
                result = "Error: Only the owner of the team can change the name"
            else:
                # Remove any characters we don't want
                fixed_name = re.sub("[^a-zA-Z0-9'\- ]", "", name)
                team.name = fixed_name
                team.db.update(name=fixed_name)
                team.db.save()
                success = True
                refresh_league = True
                result = "Successfully changed team name for {} to '{}'".format(
                            manager, fixed_name)

        elif not self.admin:
            # The rest of the tools can only be performed by admins
            result = "This operation can only be performed by an administrator"

        elif action == "newSeason":
            # Attempt to create a new season
            start = self.request.get('start', "")
            end = self.request.get('end', "")
            try:
                ff.FFLeague.create_season(start, end)
            except ff.TeamError as e:
                result = "Error: {}".format(str(e))
            else:
                success = True
                result = "Created new seasion {}: {} - {}".format(self.year,
                                                                  start, end)
        elif action == "addPlayer":
            # Add a new temporary player to the database
            pos = self.request.get('pos', "--")
            name = self.request.get('name', None)
            player_key = "{}-temp".format(re.sub(r'\W+', '-', name.lower()))
            player_name = "{} (T)".format(name)
            player = ff.FFPlayerList(self.year, 
                                     player_key=player_key).find_player(
                                                               player_key)

            if pos not in ff.FFLeague.pos_list():
                result = "Error: Invalid position {}".format(pos)
            elif name == None:
                result = "Error: Name missing"
            elif player != None:
                result = "Error: Player with key {} already exists".format(
                                                            player_key)
            else:
                player = ffdb.FFDBPlayer()
                player.name = player_name
                player.year = self.year
                player.player_key = player_key
                player.pos = pos
                player.club = "NON"
                player.status = ffdb.FFDBPlayer.FIT
                player.reason = ""
                try:
                    player.save()
                except Exception as e:
                    result = "Error: Failed to save player {}: {}".format(
                                     player_key, str(e))
                else:
                    success = True
                    result = "Successfully added player {}".format(player_name)

                # If there isn't already a club for 'NON' then create one
                club = ffdb.FFDBClub.load(self.year, "NON")

                if club == None:
                    club = ffdb.FFDBClub()
                    club.year = self.year
                    club.abr = "NON"
                    club.name = "None"
                    club.url = ""
                    club.save()

        elif action == "update":
            # Update scores
            if self.league.season.enableUpdates == 0:
                result = "Updates are currently disabled"
            else:
                pos = self.request.get('pos', "All")
                try:
                    tools.update_player_scores(self.league.season, log, 
                                               pos=pos)
                except ParseError as e:
                    result = "Failed to update scores for position {}: {}".format(
                                                           pos, str(e))
                else:
                    tools.update_team_scores(self.league.season, log)
                    success = True
                    result = "Updating scores for position '{}' complete".format(
                                                                       pos)

        elif action == "weeklyUpdate":
            tools.weekly_update(self.league.season, log)
            success = True
            result = "Weekly update complete"

        elif action == "transfer":
            manager = self.request.get('manager', None)
            in_player_key = self.request.get('in_player', None)
            out_player_key = self.request.get('out_player', None)
            price_string = self.request.get('price', None)
            if self.is_float(price_string):
                price = float(price_string)
            else:
                price = None
            in_player = ff.FFPlayerList(self.year, 
                                        player_key=in_player_key).find_player(
                                                              in_player_key)
            team = self.league.get_team(manager=manager)
            if team != None:
                out_player = team.get_player(out_player_key)
            else:
                out_player = None

            if (manager == None or in_player_key == None or 
                out_player_key == None or price == None):
                result = "Required argument missing"
            elif in_player == None:
                result = "Failed to find player '{}'".format(in_player_key)
            elif team == None:
                result = "Failed to find team for '{}'".format(manager)
            elif out_player == None:
                result = "Failed to find player '{}' in {}'s team".format(
                                          out_player_key, manager)
            elif out_player.name == "None":
                result = "Cannot transfer out empty slots. Use the Auction page"
            elif team.get_player(in_player_key) != None:
                result = "Player {} already belongs to {}'s team".format(
                                                 in_player_key, manager)
            else:
                replace_non = out_player.club == "NON"
                if replace_non:
                   # When transferring out temporary players inherit their
                   # price and don't update the team's funds
                   price = 0;
                team.remove_player(out_player.squad_num);
                # Add the new player. If the old player was NON then we are
                # replacing a temporary player with a valid counterpart and 
                # this is allowed even if the team is maxed out for the new 
                # club
                sn = team.add_player(in_player, price, 
                                     check_clubs=not replace_non)
                new_player = team.players[sn]
                if replace_non:
                    price = out_player.price
                    new_player.db.price = price
                    new_player.db.save()
                success = True
                result = "Replaced {} with {} in slot {} in {}'s team".format(
                             out_player.name, in_player.name, sn, manager)

        elif action == "clearAll":
            # Remove all players from all teams and add 50M to their funds
            # so long as this doesn't take them over the maximum limit
            for team in self.league:
                for sn in range(ff.FFTeam.SQUADSIZE):
                    team.remove_player(sn)
                new_funds = min(50, 100 - team.funds)
                team.update_funds(new_funds)
                log.append("Added {}M to {}'s funds".format(new_funds,
                                                            team.manager))
            success = True
            result = "Successfully cleared all teams"

        elif action == "refreshCache":
            # Refresh all cached pages
            refresh_all = True
            success = True
            result = "Refreshed cached pages"

        elif action == "toggleUpdates":
            # Flip the flag to enable or disable periodic updates
            season = self.league.season
            season.enableUpdates = 1 - season.enableUpdates
            season.save()
            if season.enableUpdates == 1:
                result = "Enabled "
            else: 
                result = "Disabled "
            result += "periodic updates"

        elif action == "clearScores":
            # Reset everyone's scores - used if auction takes place after the
            # start of the season
            season = self.league.season
            tools.clear_teamplayer_scores(season, log)
            result = "Cleared all team scores"
            refresh_all = True

        else:
            result = "Unsupported action: {}".format(action)

        # Update Cache
        if refresh_league or refresh_all:
            page = ViewLeague()
            page.common_setup(page.MENU, year=self.year, league=self.league)
            page.display_page(respond=False)

        if refresh_all:
            page = ViewAllTeams()
            page.common_setup(page.MENU, year=self.year, league=self.league)
            page.display_page(respond=False)
            pos_list = ff.FFLeague.pos_list()
            # Add None for the 'all' tab
            pos_list.append(None)
            for pos in pos_list:
                page = PlayerListTab()
                page.display_page(self.year, pos, respond=False)
            
        logging.info("Performed action '{}'. Result: '{}'".format(action,
                                                                   result))
        
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps({'success': success,
                                            'result':result,
                                            'log':log}))


class AdminToolActions(ToolActions):
    """
    Extension of ToolActions which assumes the user has admin privileges
    (enforced in app.yaml). This allows cron jobs to run the tools
    """
    def get (self):
        self.admin = True
        super(AdminToolActions, self).get()

class Auction(FFPage):
    def get (self):
        """ Render the page for auctioning players """
        super(Auction, self).get(3)

        # List of teams for populating team data table
        self.set_value("team_list", [team.safemgr for team in self.league])
        # List of (squad number, possible positions) 
        possible_pos_list = []
        for i in xrange(11):
            possible_pos_list.append((i, "/".join(
                                           ff.FFTeam.valid_position_list(i))))
        for i in xrange(11, 17):
            possible_pos_list.append((i,"Sub"))
        self.set_value("possible_pos_list", possible_pos_list)
        # Lists of possible clubs and positions for dropdowns
        self.set_value("pos_list", self.league.pos_list())
        self.set_value("club_list", self.league.club_list(self.year))
        self.add_tab(Tab("Auction", "auction"))
        self.add_tab(Tab("Available Players", "available", 
                         "./freeplayers.html"))
        self.render("auction.html")


class GetPlayersFromClub(FFPage):
    """
    Return a list of players in a specific position and club and a list of
    managers whose teams can accept such a player
    """
    def get (self):
        super(GetPlayersFromClub, self).get(populate_teams=True)
        pos = self.request.get('pos', None)
        club = self.request.get('club', None)
        max_squad_num = int(self.request.get('max', ff.FFTeam.SQUADSIZE))
        try:
            unowned = int(self.request.get('unowned', 0)) != 0
        except ValueError as e:
            unowned = True
        # Get the list of unowned players matching the given club and pos
        playerlist = ff.FFPlayerList(self.year, pos=pos, club=club,
                                     unowned=unowned)
        players = {p.player_key : p.get_properties() for p in playerlist }
        # Get the list of managers with space for a player in this position
        managers = {}
        for team in self.league:
            if team.club_free(club):
                try:
                    squad_num = team.find_free_squad_num(pos, max_squad_num)
                except ff.TeamError:
                    pass
                else:
                    managers[team.safemgr] = squad_num

        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps({'players':players,
                                            'managers':managers}))


class FindUnowned(FFPage):
    """
    Return a page listing players that do not belong to any team. This is used
    within a tab on another page and does not represent a page in its own right
    """
    def get (self):
        super(FindUnowned, self).get(populate_teams=True)

        def by_total_score (player, current=False):
            """ 
            Sort function for sorting by this season's score
            """
            return player.total_score

        def by_last_season_score (player, current=False):
            """ 
            Sort function for sorting by last season's score
            """
            return player.last_season

        # Set an arbitrary cut-off of 2 weeks, after which the current score
        # is a better measure than the current season.
        current = self.league.current_week() > 2

        # Find all unowned players
        playerlist = ff.FFPlayerList(self.year, unowned=True)

        # Add the player to the appropriate position array
        unowned_lists = OrderedDict([('GK', []), ('FB', []), ('CB', []),
                                     ('M', []), ('S', [])])

        for p in playerlist:
            unowned_lists[p.pos].append(p)

        for k, list in unowned_lists.items():
            # Sort the list by score and return the first 25 items
            if current:
                list.sort(key=by_total_score, reverse=True)
            else:
                list.sort(key=by_last_season_score, reverse=True)
            unowned_lists[k] = list[:25]
        self.set_value('unowned_lists', unowned_lists)
        self.set_value('current', current)
        self.render("unowned.html")



class GetValidSubs(FFPage):
    """ Return a list of positions that a specified player can switch with """
    def get(self):
        super(GetValidSubs, self).get()
        manager = self.request.get('manager', None)
        squad_num = int(self.request.get('squad_num', -1))

        team = ff.FFTeam(self.year, manager=manager)

        valid_values = []
        for i in range(ff.FFTeam.SQUADSIZE):
            if team.can_sub(squad_num, i):
                valid_values.append(i)

        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps({'valid_values':valid_values}))

class GetLeague(FFPage):
    """ Return the league table in json format """
    def get (self):
        super(GetLeague, self).get()
        league_table = {t.manager:{'manager':t.manager,
                                   'name':t.name,
                                   'total':t.total_score,
                                   'week':t.week_score,
                                   'funds':t.funds} for t in self.league}
        
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps(league_table))

class GetTeam(FFPage):
    def get (self):
        super(GetTeam, self).get()
        manager = self.request.get('manager', None)
        team = ff.FFTeam(year=self.year, manager=manager)

        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps(team.get_properties()))

class AddPlayer(FFPage):
    """ Page used from within an ajax call to add a player to a team """

    def get (self):
        """ Get method called when data is submitted """
        super(AddPlayer, self).get()
        player_key = self.request.get('player', None)
        manager = self.request.get('manager', None)
        price = self.request.get('price', None)
        # max_squad_num may be set to a lower value during the auction
        max_squad_num = int(self.request.get('max', ff.FFTeam.SQUADSIZE))

        result = False
        error  = ""
        squad_num = -1
        team = ff.FFTeam(self.year, manager=manager)
        player = ff.FFPlayerList(self.year, 
                                 player_key=player_key).find_player(player_key)

        # First sanity check this request
        # User must be an administrator
        if not self.admin:
            error = "Error: User must be an administrator"
        elif player_key == None or manager == None or price == None:
            error = "Error: Null value supplied"
        elif not self.is_float(price):
            error = "Error: Price supplied is not a valid number"
        elif team == None:
            error = "Error: No team found for '{}'".format(manager)
        elif player == None:
            error = "Error: No player found for '{}'".format(player_key)
        elif player.manager != None:
            error = "Error: '{}' already belongs to '{}'".format(
                                                     player.name,
                                                     player.manager)
        else: 
            # The parameters seem OK so try adding a player to the team
            try:
                squad_num = team.add_player(player, float(price), 
                                            max_squad_num=max_squad_num)
            except ff.TeamError as e:
                error = "Error: {}".format(str(e))
            else:
                result = True

        # Data to return in json format
        output = {'result' : result,     # Result of this operation
                  'error'  : error,      # error string if anything went wrong
                  'squad_num' : squad_num} # squad number if call succeeded 
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps(output))


class RemovePlayer(FFPage):
    """ Page used from within an ajax call to remove a player to a team """

    def get (self):
        """ Get method called when data is submitted """
        super(RemovePlayer, self).get()
        manager = self.request.get('manager', None)
        squad_num = int(self.request.get('squad_num', None))
        # If undo is set then remove the player completely and refund the price
        # otherwise just move them to ex-players
        undo = int(self.request.get('undo', 0)) != 0

        result = False
        error  = ""
        team = ff.FFTeam(self.year, manager=manager)
        
        # First sanity check this request
        # User must be an administrator
        if not self.admin:
            error = "Error: User must be an administrator"
        elif manager == None or squad_num == None:
            error = "Error: Null value supplied"
        elif team == None:
            error = "Error: No team found for '{}'".format(manager)
        elif squad_num < 0 or squad_num > team.SQUADSIZE:
            error = "Error: Squad number {0} out of range".format(squad_num)
        else: 
            # The parameters seem OK so remove the player from the team
            team.remove_player(squad_num, undo)
            result = True

        # Data to return in json format
        output = {'result' : result,     # Result of this operation
                  'error'  : error}      # error string if anything went wrong 
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(json.dumps(output))

application = webapp2.WSGIApplication([
    ('/', MainPage),
    ('/players.html', PlayerList),
    ('/player.html', Player),
    ('/rules.html', Rules),
    ('/history.html', History),
    ('/playerlisttab.html', PlayerListTab),
    ('/allteams.html', ViewAllTeams),
    ('/teams.html', ViewTeams),
    ('/league.html', ViewLeague),
    ('/myteam.html', EditTeam),
    ('/addteam.html', AddTeam),
    ('/sub.html', Sub),
    ('/auction.html', Auction),
    ('/tools.html', Tools),
    ('/freeplayers.html', FindUnowned),
    ('/tools.json', ToolActions),
    ('/admintools.json', AdminToolActions),
    ('/getplayers.json', GetPlayersFromClub),
    ('/getsubs.json', GetValidSubs),
    ('/getteam.json', GetTeam),
    ('/addplayer.json', AddPlayer),
    ('/removeplayer.json', RemovePlayer),
    ('/league.json', GetLeague),
], debug=True)

application = gae_mini_profiler.profiler.ProfilerWSGIMiddleware(application)

def main():
    # Set the logging level in the main function
    logging.getLogger().setLevel(logging.DEBUG)
    webapp.util.run_wsgi_app(application)

if __name__ == '__main__':
    main()
