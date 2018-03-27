#!/usr/bin/env python                                                                                                                    
# -*- coding: utf-8 -*- 

import csv
import collections
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import pickle
import pprint
import sys

def getArtists( csv_file ):
    artist = []
    with open(csv_file, "rb") as f:
        reader = csv.reader(f)
        for row in reader:
            artist.append( row[0] )

    counter = collections.Counter( artist )
    return counter


def getUrl( name, auth_token ):
    url = 'https://api.spotify.com/v1/search?q=' + name + '&type=artist&market=US" -H "Accept: application/json" -H "Authorization: Bearer ' + auth_token
    return url

def getGenre( artists ):
    '''Return the genre - artists dictionary'''

    client_id = "b054f1c3e75e4ddba82ae5a846357e36"
    client_secret = "1b8d62fdf3d94368a6d47da3ad83fd7c"
    client_credentials_manager = SpotifyClientCredentials(client_id, client_secret)
    sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

    genre = {}
    for key in artists.keys():
        name = key
        res = sp.search( q='artist:'+ name, type='artist' )
        try:
            items = res['artists']['items']
            genre[name] = items[0]['genres']
        except:
            print "Genre not found"
    return genre

def dumpDict( dict_file, diction ):
    with open(dict_file, 'wb') as f:
        pickle.dump( diction, f, protocol=pickle.HIGHEST_PROTOCOL) 
    return

def loadDict( dict_file ):
    with open( dict_file, 'rb' ) as f:
        genre = pickle.load( f )
    return genre

def dwnldLyrics( genre, genre_dict, songdata_file ):
    res = []
    res_lyrics = []
    cnt = 0
    with open(songdata_file, "rb") as f:
        reader = csv.reader(f)
        for row in reader:
            artist, song, link, lyrics = row
            try:
                genre_list = genre_dict[ artist ]
            except:
                pass
            for g in genre_list:
                if genre in g:
                    line = ( artist, genre, song, link, lyrics  )
                    lyrics_line = lyrics.split('\n')
                    res.append( list(line) )
                    res_lyrics.append( lyrics_line )
                    break
    
    out_file = "songdata_" + genre.replace(" ", "_") + ".csv"
    with open(out_file,'wb') as f:
        wr = csv.writer(f, dialect='excel')
        wr.writerow(res)

    lyrics_out_file = "lyrics_" + genre.replace(" ", "_") + ".txt"
    f = open( lyrics_out_file, 'w')
    for song in res_lyrics:
        for line in song:
            if len( line.strip() ) > 0:
                f.write("%s\n" % line )
    return res
            
        

def main():
    artist_file = "songdata.csv"
    dict_file = "genre.pkl"
    if len(sys.argv) > 1:
        genre = " ".join( sys.argv[1:] )
        print "Generating Lyrics for the genre: ", genre
        
    else:
        print "Genre not specified Mahn! Default is rap, Yo!!"
        genre = 'rap'

    artists = getArtists( artist_file )
    #genre_dict = getGenre( artists )
    #dumpDict( dict_file, genre_dict )
    genre_dict = loadDict( dict_file )
    pp = pprint.PrettyPrinter()
    #pp.pprint( genre_dict )
    res = dwnldLyrics( genre , genre_dict, artist_file )
    #pp.pprint( res )
 
if __name__ == '__main__':
    main()

        
