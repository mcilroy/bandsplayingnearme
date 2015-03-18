from bs4 import BeautifulSoup
import re
import sqlite3
import operator
import sys
from geopy.geocoders import OpenMapQuest
from geopy.distance import vincenty
import geopy
import time
import csv
import pycountry
import urllib.request
import urllib.error
from urllib import parse
import constants


# get bands from Media Monkey playlist set. Get their rating and playcount etc. Then get the tour dates from
# bandsintown.com. Get how close the bands tour dates are to your own city. Print out to csv file.
def main():
    amountType = "all"
    amount = 40
    tries_to_geoservice = 1

    # don't recreate db
    # createDb()
    addInfoNotFoundAnywhere()
    bands = get_bands()
    bands = get_band_info(bands, amountType, amount)
    bands = get_band_map_score(bands, tries_to_geoservice)
    all_data = []
    for b in bands:
        for t in b.tour_dates:
            all_data.append([b.rank, b.score, b.artist, t.date, t.venue, t.city, t.region, t.dist_score])

    all_data.sort(key=lambda x: x[3])
    all_data.sort(key=lambda x: x[7], reverse=True)
    write_to_file(all_data)


# write the band and tour dates to a csv file
def write_to_file(all_data):
    with open(constants.output_file_name, 'w', newline='', encoding='utf-8') as csvfile:
        spamwriter = csv.writer(csvfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        for data in all_data:
            spamwriter.writerow(data)


# some places are not available in either online map api or in csv table of locations. Adding manually.
def addInfoNotFoundAnywhere():
    conn = sqlite3.connect(constants.db_name)
    c = conn.cursor()
    c.execute('''INSERT OR IGNORE INTO geolocations(city, region, country, latitude, longitude) VALUES (?,?,?,?,?)''',
              ("Hollywood", "CA", "US", 34.09833, -118.32583))
    conn.commit()
    conn.close()


# create database
def createDb():
    conn = sqlite3.connect(constants.db_name)
    c = conn.cursor()
    c.execute('''DROP TABLE geolocations''')
    c.execute('''CREATE TABLE IF NOT EXISTS geolocations
             (city text NOT NULL, region text NOT NULL, country text NOT NULL, latitude real, longitude real, PRIMARY
             KEY ( city, region, country))''')
    conn.commit()
    with open(constants.geo_locations_file_name, 'r', encoding='latin-1') as csvfile:
        spamreader = csv.reader(csvfile, delimiter=',', quotechar='"')
        for i, row in enumerate(spamreader):
            if i < 245:
                continue
            c.execute(
                '''INSERT OR IGNORE INTO geolocations(city, region, country, latitude, longitude) VALUES (?,?,?,?,?)''',
                (row[3], row[2], row[1], row[5], row[6]))
    conn.commit()
    conn.close()


# for each band get the location of the tour date and compare with current hometown. score = 1/distance
def get_band_map_score(bands, tries_to_geoservice):
    conn = sqlite3.connect('geocoder.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    geolocator = OpenMapQuest()
    for i, band in enumerate(bands):
        for j, tour_date in enumerate(band.tour_dates):

            # US states are treated as countries in the table, so need to convert country label to USA instead of state
            region_is_US_state = False
            if tour_date.region == "BROOKLYN":
                tour_date.region = "NY"
            if len(tour_date.region) == 2 and tour_date.region.isupper():
                region_is_US_state = True
            print(tour_date.city, tour_date.region, region_is_US_state)
            if region_is_US_state:
                c.execute(
                    "SELECT * from geolocations where city = '" + appos(tour_date.city) + "' and region = '" + appos(
                        tour_date.region) + "'")
            else:
                try:
                    c.execute("SELECT * from geolocations where city = '" + appos(
                        tour_date.city) + "' and country = '" + appos(abbr(tour_date.region)) + "'")
                except NameError:
                    print(tour_date.region + "***123***")
                    tour_date.dist_score = -1
                    continue
            data = c.fetchone()
            # no data was found therefore look using MapQuest online API
            if data is None:
                tour_date.dist_score = -1  # assume -1 means you can't find a distance score
                continue
                print("There is no location yet in: " + ', '.join((tour_date.city, tour_date.region)))
                success = False
                unknown = False
                counter = 0
                while True:
                    try:
                        tour_date.location = geolocator.geocode(', '.join((tour_date.city, tour_date.region)))
                        time.sleep(10)  # wait 10 seconds
                        success = True
                    except geopy.exc.GeocoderTimedOut:
                        print("timed out. waiting...")
                        pass
                    except geopy.exc.GeocoderServiceError:
                        print("service error")
                        time.sleep(10)
                        unknown = True
                        success = True
                    if success:
                        break
                    else:
                        time.sleep(60)  # wait 1 minutes
                        counter += 1
                        if counter >= tries_to_geoservice - 1:
                            unknown = True
                            break
                if unknown or tour_date.location is None:
                    print("unknown")
                    tour_date.dist_score = -1
                else:
                    dist = vincenty(constants.hometown,
                                    (tour_date.location.latitude, tour_date.location.longitude)).meters
                    print("distance: " + str(dist))
                    if dist <= 0:
                        tour_date.dist_score = 0
                    else:
                        tour_date.dist_score = 1 / dist
                    unknown = ""
                    if region_is_US_state:
                        unknown = "US"
                        c.execute(
                            '''INSERT INTO geolocations(city, region, country, latitude, longitude) VALUES (?,?,?,?,?)''',
                            (tour_date.city, tour_date.region, unknown, tour_date.location.latitude,
                             tour_date.location.longitude))
                    else:
                        unknown = "unknown"
                        c.execute(
                            '''INSERT INTO geolocations(city, region, country, latitude, longitude) VALUES (?,?,?,?,?)''',
                            (tour_date.city, unknown, abbr(tour_date.region), tour_date.location.latitude,
                             tour_date.location.longitude))
                    conn.commit()
            else:
                print('Location: ' + ', '.join((tour_date.city, tour_date.region)) + ' already in table.')
                dist = vincenty(constants.hometown, (data['latitude'], data['longitude'])).meters
                print("distance: " + str(dist))
                if dist <= 0:
                    tour_date.dist_score = 0
                else:
                    tour_date.dist_score = 1 / dist
    conn.commit()
    conn.close()
    return bands


# convert to appostraphes
def appos(string):
    return re.sub(r"'", "''", string)


# handle some unique abbreviations
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
    raise NameError('country not found ' + str(string))


# get all the bands tour date info from bandsintown.com
def get_band_info(bands, amountType, amount):
    start_url = constants.bands_in_town_url
    interested_bands = []
    for i, band in enumerate(bands):
        print(band.artist)
        try:

            scheme, netloc, path, query, fragment = parse.urlsplit(start_url + band.artist.replace(" ", ""))
            path = parse.quote(path)
            link = parse.urlunsplit((scheme, netloc, path, query, fragment))

            html = urllib.request.urlopen(link).read()
            soup = BeautifulSoup(html)
        except urllib.error.HTTPError:
            pass
        except urllib.error.URLError:
            pass
        div_tag = soup.find_all("div", {'class': 'events-table'})
        band.tour_dates = []
        try:
            for j, row in enumerate(div_tag[0].find_all("tr")):
                if j == 0:
                    continue
                date_tag = row.find_all("td", {'class': 'date'})[0]
                meta = date_tag.find_all("meta")[0]
                date = meta.get("content")

                venue_tag = row.find_all('td', {'class': 'venue'})[0]
                venue = venue_tag.find_all("span")[0].contents
                location = row.find_all("td", {'class': 'location'})[0]

                a = location.find_all("a")[0]
                city = a.find_all("span")[0].contents
                region = a.find_all("span")[1].contents
                band.tour_dates.append(Tour_Date(date, venue[0], city[0], region[0]))
            interested_bands.append(band)
            if i == amount and amountType == "selectAmount":
                break
        except IndexError:
            pass
    return interested_bands


# get user's band information from media monkey
# remove outlier Beatles
# Calculate band score based on adding up ratings of songs of a band with highest rating exponentially greater than
# lowest score. 5 star rating = 25 points, 1 star rating = 1 point
def get_bands():
    conn = sqlite3.connect(constants.media_monkey_db_location)
    c = conn.cursor()
    c.execute("SELECT distinct Songs.Artist COLLATE NOCASE from Songs")
    # c.execute("SELECT distinct Songs.Artist COLLATE NOCASE  from Songs where Songs.Year >= 20140000")
    # c.execute("SELECT distinct Songs.Artist COLLATE NOCASE  from Songs where Songs.Year >= 20090000 and Songs.Album COLLATE NOCASE like '%Birp!%'")
    bands = []
    for row in c:
        band = Band()
        band.artist = row[0]
        if band.artist != "" and band.artist != "The Beatles" and band.artist != "Beatles":  # remove outlier Beatles
            bands.append(band)
    min_rating = sys.maxsize
    max_rating = 0
    min_number_of_songs = sys.maxsize
    max_number_of_songs = 0
    min_playCounter = sys.maxsize
    max_playCounter = 0
    print("get ratings and play counter")
    for band in bands:
        c.execute(
            "SELECT Rating,PlayCounter from Songs where Songs.Artist COLLATE NOCASE = '" + appos(band.artist) + "'")
        total = 0.0
        rating = 0.0
        playCounter = 0.0
        ratedSongsTotal = 0.0
        for row in c:
            total += 1
            if row[0] != -1.0:
                rating += float(row[0]) * float(row[0])  # convert to exponential curve
                ratedSongsTotal += 1
                if rating > max_rating:
                    max_rating = rating
                if rating < min_rating:
                    min_rating = rating
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
            band.rating = rating  #additive process
        if total <= 0:
            band.number_of_songs = 0
            band.playCounter = 0
        else:
            band.number_of_songs = total
            band.playCounter = playCounter / total
    for band in bands:
        band.number_of_songs = normalize(band.number_of_songs, min_number_of_songs, max_number_of_songs)
        band.playCounter = normalize(band.playCounter, min_playCounter, max_playCounter)
        band.score = band.rating  # simply add up exponential ratings of all songs to get score
    bands.sort(key=operator.attrgetter('score'))
    bands.reverse()
    rank_count = 1
    prev_score = bands[0].score
    for band in bands:
        band.rank = 0
        if prev_score == band.score:
            band.rank = rank_count
            prev_score = band.score
        else:
            rank_count += 1
            band.rank = rank_count
            prev_score = band.score

    conn.close()
    return bands


def normalize(num, mini, maxi):
    if mini == maxi:
        return maxi
    else:
        return (num - mini) / (maxi - mini)


class Band():
    def __init__(self):
        pass


class Tour_Date():
    def __init__(self, date, venue, city, region):
        self.date = date
        self.venue = venue
        self.city = city
        self.region = region


main()
print("done!")

    
