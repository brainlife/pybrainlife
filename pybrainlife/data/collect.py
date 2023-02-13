#!/usr/bin/env python3

import os,sys,glob
import requests
from matplotlib import colors as mcolors
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import json
import seaborn as sns
from itertools import combinations
from sklearn.metrics import mean_squared_error
from scipy import stats
import bct
import jgf
from scipy.signal import resample
import requests

## this will add a subjectID and sessionID column to the output data
def add_subjects_sessions(subject,session,path,data):
    
    if 'subjectID' not in data.keys():
        data['subjectID'] = [ str(subject) for f in range(len(data)) ]
    
    if 'sessionID' not in data.keys():
        data['sessionID'] = [ str(session) for f in range(len(data)) ]
        
    return data

## this function calles check_for_duplicates and attempts to find duplicates. then uses that output, sets a dumby sessionID if not present,
## and appends the object data
def append_data(subjects,sessions,paths,finish_dates,obj,filename,obj_tags,obj_datatype_tags):
        
    # check for duplicates. if so, remove
    finish_dates, subjects, sessions, paths, obj_tags, obj_datatype_tags = check_for_duplicates(obj,finish_dates,subjects,sessions,paths,obj_tags,obj_datatype_tags)

    # append data to appropriate lists
    subjects = np.append(subjects,str(obj['output']['meta']['subject']))
    if 'session' in obj['output']['meta'].keys():
        sessions = np.append(sessions,obj['output']['meta']['session'])
    else:
        sessions = np.append(sessions,'1')
    paths = np.append(paths,"input/"+obj["path"]+"/"+filename)
    finish_dates = np.append(finish_dates,obj['finish_date'])
    obj_datatype_tags = obj_datatype_tags + [obj['output']['datatype_tags']]
    obj_tags = obj_tags + [obj['output']['tags']]
    
    return finish_dates, subjects, sessions, paths, obj_tags, obj_datatype_tags

## this function will call add_subjects_sessions to add the appropriate columns and will append the object data to a study-wide dataframe
def compile_data(paths,subjects,sessions,data):
    # loops through all paths
    for i in range(len(paths)):
        # if network, load json. if not, load csv
        if '.json.gz' in paths[i]:
            tmpdata = pd.read_json(paths[i],orient='index').reset_index(drop=True)
            tmpdata = add_subjects_sessions(subjects[i],sessions[i],paths[i],tmpdata)
        else:
            if '.tsv' in paths[i]:
                sep = '\t'
            else:
                sep = ','
            tmpdata = pd.read_csv(paths[i],sep=sep)
            tmpdata = add_subjects_sessions(subjects[i],sessions[i],paths[i],tmpdata)

        #data = data.append(tmpdata,ignore_index=True)
        data = pd.concat([data,tmpdata])

    # replace empty spaces with nans
    data = data.replace(r'^\s+$', np.nan, regex=True)
    
    return data

# this function will comile network adjacency matrices into a dictionary structure
def compile_network_adjacency_matrices(paths,subjects,sessions,data):
    
    # loop through paths and append adjacency matrix to dictionary
    for i in range(len(paths)):
        data[subjects[i]+'_sess'+sessions[i]] = jgf.conmat.load(paths[i],compressed=True)[0]

    return data

### load data
## this function is useful for identifying duplicate datatypes. if it finds one, it will update the data with the latest finishing dataset.
def check_for_duplicates(obj,finish_dates,subjects,sessions,paths,obj_tags,obj_datatype_tags):
    
    # first checks if there is a session id available in the keys of the object. if finds one, then checks if the subject and session ID 
    # were already looped over. if so, will delete position in list and update with appropriate path. if it doesn't find a session ID, it
    # just attempts to find if the subject has already been looped over
    
    if 'session' in obj['output']['meta'].keys():
        if (obj['output']['meta']['subject'] in subjects) and (obj['output']['meta']['session'] in sessions):
            index = np.where(np.logical_and(subjects == obj['output']['meta']['subject'],sessions == obj['output']['meta']['session']))
            index_identified = True
        else:
            index_identified = False
    else:
        if (obj['output']['meta']['subject'] in subjects):
            # check to see if there are multiple instances for this subject
            index = np.where(subjects == obj['output']['meta']['subject'])
            index_identified = True
        else:
            index_identified = False
    
    if index_identified == True:
        if len(index[0]) > 1:
            finish_dates, subjects, sessions, paths, obj_tags, obj_datatype_tags = remove_duplicates(index,obj,subjects,sessions,paths,finish_dates,obj_tags,obj_datatype_tags)

    return finish_dates, subjects, sessions, paths, obj_tags, obj_datatype_tags

def remove_duplicates(index,obj,subjects,sessions,paths,finish_dates,obj_tags,obj_datatype_tags):
    
    # are the datatype tags the same
    tmp_datatype_tags = [ obj_datatype_tags[f] for f in list(index[0]) ]
    duplicate_datatype_tags_index = [ index[0][f] for f in range(len(list(index[0]))) if tmp_datatype_tags[f] == obj['output']['datatype_tags'] ]

    if len(duplicate_datatype_tags_index) > 0:
        duplicate_datatype_tags = True
    else:
        duplicate_datatype_tags = False

    # are the tags the same
    tmp_tags = [ obj_tags[f] for f in list(index[0]) ]
    duplicate_tags_index = [ index[0][f] for f in range(len(list(index[0]))) if tmp_tags[f] == obj['output']['tags'] ]

    if len(duplicate_tags_index) > 0:
        duplicate_tags = True
    else:
        duplicate_tags = False

    # if yes to both above, check for finish dates
    if duplicate_tags == True and duplicate_datatype_tags == True:
        duplicate_index = list(set(duplicate_tags_index) & set(duplicate_datatype_tags_index))
            
    return finish_dates, subjects, sessions, paths, obj_tags, obj_datatype_tags
    
# this will check to see if the datatype tags or tags of the datatype object exists within the filtered ('!') tags
def check_for_filter_tags(input_tags,obj,tagOrDatatypeTag):
    
    filter_checks = 0
    for i in input_tags:
        if i.replace('!','') not in obj['output'][tagOrDatatypeTag]:
            filter_checks = filter_checks+1

    return filter_checks    

## this function is the wrapper function that calls all the prevouis functions to generate a dataframe for the entire project of the appropriate datatype
def collect_data(datatype,datatype_tags,tags,filename,outPath,net_adj):

    # grab path and data objects
    objects = requests.get('https://brainlife.io/api/warehouse/secondary/list/%s'%os.environ['PROJECT_ID']).json()

    # subjects and paths
    subjects = []
    sessions = []
    paths = []
    finish_dates = []
    obj_datatype_tags = []
    obj_tags = []

    # set up output
    data = pd.DataFrame()

    # loop through objects and find appropriate objects based on datatype, datatype_tags, and tags. can include drop tags ('!'). this logic could probably be simplified
    for obj in objects:
        if obj['datatype']['name'] == datatype:
            # if datatype_tags is set, identify data using this info. if not, just use tag data. if no tags either, just append if meets datatype criteria. will check for filter with a not tag (!)
            if datatype_tags:
                # if the input datatype_tags are included in the object's datatype_tags, look for appropriate tags. if no tags, just append
                if 'datatype_tags' in list(obj['output'].keys()) and len(obj['output']['datatype_tags']) != 0:
                    if '!' in str(datatype_tags):
                        datatype_tags_to_drop = [ f for f in datatype_tags if '!' in str(f) ]
                        datatype_tag_keep = [ f for f in datatype_tags if f not in datatype_tags_to_drop ]

                        if set(datatype_tag_keep).issubset(obj['output']['datatype_tags']):
                            datatype_tag_checks = check_for_filter_tags(datatype_tags_to_drop,obj,'datatype_tags')
                            if datatype_tag_checks == len(datatype_tags_to_drop):
                                datatype_tag_filter = True
                            else:
                                datatype_tag_filter = False
                        else:
                            datatype_tag_filter = False
                    else:
                        if set(datatype_tags).issubset(obj['output']['datatype_tags']):
                            datatype_tag_filter = True
                        else:
                            datatype_tag_filter = False
                else:
                    datatype_tag_filter = False
            else:
                datatype_tag_filter = True

            if tags:
                if 'tags' in list(obj['output'].keys()) and len(obj['output']['tags']) != 0:
                    if '!' in str(tags):
                        tags_drop = [ f for f in tags if '!' in str(f) ]
                        tags_keep = [ f for f in tags if f not in tags_drop ]

                        if set(tags_keep).issubset(obj['output']['tags']):
                            tag_checks = check_for_filter_tags(tags_drop,obj,'tags')
                            if tag_checks == len(tags_drop):
                                tag_filter = True
                            else:
                                tag_filter = False
                        else:
                            tag_filter = False
                    else:
                        if set(tags).issubset(obj['output']['tags']):
                            tag_filter = True
                        else:
                            tag_filter = False
                else:
                    tag_filter = False
            else:
                tag_filter = True

            if datatype_tag_filter == True & tag_filter == True:
                finish_dates, subjects, sessions, paths, obj_tags, obj_datatype_tags = append_data(subjects,sessions,paths,finish_dates,obj,filename,obj_tags,obj_datatype_tags)

    # check if tab separated or comma separated by looking at input filename
    if '.tsv' in filename:
        sep = '\t'
    else:
        sep = ','

    # compile data
    if net_adj:
        data = {}
        data = compile_network_adjacency_matrices(paths,subjects,sessions,data)
        if outPath:
            np.save(outPath,data)
    else:
        data = compile_data(paths,subjects,sessions,data)

        # output data structure for records and any further analyses
        if outPath:
            data.to_csv(outPath,sep=sep,index=False)

    return data, obj_tags, obj_datatype_tags

### subjects dataframe generation
## this function will make a dataframe from a list of subjects and groups. will also add a color column for easy plotting
def collect_subject_data(dataPath=""):

    data = pd.read_json('input/participants.json',dtype=False)

    if dataPath:
        # output data structure for records and any further analyses
        if not os.path.exists(dataPath):
            os.mkdir(dataPath)

        data.to_csv(dataPath+'subjects.csv',index=False)

    return data

## this will create a subject-specific color for each subject in the subjects dataframe
def create_color_dictionary(data,measure,colorPalette):

    # Create subject keys and color values
    keys = data[measure].unique()
    values = sns.color_palette(colorPalette,len(keys))
    values = values.as_hex()

    # zip dictionary together
    colors_dict = dict(zip(keys,values))

    return colors_dict