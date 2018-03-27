import csv
import random
import re

genre_1_file = "rap.csv"
genre_2_file = "country.csv"

def clean_str( string, lower=True ):
    """
    Tokenization/string cleaning for the datasets.
    Taken from https://github.com/yoonkim/CNN_sentence/blob/master/process_data.py
    """
    if string == '<eos>':
        return string

    #Remove anything that is not a character, a digit, a bracket etc. from the string
    string = re.sub( r"[^A-Za-z0-9(),!?\'\`]"," ", string )
    #Add a space between the apostrophes so that they are not counted as a single word
    string = re.sub( r"\'s"," 's", string )
    string = re.sub( r"\'ve", " 've", string )
    string = re.sub( r"\'re", " 're", string )
    string = re.sub( r"\'d", " 'd", string )
    string = re.sub( r"\'ll", " 'll", string )
    string = re.sub( r"n\'t", " n't", string )
    string = re.sub( r",", " , ", string )
    string = re.sub( r"!", " ! ", string )
    string = re.sub( r"\(", " ( ", string )
    string = re.sub( r"\)", " ) ", string )
    string = re.sub( r"\?", " ? ", string )
    string = re.sub( r"\s{2,}"," ", string )

    result = string.strip()
    if lower:
        result = result.lower()

    return result

def load_data( genre_1_file, genre_2_file, num_sentences = None  ):
    rap_data = []
    country_data = []
    with open(genre_1_file, 'rb') as f1:
        rap_reader = csv.reader( f1 )
        for row in rap_reader:
            cnt = 0
            if not num_sentences:
                proc_row = " ".join( row[3].replace("\n", " <eos> ").split() )
                rap_data.append([ proc_row, 1 ])
            else:
                proc_row = row[3].splitlines()
                line_app = ""
                for line in proc_row:
                    line_app += line + " <eos> "
                    cnt += 1
                    if cnt % num_sentences == 0:
                        line_app = " ".join( line_app.split() )
                        clean_line_app = ""
                        for word in line_app.split():
                            clean_line_app += clean_str( word ) + " "
                        rap_data.append( [ clean_line_app, 1 ] )
                        line_app = ""

    with open(genre_2_file, 'rb') as f2:
        country_reader = csv.reader( f2 )
        for row in country_reader:
            cnt = 0
            if not num_sentences:
                proc_row = " ".join( row[4].replace("\n", " <eos> ").split()  )
                country_data.append([ proc_row, 0 ])
            else:
                proc_row = row[4].splitlines()
                line_app = ""
                for line in proc_row:
                    line_app += line + " <eos> "
                    cnt += 1
                    if cnt % num_sentences == 0:
                        line_app = " ".join( line_app.split() )
                        clean_line_app = ""
                        for word in line_app.split():
                            clean_line_app += clean_str( word ) + " "
                        country_data.append( [ clean_line_app, 0 ] )
                        line_app = ""

    return rap_data, country_data

def gen_op( tr_data, val_data, test_data, num_sentences=None ):
    q_tr_f = open('q_train.txt', 'w' )
    r_tr_f = open('r_train.txt', 'w' )
    s_tr_f = open('s_train.txt', 'w' )

    q_val_f = open('q_val.txt', 'w' )
    r_val_f = open('r_val.txt', 'w' )
    s_val_f = open('s_val.txt', 'w' )
        
    q_test_f = open('q_test.txt', 'w' )
    r_test_f = open('r_test.txt', 'w' )
    s_test_f = open('s_test.txt', 'w' )

    random.shuffle( tr_data )    
    random.shuffle( val_data )    
    random.shuffle( test_data )    
    
    for t in tr_data:
        q_tr_f.write( "%s\n" % t[0] )
        r_tr_f.write( "%s\n" % t[0] )
        s_tr_f.write( "%s\n" % t[1] )

    for t in val_data:
        q_val_f.write( "%s\n" % t[0] )
        r_val_f.write( "%s\n" % t[0] )
        s_val_f.write( "%s\n" % t[1] )
        
    for t in test_data:
        q_test_f.write( "%s\n" % t[0] )
        r_test_f.write( "%s\n" % t[0] )
        s_test_f.write( "%s\n" % t[1] )

def print_stat( data ):
    cnt_country = 0
    cnt_rap = 0
    for t in data:
        if t[1] == 0:
            cnt_country += 1
        if t[1] == 1:
            cnt_rap += 1

    print "Total: ", len( data )
    print " Rap: ", cnt_rap
    print " Country: ", cnt_country
        
if __name__ == '__main__':
    rap_data, country_data = load_data( genre_1_file, genre_2_file, num_sentences=None )
    country_data = country_data[:len(rap_data)]
    N = int(len( country_data ) * 0.75 )
    tr_data = country_data[: int(N * 0.8)] + rap_data[: int( N * 0.8 )]
    val_data = country_data[int(N * 0.8): int(N * 0.9)] + rap_data[ int( N * 0.8 ): int( N * 0.9 )]
    test_data = country_data[ int(N * 0.9): ] + rap_data[int( N * 0.9 ): ]
    
    #Print Stats
    print_stat( tr_data )
    
    gen_op( tr_data, val_data, test_data ) 
    









