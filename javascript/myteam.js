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

//Select a player to sub in or out. Make an ajax query to find all of the
//positions that could be a valid swap for this player
function selectRow(tr, index) {
    $(tr).addClass('highlight_last');
    $('#sn1').val(index)
    selected = index;

    // Request the possible players to substitute
    var manager = $('#manager').val();
    var squad_num = $(tr).attr('id');

    $('#first_{0}'.format(squad_num)).show();
    $.ajax({
        url: '/getsubs.json',
        data: "manager={0}&squad_num={1}".format(manager, squad_num),
        dataType: 'json',
        success: function(data) {
                      data.valid_values.forEach(function(sn) {
                          var div = $('#second_{0}'.format(sn));
                          $(div).show();
                      });
                 }
    });
}

//Unselect the selected row
function unselectRow(tr) {
    $(tr).removeClass('highlight_last');
    selected = -1;
    hideAll();
}

//Hide all hidden elements
function hideAll() {
    $('.hidden').each(function(index) {
        $(this).hide();
    });
}

// Make an ajax request to update the team name
function updateName() {
    var manager = $('#manager').val();
    //Strip out any unwanted characters
    var name = $('#inputname').val().replace(/[<>&]/g, '');
    
     
    if (name.length > 0) {
        var command = "action=changeTeamName&manager={0}&name={1}".format(
                      manager, name);
        console.log("sending command '{0}'".format(command));
        $.ajax({
            url: '/tools.json',
            data: command,
            dataType: 'json',
            success: function(data) {
                          console.log("Result: {0}".format(data.result));
                          //Update the team name on the subs tab
                          $('#teamname').empty();
                          $('#teamname').append(name);
                     },
            error: function (request, status, error) {
                alert("A server error was encountered during this operation");
                hideAll();
                }
        });
    }
}

//Function called when the DOM is fully loaded. Anything to be done on page
//load goes here
$(document).ready(function(){
    // Add a class to each table row if it is hovered over while nothing is
    // selected
    $('.row').hover(  
        //Function to call on hover enter
        function() {
            if (selected == -1) {
                $(this).addClass('hover');
            }
        },
        //Function to call on hover exit
        function() {  
            $(this).removeClass('hover');  
        }  
    );

    // If a row is clicked then toggle selected mode
    $('.row').click(function() {
        index = $(this).attr('id');
        if (selected == -1) {
            selectRow(this, index);
        } else if (selected == index) {
            unselectRow(this);
        }
    });

    // If a submit button is pressed then submit the form
    $('.submit').click(function() {
        $('#sn2').val($(this).closest('tr').attr('id'));
        $('#subform').submit();
    });

    //Handle name updates
    $('#updatename').click(function() {
        updateName();
    });


    hideAll();
});
