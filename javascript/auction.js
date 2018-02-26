//Parameters

//Number of players up for auction
var WITHOUTSUBS=12;

//Total number of players in the team
var WITHSUBS=17;

//Global Variables

//Ajax query result for player list
var playerList;

//The number of rows to consider
var active_rows = WITHOUTSUBS;

//Whether or not the remove button has been pressed
var removing = false;

//Define a .format method on strings similar to python's
if (!String.prototype.format) {
  String.prototype.format = function() {
    var args = arguments;
    return this.replace(/{(\d+)}/g, function(match, number) { 
      return typeof args[number] != 'undefined'
        ? args[number]
        : match
      ;
    });
  };
}

//Clear and disable the elements relating to a particular player
function clearPlayer() {
    console.log("Clearing form data");
    setMessage('');
    $('input[name=price]').val('');
    $('#add').attr('disabled', 'disabled');
}

//Clear and disable all the elements on the form
function clearForm() {
    // Clear and disable player names
    $('#player').empty();
    $('#player').attr('disabled', 'disabled');
    $('#manager').empty();
    $('#manager').attr('disabled', 'disabled');
    clearPlayer();
    clearHighlights();
}

//Reset the club and position selections
function resetClubPos() {
    $('#pos').val('');
    $('#club').val('');
}

//Clear the data in a team div in preparation for reloading it
function clearTeam(id) {
    $('#' + id).empty();
    for (var i = 0; i < WITHSUBS; i++) {
        $('#{0}_pos_{1}'.format(id, i)).empty();
    }
}

//Set the status message to display below the form
function setMessage(string) {
    $('#message').empty();
    $('#message').append(string);
}

//Query data for a team and update the appropriate divs
function updateTeam(id) {
    //Make an ajax query to get the data for this team
    console.log("Querying data for {0}".format(id));
    $.ajax({
        url: '/getteam.json',
        data: 'manager=' + id, 
        dataType: 'json',
        success: function(data) {
            //Clear the existing data
            clearTeam(id);
            $('#' + id).append("{0} - {1}M".format(data.manager,
                                                 data.funds.toFixed(1)));
            for (var i = 0; i < WITHSUBS; i++) {
                if (data.players[i].name != "None") {
                    divid = '#{0}_pos_{1}'.format(id, i);
                    $(divid).append("{0} {1} {2}M".format(
                                               data.players[i].name,
                                               data.players[i].club,
                                               data.players[i].price));
                } 
            }
        }
    });
}

//Remove the highlights for any cells that have them
function clearHighlights() {
    $('.highlight_club').each(function() {
        $(this).removeClass('highlight_club', '');
    });
    $('.highlight_free').each(function() {
        $(this).removeClass('highlight_free', '');
    });
    $('.highlight_last').each(function() {
        $(this).removeClass('highlight_last', '');
    });
}

//Return the display name for a given safe name
function mgrDisplayName(mgr) {
    var display = $('#' + mgr).html().split(" - ")[0];
    return (display);
}

//Highlight all players belonging to the specified club
function highlightPlayers(club) {
    $('.team').each(function(index) {
        var manager = $(this).attr('id');
        
        for (var i = 0; i < WITHSUBS; i++) {
            var div = '#{0}_pos_{1}'.format(manager, i);
            var text = $(div).html();
            var td = $(div).closest("td");

            if (text.indexOf(club) > 0) {
                td.addClass('highlight_club');
            }
        }
    });
}

//Update the player list using values from other dropdowns to make an ajax
//query which returns the allowed values
function updatePlayerList() {
    var pos = $('select[name=pos] option:selected').text();
    var club = $('select[name=club] option:selected').text();
    console.log("UpdatePlayerList: " + pos + " " + club);

    clearForm();

    // If both a position and club have been specified then find the
    // corresponding player list
    if (pos != '' && club != '') {
        $.ajax({
            url: '/getplayers.json',
            data: 'unowned=1&pos=' + pos + '&club=' + club + '&max=' + active_rows, 
            dataType: 'json',
            success: function(data) {
                var listItems= "<option></option>";
                //Set the global player list for use later
                playerList = data.players;
                //Add the players to the dropdown list
                for (var key in playerList) {
                    var player = playerList[key];
                    console.log("  {0}".format(player.name));
                    listItems += '<option name="{0}">{1}</option>'.format(
                                                 key, player.name);
                }
                $('#player').removeAttr('disabled');
                $('#player').append(listItems);
                //Add the managers to the dropdown list and highlight the
                //position where the new player would go
                listItems= "<option></option>";
                var managerList = data.managers;
                for (var mgr in managerList) {
                    console.log("  {0} ({1})".format(mgr, managerList[mgr]));
                    listItems += '<option name="{0}">{1}</option>'.format(
                                      mgr, mgrDisplayName(mgr));
                    var div = '#{0}_pos_{1}'.format(mgr, managerList[mgr]);
                    $(div).closest("td").addClass('highlight_free');
                }
                $('#manager').removeAttr('disabled');
                $('#manager').append(listItems);
                //highlight players from the same club
                highlightPlayers(club);
            }
        });
    }
}

//Highlight the last selection and keep updating the team until it is reflected
function highlightLast (manager, squad_num, removing) {
    updateTeam(manager);
    div = $('#{0}_pos_{1}'.format(manager,squad_num));
    td = div.closest('td');
    td.addClass('highlight_last');
    if ((!removing && div.html() == '') || (removing && div.html() != '')) {
        //Change isn't reflected yet. Wait half a second and then try again
        setTimeout(function() {
            highlightLast(manager, squad_num, removing);
        }, 500);
    }
}

//Make an ajax query to add a player
function addPlayer() {
    var pos = $('select[name=pos] option:selected').text();
    var club = $('select[name=club] option:selected').text();
    var player_id = $('select[name=player] option:selected').attr('name');
    var player = $('select[name=player] option:selected').text();
    var manager = $('select[name=manager] option:selected').attr('name');
    var price = $('input[name=price]').val();

    if (price == '') {
        setMessage("Error: No price entered");
    } else {
        $.ajax({
            url: '/addplayer.json',
            data: 'player={0}&manager={1}&price={2}&max={3}'.format(
                         player_id, manager, price, active_rows), 
            dataType: 'json',
            success: function(data) {
                if (!data.result) {
                    // Something went wrong
                    setMessage(data.error);
                } else {
                    // Success!
                    squad_num = data.squad_num;

                    //Clear the existing last player highlight and highlight 
                    //the ew one
                    $('.highlight_last').each(function() {
                        $(this).removeClass('highlight_last', '');
                    });
                    
                    clearForm();
                    resetClubPos();
                    setMessage("Added player {0} to {1}'s team".format(player,
                                                     mgrDisplayName(manager)));
                    highlightLast(manager, squad_num, false);
                }
            }
        });
    }
}

// Remove a player from a team
function removePlayer(div_id) {
    //Div id has form '<mgr>_pos_<id>'
    div_list = div_id.split("_");
    manager = div_list[0];
    squad_num = div_list[2];
    console.log("Remove {0} ({1})".format(manager, squad_num));
    $.ajax({
        url: '/removeplayer.json',
        // Set 'undo' to remove the player totally and refund the price rather
        // than move them to ex-players list
        data: 'manager={0}&squad_num={1}&undo=1'.format(manager, squad_num),
        dataType: 'json',
        success: function(data) {
                      if (!data.result) {
                          setMessage(data.error);
                      } else {
                          highlightLast(manager, squad_num, true);
                          setMessage("Removed player from position {0} in {1}'s team".format(
                                     squad_num, mgrDisplayName(manager)));
                      }
                 }
    });
}


//Enable or disable remove mode, in which existing players are highlighted and
//can be clicked to remove them
function toggleRemove() {
    removing = !removing;
    clearHighlights();
    if (removing) {
        $('#RemoveOne').addClass('hover');
    } else {
        $('#RemoveOne').removeClass('hover');
    }
    console.log("Remove mode: {0}".format(removing ? "ON" : "OFF"));
}


//Enable or disable the extra rows for subs not used in the auction
function enableSubs(enable) {
    console.log("{0} subs".format(enable ? "enabling" : "disabling"))
    $('.pos_row').each(function() {
        pos = $(this).attr('id').split("_")[1];
        if (pos > 11) {
            if (!enable) {
                $(this).hide();
                active_rows = WITHOUTSUBS;
            } else {
                $(this).show();
                active_rows = WITHSUBS;
            }
        }
    });
}

//Function called when the DOM is fully loaded. Anything to be done on page
//load goes here
$(document).ready(function(){
    //If the position changes then clear everything and update the player list
    $('select[name=pos]').change(function() {
        updatePlayerList();
    });

    //If the club changes then clear everything and update the player list
    $('select[name=club]').change(function() {
        updatePlayerList();
    });

    //If a player is selected update their details
    $('select[name=player]').change(function() {
        var key  = $('select[name=player] option:selected').attr('name');
        var player = playerList[key];
        var pos = $('select[name=pos] option:selected').text();
        var club = $('select[name=club] option:selected').text();
        clearPlayer();
        setMessage("<b>Score:</b> {0}, ".format(player.score) +
                             "<b>Last Season:</b> {0}, ".format(
                                                        player.last_season) +
                             "<b>Status:</b> {0} {1} {2}".format(
                                    player.status,
                                    player.reason != "" ? "-" : "",
                                    player.reason));
    });

    //If a manager is selected enable the price field and 'add player' button
    $('select[name=manager]').change(function() {
        var manager = $('select[name=manager] option:selected').text();
        console.log("Manager: '{0}'".format(manager));
        if (manager != '') {
            $('#add').removeAttr('disabled');
        } else {
            $('#add').attr('disabled', 'disabled');
        }
    });

    //If the clear button is pressed then reset everything
    $("form").bind("reset",function(){
        setTimeout(function(){
            clearForm();
        },50)
    });

    //If the add player button is pressed then make an ajax request to perform
    //the action
    $("#addPlayer").click(function(){
        addPlayer();
    });

    //If the toggle subs button is pressed then enable or disable the subs list
    $("#ToggleSubs").click(function(){
        var enable = false;
        if (active_rows == WITHOUTSUBS) {
            enable = true;
        }
        enableSubs(enable);
    });

    // If the refresh button is clicked update the teams
    $("#refresh").click(function(){
        $('.team').each(function(index) {
             updateTeam($(this).attr('id'));
        });
    });

    // Handle the delete button being clicked
    $("#RemoveOne").click(function() {
        toggleRemove();
    });

    // Add a class to each table cell if it is hovered over while we are in
    // removing mode
    $('.teampos').hover(  
        //Function to call on hover enter
        function() {
            if (removing && $(this).html() != '') {
                $(this).addClass('hover');
            }
        },
        //Function to call on hover exit
        function() {  
            $(this).removeClass('hover');  
        }  
    );

    // If a cell is clicked in remove mode then remove that player
    $('.teampos').click(function() {
        if (removing && $(this).html() != '') {
            removePlayer($(this).attr('id'));
        }
    });
    
    // Disable the sub rows that aren't used for the auction
    enableSubs(false);

    // Start by updating the player list on page load
    updatePlayerList();

    // Load each of the teams
    $('.team').each(function(index) {
        updateTeam($(this).attr('id'));
    });

});
