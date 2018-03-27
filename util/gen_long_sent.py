import sys

fname = "q_train.txt"
lines_to_append = 4


if len( sys.argv ) < 3:
    print "Usage: python gen_long_sent.py q_train.txt 4"
    exit(0)

fname = sys.argv[1]
lines_to_append = int(sys.argv[2])


def combine_sent( fname, length ):
    cnt = 0
    tr = []
    with open( fname ) as f:
        content = f.readlines()
        big_sent = ""
        for c in content:
            cnt += 1
            big_sent += c.rstrip() + " <eos> "
            if cnt % length == 0:
                big_sent.replace("\n", " <eos> ")
                tr.append( big_sent )
                big_sent = ""
    return tr

def write_to_file( fname, tr ):
    out_file = fname[:-4] + "_" + str( lines_to_append ) + fname[-4:] 
    f = open( out_file, 'w' )
    for t in tr:
        f.write( "%s\n" % t )



if __name__ == '__main__':
    tr = combine_sent( fname, lines_to_append )
    write_to_file( fname, tr )
