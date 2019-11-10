import urllib.request, json 
from slugify import slugify

with urllib.request.urlopen("http://sourcefabric.airtime.pro/api/live-info") as url:
    data = json.loads(url.read().decode())
    print(data['currentShow'][0]['name'])