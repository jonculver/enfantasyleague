//Parameters

//Whether or not a player to substitute has been selected
var selected = -1;

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

// Fill in the message boxes for the given ID
function setMessage(action, result, log) {
    var mes_id = "#mes-{0}".format(action);
    var log_id = "#log-{0}".format(action);
    $(mes_id).append(result);
    $(mes_id).show();
    if (log.length > 0) {
        log.forEach(function(line) {
            $(log_id).append("{0}\n".format(line));
        });
        $(log_id).show();
    }
}

// Send a request to the server to perform the action and display the result
function performAction(action, command) {
    cmd_data = "action={0}{1}{2}".format(action, command != "" ? "&" : "",
                                         command)
    console.log("sending command '{0}'".format(cmd_data)); 
    $.ajax({
        url: '/tools.json',
        data: cmd_data,
        dataType: 'json',
        success: function(data) {
                      console.log("Result: {0}".format(data.result));
                      setMessage(action, data.result, data.log);
                 },
        error: function (request, status, error) {
            alert("A server error was encountered during this operation");
            hideAll();
            }
    });
}

// Send a request to update scores
function updateScores(action) {
    setMessage(action, "Updating scores. This may take a while...", "");
    performAction(action, "");
}

function newSeason(action) {
    var start = $('#seasonStart').val();
    var end   = $('#seasonEnd').val();
    hideAll();
    performAction(action, "start={0}&end={1}".format(start, end));
}

// Clear all - show a confirmation dialogue
function clearAll(action) {
    // JqueryUI dialogue widget
	$( "#dialog-confirm" ).dialog({
		resizable: false,
		height:250,
		modal: true,
		buttons: {
			"Clear Teams": function() {
                performAction(action, "");
				$( this ).dialog( "close" );
			},
			Cancel: function() {
				$( this ).dialog( "close" );
			}
		}
	});
}

// Add a new player
function addPlayer(action) {
    var pos = $('select[name=pos] option:selected').text();
    var name = $('#playername').val();
    performAction(action, "pos={0}&name={1}".format(pos,name));
}

// Perform a transfer
function transfer(action) {
    var manager = $('#manager option:selected').attr('name');
    var out_player = $('#out_player option:selected').attr('name');
    var in_player = $('#in_player option:selected').attr('name');
    var price = $('#price').val();
    performAction(action, "manager={0}&out_player={1}&in_player={2}&price={3}".format(
                              manager, out_player, in_player, price));

}

//Update the In player list using values from other dropdowns to make an ajax
//query which returns the allowed values
function updateInPlayerList() {
    var pos = $('#in_pos option:selected').text();
    var club = $('#in_club option:selected').text();
    console.log("UpdatePlayerList: " + pos + " " + club);

    // If both a position and club have been specified then find the
    // corresponding player list
    if (pos != '' && club != '') {
        $.ajax({
            url: '/getplayers.json',
            data: 'unowned=0&pos=' + pos + '&club=' + club, 
            dataType: 'json',
            success: function(data) {
                var listItems= "<option></option>";
                //Add the players to the dropdown list
                var playerList = data.players;
                for (var key in playerList) {
                    var player = playerList[key];
                    console.log("  {0}".format(player.name));
                    listItems += '<option name="{0}">{1}</option>'.format(
                                                 key, player.name);
                }
                $('#in_player').empty();
                $('#in_player').append(listItems);
            }
        });
    }
}

// Update the list of players belonging to the specified manager
function updateOutPlayerList() {
    var manager = $("#manager option:selected").attr('name');
    //Make an ajax query to get the data for this team
    console.log("Querying data for {0}".format(manager));
    $.ajax({
        url: '/getteam.json',
        data: 'manager=' + manager, 
        dataType: 'json',
        success: function(data) {
            var listItems= "<option></option>";
            var sn = 0;
            data.players.forEach(function(player) {
                if (player.name != "None") {
                    // Cannot transfer 'None' players. Use the auction UI
                    console.log("  {0}".format(player.name));
                    listItems += '<option name="{0}">{1}</option>'.format(
                                                     player.player_key, 
                                                     player.name);
                }
            });
            $('#out_player').empty();
            $('#out_player').append(listItems);
        }
    });
}

//Hide all hidden elements
function hideAll() {
    $('.hidden').each(function(index) {
        $(this).empty();
        $(this).hide();
    });
}


//Function called when the DOM is fully loaded. Anything to be done on page
//load goes here
$(document).ready(function(){
    //Handle button clicks
    $(".toolbutton").click(function(){
        var action = $(this).attr('id')
        hideAll();

        switch (action) {
        case "update":
            updateScores(action);
            break;
        case "addPlayer":
            addPlayer(action);
            break;
        case "transfer":
            transfer(action);
            break;
        case "newSeason":
            newSeason(action);
            break;
        case "clearAll":
            clearAll(action);
            break;
        default:
            //For everything else just do the action
            performAction(action, "")
            break;
        }
    });

    //If the position changes then update the player list
    $('#in_pos').change(function() {
        updateInPlayerList();
    });

    //If the club changes then update the player list
    $('#in_club').change(function() {
        updateInPlayerList();
    });

    //If a manager is selected update their team
    $('select[name=manager]').change(function() {
        updateOutPlayerList()
    });

    hideAll();
});
