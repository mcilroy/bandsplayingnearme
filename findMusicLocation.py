from bs4 import BeautifulSoup
#import urllib3
import re
import os
import sqlite3
import operator
import sys
import unicodedata
from geopy.geocoders import Nominatim
from geopy.geocoders import OpenMapQuest
from geopy.distance import vincenty
import geopy
import time
import csv
import pycountry
import urllib.request
import urllib.error
from urllib import parse

def main():
    amountType = "all"
    amount = 40
    latitude = 44.2299618
    longitude = -76.4805666
    #createDb()
    addInfoNotFoundAnywhere()
    bands = get_bands()
    bands = get_band_info(bands,amountType,amount)
    bands = get_band_map_score(bands,(latitude,longitude))
    all_data = []
    for b in bands:
        for t in b.tour_dates:
            all_data.append([b.score,b.artist,t.date,t.venue,t.city,t.region,t.dist_score])
    
    all_data.sort(key=lambda x: x[2])
    all_data.sort(key=lambda x: x[6], reverse=True)
    #all_data = sorted(all_data, key=operator.itemgetter(5,1), reverse=True)

    with open('bands_output.csv', 'w', newline='') as csvfile:
        spamwriter = csv.writer(csvfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        for data in all_data:
            spamwriter.writerow([x.encode("utf-8") if isinstance(x,str)==True else x for x in data])
    for data in all_data:
        print(data)
    
def addInfoNotFoundAnywhere():
    conn = sqlite3.connect('geocoder.db')
    c = conn.cursor()
    c.execute('''INSERT OR IGNORE INTO geolocations(city, region, country, latitude, longitude) VALUES (?,?,?,?,?)''', ("Hollywood","CA", "US", 34.09833, -118.32583))
    conn.commit()
    conn.close()
def createDb():
    conn = sqlite3.connect('geocoder.db')
    c = conn.cursor()
    c.execute('''DROP TABLE geolocations''')
    c.execute('''CREATE TABLE IF NOT EXISTS geolocations
             (city text NOT NULL, region text NOT NULL, country text NOT NULL, latitude real, longitude real, PRIMARY KEY ( city, region, country))''')
    conn.commit()
    with open('C:\\Users\\STU\\Documents\\GitHub\\bandsplayingnearme\\GeoLiteCity-latest\\GeoLiteCity_20140805\\GeoLiteCity-Location.csv', 'r', encoding='latin-1') as csvfile:
        spamreader = csv.reader(csvfile, delimiter=',', quotechar='"')
        for i,row in enumerate(spamreader):
            if i < 245:
                continue
            c.execute('''INSERT OR IGNORE INTO geolocations(city, region, country, latitude, longitude) VALUES (?,?,?,?,?)''', (row[3],row[2], row[1], row[5], row[6]))
    conn.commit()
    conn.close()
    
def get_band_map_score(bands,hometown):
    conn = sqlite3.connect('geocoder.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    geolocator = OpenMapQuest()
    for i,band in enumerate(bands):
        for j,tour_date in enumerate(band.tour_dates):
            
            region_is_US_state = False
            if tour_date.region == "BROOKLYN":
                tour_date.region = "NY"
            if len(tour_date.region) == 2 and tour_date.region.isupper():
                region_is_US_state = True
            print(tour_date.city,tour_date.region,region_is_US_state)
            if region_is_US_state:
                c.execute("SELECT * from geolocations where city = '"+appos(tour_date.city)+"' and region = '"+appos(tour_date.region)+"'")
            else:
                #print(tour_date.city,abbr(tour_date.region),tour_date.region)
                try:
                    c.execute("SELECT * from geolocations where city = '"+appos(tour_date.city)+"' and country = '"+appos(abbr(tour_date.region))+"'")
                except NameError:
                    print(tour_date.region+"***123***")
                    tour_date.dist_score = -1
                    continue
            data=c.fetchone()
            if data is None:
                print("There is no location yet in: "+', '.join((tour_date.city, tour_date.region)))
                success = False
                unknown = False
                counter = 0
                while True:
                    try:
                        tour_date.location = geolocator.geocode(', '.join((tour_date.city, tour_date.region)))
                        #wait 2 seconds
                        time.sleep(10)
                        success = True
                    except geopy.exc.GeocoderTimedOut:
                        print("timed out. waiting...")
                        pass
                    except geopy.exc.GeocoderServiceError:
                        print("service error")
                        time.sleep(10)
                        unknown = True
                        success = True
                    if success == True:
                        break
                    else:
                        #wait 1 minutes
                        time.sleep(60)
                        counter+=1
                        if counter > 3:
                            unknown = True
                            break
                if unknown == True or tour_date.location == None:
                    print("unknown")
                    tour_date.dist_score = -1
                else:
                    dist = vincenty(hometown,(tour_date.location.latitude,tour_date.location.longitude)).meters
                    print("distance: "+str(dist))
                    if dist <=0:
                        tour_date.dist_score = 0
                    else:
                        tour_date.dist_score = 1/dist
                    unknown = ""
                    if region_is_US_state:
                        unknown = "US"
                        c.execute('''INSERT INTO geolocations(city, region, country, latitude, longitude) VALUES (?,?,?,?,?)''', (tour_date.city,tour_date.region,unknown,tour_date.location.latitude,tour_date.location.longitude))
                    else:
                        unknown = "unknown"
                        c.execute('''INSERT INTO geolocations(city, region, country, latitude, longitude) VALUES (?,?,?,?,?)''', (tour_date.city,unknown,abbr(tour_date.region),tour_date.location.latitude,tour_date.location.longitude))
                    conn.commit()
            else:
                print('Location: '+', '.join((tour_date.city, tour_date.region))+' already in table.')
                dist = vincenty(hometown,(data['latitude'],data['longitude'])).meters
                print("distance: "+str(dist))
                if dist <=0:
                    tour_date.dist_score = 0
                else:
                    tour_date.dist_score = 1/dist
    conn.commit()
    conn.close()
    return bands

def appos(string):
    return re.sub(r"'","''",string)

def abbr(string):
    countries = list(pycountry.countries)
    for country in countries:
        if country.name.lower() == string.lower():
            return country.alpha2
    if string == "Taiwan":
        return "TW"
    if string == "Uk":
        return "GB"
    if string == "Russia":
        return "RU"
    raise NameError('country not found '+str(string))

def get_band_info(bands,amountType,amount):

    start_url="http://www.bandsintown.com/"
    interested_bands = []
    for i,band in enumerate(bands):
        print(band.artist)
        try:
            #http = urllib3.PoolManager()
            #print(band.artist)
            #print(type(u'sdf'))
            #print(type(band.artist))
            #print(str(band.artist))
            #print(band.artist.encode('utf-8'))
            #print(band.artist.encode('utf-8').decode('utf-8'))
            #html = http.request('GET', start_url+band.artist.encode('utf-8').decode('utf-8')).data

            scheme, netloc, path, query, fragment = parse.urlsplit(start_url+band.artist.replace(" ", ""))
            path = parse.quote(path)
            link = parse.urlunsplit((scheme, netloc, path, query, fragment))
            
            html = urllib.request.urlopen(link).read()
            #html = urllib2.urlopen(start_url+band.artist).read()
            soup = BeautifulSoup(html)
        except urllib.error.HTTPError:
            pass
        except urllib.error.URLError:
        #except urllib.error.LocationParseError:
            pass
        divTag = soup.find_all("div",{'class':'events-table'})
        band.tour_dates = []
        for i,row in enumerate(divTag[0].find_all("tr")):
            if i==0:
                continue
            date_tag = row.find_all("td",{'class':'date'})[0]
            meta = date_tag.find_all("meta")[0]
            date = meta.get("content")
            
            venue_tag = row.find_all('td',{'class':'venue'})[0]
            venue = venue_tag.find_all("span")[0].contents
            location = row.find_all("td",{'class':'location'})[0]
            
            a = location.find_all("a")[0]
            city = a.find_all("span")[0].contents
            region = a.find_all("span")[1].contents
            band.tour_dates.append(Tour_Date(date,venue[0],city[0],region[0]))
        interested_bands.append(band)
        if i == amount and amountType == "selectAmount":
            break
    return interested_bands
        
    
                
                
        
def get_bands():
    conn = sqlite3.connect("C:\\Users\\STU\\AppData\\Local\\MediaMonkey\\MM.DB")
    c = conn.cursor()

    c.execute("SELECT distinct Songs.Artist COLLATE NOCASE  from Songs where Songs.Year >= 20090000")
    #c.execute("SELECT distinct Songs.Artist COLLATE NOCASE  from Songs where Songs.Year >= 20090000 and Songs.Album COLLATE NOCASE like '%Birp!%'")
    bands = []
    for row in c:
        band = Band()
        band.artist = row[0]
        if band.artist != "":
            bands.append(band)
    min_rating=sys.maxsize
    max_rating=0
    min_number_of_songs = sys.maxsize
    max_number_of_songs = 0
    min_playCounter= sys.maxsize
    max_playCounter = 0
    print("get ratings and play counter")
    for band in bands:
        c.execute("SELECT Rating,PlayCounter from Songs where Songs.Artist COLLATE NOCASE = '"+appos(band.artist)+"'")
        total = 0.0
        rating = 0.0
        playCounter = 0.0
        ratedSongsTotal = 0.0
        for row in c:
            total += 1
            if row[0] != -1.0:
                rating += float(row[0])
                ratedSongsTotal += 1
                if float(row[0]) > max_rating:
                    max_rating = float(row[0])
                if float(row[0]) < min_rating:
                    min_rating = float(row[0])
            playCounter += int(row[1])
            if int(row[1]) > max_playCounter:
                max_playCounter = int(row[1])
            if int(row[1]) < min_playCounter:
                min_playCounter = int(row[1])
        if total > max_number_of_songs:
            max_number_of_songs = total
        if total < min_number_of_songs:
            min_number_of_songs = total
        if ratedSongsTotal <= 0:
            band.rating = 0
        else:
            band.rating = rating/ratedSongsTotal
        if total <= 0:
            band.number_of_songs = 0
            band.playCounter = 0
        else:
            band.number_of_songs = total
            band.playCounter = playCounter/total
    for band in bands:
        band.rating = normalize(band.rating,min_rating,max_rating)
        band.number_of_songs = normalize(band.number_of_songs,min_number_of_songs,max_number_of_songs)
        band.playCounter = normalize(band.playCounter,min_playCounter,max_playCounter)
        band.score = (0.4*band.rating) + (0.2*band.number_of_songs) + (0.4*band.playCounter)
    bands.sort(key=operator.attrgetter('score'))
    bands.reverse()
    conn.close()
    return bands
    
    
def normalize(num,mini,maxi):
    if mini == maxi:
        return maxi
    else:
        return (num-mini)/(maxi-mini)

class Band():
    def __init__(self):
        pass
class Tour_Date():
    def __init__(self,date,venue,city,region):
        self.date = date
        self.venue = venue
        self.city = city
        self.region = region

main()
print("done!")

    
