#encoding=utf-8
import numpy as np
import cPickle as pkl

class Embedding():
    def __init__(self, dim, static=True, model=None):
        dim_all = [50, 100, 200, 300]
        assert dim in dim_all, "dim wrong"
        if static:
            self.emb = self.read_emb(dim)
        else:
            self.emb = self.read_emb_from_pkl(model)


    def read_emb_from_pkl(self,model):
        #Load Non static word embeddings
        model_dir  = '/Users/vivekpradhan/Documents/cs291-DL4NLP/models/'
        output = model_dir + model + '/word_emb.pkl'
        emb = dict()
        with open(output, 'rb') as f:
            emb = pkl.load(f)
        return emb
    
    def read_emb(self, dim):
        emb_all = dict()
        file_name = "word_emb/glove.6B."+str(dim)+"d.txt"
        try:
            f = open(file_name, "r")
        except Exception, e:
            assert False, "fail to read file "+file_name
        lines = f.readlines()
        f.close()

        for line in lines:
            line_split = line.split()
            line_name = line_split[0]
            line_emb = line_split[1:]
            line_emb = map(lambda x: float(x), line_emb)
            line_emb = np.array(line_emb)
            emb_all[line_name] = line_emb 
        return emb_all
    
    def get_all_emb(self):
        return self.emb
    

if __name__=="__main__":
    emb = Embedding(100)
    x = emb.get_all_emb()
    print x["name"]
