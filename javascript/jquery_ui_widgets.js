
// Accordian Widget
$(function() {
    $( "#accordion" ).accordion({heightStyle: "content",
                                 active: {{ menu_num }}
                                });
});

// Tabs Widget
$(function() {
	$( "#tabs" ).tabs({
		ajaxOptions: {
			error: function( xhr, status, index, anchor ) {
				$( anchor.hash ).html(
					"Failed to load tab contents" );
			}
		}
	});
});
