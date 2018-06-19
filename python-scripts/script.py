## compute_input.py

import sys, json, numpy as np, pandas as pd


def hist(data):
    df1 = data['A'].value_counts()
    dict_temp ={}
    
    dict_temp['A'] = list(df1.index.astype(str))
    dict_temp['B'] = list(df1.values.astype(str))
    
    print(json.dumps(dict_temp))

def columns(data):
    print(list(data.columns))
    
def main():
    #get our data as an array from read_in()    
    sessId = sys.argv[1]
    type = sys.argv[2]
    
    with open('../data/data.json', 'r') as f:
        datastore = json.loads(f.read())
    
    file = datastore['path']
    data = pd.read_csv(file)
    
    if type == 'hist':
        hist(data)
    elif type == 'columns':
        columns(data)

    sys.stdout.flush()

    

#start process
if __name__ == '__main__':
    main()