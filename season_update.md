# Instructions for updating at the start of the season

1. Manually delete the contents of all keys in the [datastore](https://console.cloud.google.com/datastore/entities;kind=FFDBPlayer;ns=__$DEFAULT$__/query/kind?project=enfantasyleague) (exporting a backup first if desired). Given that the default is 50 rows at a time this is quite a few clicks.
1. On the EnFL site create a new season giving the start date as the Friday before the first set of matches and the end date sometime after the end.
1. At [fantasyleague.com](https://www.fantasyleague.com/) log in with username and password in `player_list_json_parse.py`. Check you can view player lists and then update the number in the URL in this file and push the change to master.
1. On the EnFL site click update scores
