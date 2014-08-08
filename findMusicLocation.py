from bs4 import BeautifulSoup
import urllib2
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

def main():
    amountType = "all"
    amount = 40
    latitude = 44.2299618
    longitude = -76.4805666
    createDb()
    bands = get_bands()
    bands = get_band_info(bands,amountType,amount)
    bands = get_band_map_score(bands,(latitude,longitude))
    all_data = []
    for b in bands:
        for t in b.tour_dates:
            all_data.append([b.artist,t.date,t.venue,t.city,t.region,t.dist_score])
    
            
    all_data = sorted(all_data, key=operator.itemgetter(5,1), reverse=True)

    for data in all_data:
        print(data)

def createDb():
    conn = sqlite3.connect('geocoder.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS geolocations
             (city text NOT NULL, region text NOT NULL, latitude real, longitude real, PRIMARY KEY ( city, region))''')
    conn.commit()

    conn.close()
    
def get_band_map_score(bands,hometown):
    conn = sqlite3.connect('geocoder.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    geolocator = OpenMapQuest()
    for i,band in enumerate(bands):
        for j,tour_date in enumerate(band.tour_dates):

            c.execute("SELECT * from geolocations where city = '"+tour_date.city+"' and region = '"+tour_date.region+"'")
            data=c.fetchone()
            if data is None:
                print("There is no location yet in: "+u', '.join((tour_date.city, tour_date.region)).encode('utf-8'))
                success = False
                unknown = False
                while True:
                    try:
                        tour_date.location = geolocator.geocode(u', '.join((tour_date.city, tour_date.region)).encode('utf-8'))
                        #wait 2 seconds
                        time.sleep(10)
                        success = True
                    except geopy.exc.GeocoderTimedOut:
                        pass
                    except geopy.exc.GeocoderServiceError:
                        time.sleep(10)
                        unknown = True
                        success = True
                    if success == True:
                        break
                    else:
                        #wait 1 minutes
                        time.sleep(60)
                if unknown == True:
                    tour_date.dist_score = -1
                else:
                    dist = vincenty(hometown,(tour_date.location.latitude,tour_date.location.longitude)).meters
                    print("distance: "+str(dist))
                    if dist <=0:
                        tour_date.dist_score = 0
                    else:
                        tour_date.dist_score = 1/dist
                    c.execute('''INSERT INTO geolocations(city, region, latitude, longitude) VALUES (?,?,?,?)''', (tour_date.city,tour_date.region,tour_date.location.latitude,tour_date.location.longitude))
                    conn.commit()
            else:
                print('Location: '+u', '.join((tour_date.city, tour_date.region)).encode('utf-8')+' already in table.')
                dist = vincenty(hometown,(data['latitude'],data['longitude'])).meters
                print("distance: "+str(dist))
                if dist <=0:
                    tour_date.dist_score = 0
                else:
                    tour_date.dist_score = 1/dist
    conn.commit()
    conn.close()
    return bands
        
def get_band_info(bands,amountType,amount):

    start_url="http://www.bandsintown.com/"
    interested_bands = []
    for i,band in enumerate(bands):
        print(band.artist)
        try:
            band.artist = band.artist.replace(" ", "")
            html = urllib2.urlopen(start_url+band.artist.encode('utf-8')).read()
            soup = BeautifulSoup(html)
        except urllib2.HTTPError, e:
            pass
        except urllib2.URLError, e:
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

    c.execute("SELECT distinct Songs.Artist COLLATE NOCASE  from Songs where Songs.Year >= 20130000 and Songs.Album COLLATE NOCASE like '%Birp!%'")
    bands = []
    for row in c:
        band = Band()
        band.artist = row[0]
        if band.artist != "":
            bands.append(band)
    min_rating=sys.maxint
    max_rating=0
    min_number_of_songs = sys.maxint
    max_number_of_songs = 0
    min_playCounter= sys.maxint
    max_playCounter = 0
    print("get ratings and play counter")
    for band in bands:
        band.artist = re.sub(r"'","''",band.artist)
        c.execute("SELECT Rating,PlayCounter from Songs where Songs.Artist COLLATE NOCASE = '"+band.artist+"'")
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
        band.score = band.rating + band.number_of_songs + band.playCounter
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

    
