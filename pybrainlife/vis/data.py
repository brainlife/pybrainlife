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

### visualization related scripts
# groups data by input measure and computes mean for each value in that column. x_stat is a pd dataframe, with each row being a single value, and each column being a different ID value or measure
def average_within_column(x_stat,y_stat,x_measure,y_measure,measure):

    X = x_stat.groupby(measure).mean()[x_measure].tolist()
    Y = y_stat.groupby(measure).mean()[y_measure].tolist()

    return X,Y

# groups data by input measure and creates an array by appending data into x and y arrays. x_stat and y_stat are pd dataframes, with each row being a single value, and each column being a different ID value or measure
# designed for test retest. x_stat and y_stat should have the same number of rows. but more importantly, should correspond to the same source (i.e. subject)
# can be same pd.dataframe, but indexing of specific subject groups
def append_within_column(x_stat,y_stat,x_measure,y_measure,measure):

    X,Y = [np.array([]),np.array([])]
    for i in range(len(x_stat[measure].unique())):
        x = x_stat[x_stat[measure] == x_stat[measure].unique()[i]][x_measure]
        y = y_stat[y_stat[measure] == y_stat[measure].unique()[i]][y_measure]

        if np.isnan(x).any() or np.isnan(y).any():
            print("skipping %s due to nan" %x_stat[measure].unique()[i])
        else:
            # checks to make sure the same data
            if len(x) == len(y):
                X = np.append(X,x)
                Y = np.append(Y,y)

    return X,Y

# unravels networks. x_stat and y_stat should be S x M, where S is the number of subjects and M is the adjacency matrix for that subject
def ravel_network(x_stat,y_stat):

    import numpy as np

    X = np.ravel(x_stat).tolist()
    Y = np.ravel(y_stat).tolist()

    return X,Y

# unravels nonnetwork data. x_stat and y_stat should be pd dataframes. x_measure and y_measure are the measure to unrvavel.
# designed for test retest. x_stat and y_stat should have the same number of rows. but more importantly, should correspond to the same source (i.e. subject)
# can be same pd.dataframe, but indexing of specific subject groups
def ravel_non_network(x_stat,y_stat,x_measure,y_measure):

    X = x_stat[x_measure].to_list()
    Y = y_stat[y_measure].to_list()

    return X,Y

# wrapper function to call either of the above scripts based on user input
def setup_data(x_data,y_data,x_measure,y_measure,ravelAverageAppend,isnetwork,measure):

    x_stat = x_data
    y_stat = y_data

    if ravelAverageAppend == 'average':
        X,Y = average_within_column(x_stat,y_stat,x_measure,y_measure,measure)
    elif ravelAverageAppend == 'append':
        X,Y = append_within_column(x_stat,y_stat,x_measure,y_measure,measure)
    elif ravelAverageAppend == 'ravel':
        if isnetwork == True:
            X,Y = ravel_network(x_stat,y_stat)
        else:
            X,Y = ravel_non_network(x_stat,y_stat,x_measure,y_measure)

    return x_stat,y_stat,X,Y

# function to shuffle data and colors
def shuffle_data_alg(X,Y,hues):

    from sklearn.utils import shuffle

    X,Y,hues = shuffle(X,Y,hues)

    return X,Y,hues

# simple display or figure save function
def save_or_show_img(dir_out,x_measure,y_measure,img_name):
    import os,sys
    import matplotlib.pyplot as plt
    import warnings

    with warnings.catch_warnings():
        # this will suppress all warnings in this block
        warnings.simplefilter("ignore")

        # save or show plot
        if dir_out:
            if not os.path.exists(dir_out):
                os.mkdir(dir_out)

            if x_measure == y_measure:
                img_name_eps = img_name+'_'+x_measure+'.eps'
                img_name_png = img_name+'_'+x_measure+'.png'
                img_name_svg = img_name+'_'+x_measure+'.svg'
            else:
                img_name_eps = img_name+'_'+x_measure+'_vs_'+y_measure+'.eps'
                img_name_png = img_name+'_'+x_measure+'_vs_'+y_measure+'.png'
                img_name_svg = img_name+'_'+x_measure+'_vs_'+y_measure+'.svg'

            plt.savefig(os.path.join(dir_out, img_name_eps),transparent=True)
            plt.savefig(os.path.join(dir_out, img_name_png))
        else:
            plt.show()

        # plt.close()

# this function will identify data within 1 sd, between 1 and 2sd, and 2 sd or greater within a scatter distrbution. intended to be used when comparing a/b
# like analyses (i.e. test retest, validity, etc)
def color_distance_scatter(x,y,perfectOrSlope):
    from scipy import stats
    import numpy as np
    import math

    ### this process creates a list of sd categories by rotating the x,y distribution
    ### by 45 degrees (to make the slope essentially zero) and computing the standard
    ### deviation along the y-axis. then, it identifies whether the y-data falls either
    ### within 1 sd, within 1-2 sd, and greater than 2 sds

    # if users want to compute distribution around perfect 45 deg equality line or around
    # the actual data slope
    if perfectOrSlope == True:
        m = 1
    else:
        m,b = np.polyfit(x,y,1)

    # compute theta as the clockwise atan rotation along m
    theta = -math.atan(m)

    # generate rotation matrix
    r = np.array([[np.cos(theta),-np.sin(theta)],[np.sin(theta),np.cos(theta)]])

    # compute rotation
    [x_dif,y_dif] = r.dot(np.array([x,y]))

    # set output variable (category)
    category = []

    # compute standard deviation thresholds for difference values
    one_sd = np.std(np.abs(y_dif))
    two_sd = one_sd * 2

    # loop through each data point and determine category (one sd: within 1 and 2 sds, two-sd: greater or equal to 2 sds, lt-one-sd: within one sd)
    category = [ 'one-sd' if one_sd <= f < two_sd else 'two-sd' if f >= two_sd else 'lt-one-sd' for f in np.abs(y_dif) ]

    return category

# this function will randomly subsample the data to make lighter visualization images
def subsample_data(x,y,percentage):

    data = np.array([x,y])
    subsample = np.random.choice(data.shape[1],int(len(data[0])*(percentage/100)),replace=False)

    sub_x = data[0,subsample]
    sub_y = data[1,subsample]

    return sub_x, sub_y
