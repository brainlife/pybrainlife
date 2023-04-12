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

### dataframe manipulations
## cut nodes for profilometry / timeseries data
def cut_nodes(data,num_nodes,dataPath,savename):

    # identify inner n nodes based on num_nodes input
    total_nodes = len(data['nodeID'].unique())
    cut_nodes = int((total_nodes - num_nodes) / 2)

    # remove cut_nodes from dataframe
    data = data[data['nodeID'].between((cut_nodes)+1,(num_nodes+cut_nodes))]

    # replace empty spaces with nans
    data = data.replace(r'^\s+$', np.nan, regex=True)

    if dataPath:
        # output data structure for records and any further analyses
        if not os.path.exists(dataPath):
            os.mkdir(dataPath)

        data.to_csv(dataPath+'/'+savename+'.csv',index=False)

    return data

## will compute mean dataframe 
def compute_mean_data(dataPath,data,outname):

    # make mean data frame
    data_mean =  data.groupby(['subjectID','classID','structureID']).mean().reset_index()
    data_mean['nodeID'] = [ 1 for f in range(len(data_mean['nodeID'])) ]

    if dataPath:
        # output data structure for records and any further analyses
        if not os.path.exists(dataPath):
            os.mkdir(dataPath)

        data_mean.to_csv(dataPath+outname+'.csv',index=False)

    return data_mean

### scripts related to outlier detection and reference dataframe generation
## this function will compute distance measures from input data and reference data
def compute_distance(data,references_data,measures,metric):

    # imports important distance functions
    from sklearn.metrics.pairwise import euclidean_distances
    from scipy.stats import wasserstein_distance

    # if distance metric desired is euclidean distance (i.e. for profiles), computes distance of profile from reference profile. else, just computes difference using emd
    if metric == 'euclidean':
        dist = data.groupby('subjectID',sort=False).apply(lambda x: euclidean_distances([x[measures].values.tolist(),references_data[measures].values.tolist()])[0][1]).values
    else:
        dist = data.groupby('subjectID',sort=False).apply(lambda x: wasserstein_distance(x[measures],[references_data[measures].values[0]]))

    return dist

## this function will compute simple average references for a given input data
def compute_references(x,groupby_measures,index_measure,diff_measures):
    
    # computes mean and sd of the measures in a dataframe
    references_mean = x.groupby(groupby_measures).mean().reset_index(index_measure)
    references_sd = x.groupby(groupby_measures).std().reset_index(index_measure)
    references_sd[diff_measures] = references_sd[diff_measures] * 2
    
    return references_mean, references_sd

## this function calls compute_references and compute_distance to create a dataframe of distance measures
def create_distance_dataframe(data,structures,groupby_measure,measures,dist_metric):
    
    # set up output lists that we will append to
    dist = []
    subj = []
    meas = []
    struc = []

    # loop through appropriate structures
    for i in structures:
        print(i)
        # set data for a given structure
        subj_data = data.loc[data['structureID'] == i]
        # compute reference for given structure
        references_data = compute_references(subj_data,groupby_measure,groupby_measure,measures)
        # loop through measures and compute distance from reference
        for m in measures:
            if dist_metric == 'euclidean':
                dist = np.append(dist,compute_distance(subj_data,references_data[0],m,'euclidean'))
            else:
                dist = np.append(dist,compute_distance(subj_data,references_data[0],m,'emd'))
            
            # append data to appropriate lists
            subj = np.append(subj,subj_data.subjectID.unique().tolist())
            meas = np.append(meas,[ m for f in range(len(subj_data.subjectID.unique().tolist())) ])
            struc = np.append(struc,[ i for f in range(len(subj_data.subjectID.unique().tolist())) ])

    # create distance dataframe
    dist_dataframe = pd.DataFrame()
    dist_dataframe['subjectID'] = subj
    dist_dataframe['structureID'] = struc
    dist_dataframe['measures'] = meas
    dist_dataframe['distance'] = dist
    
    return dist_dataframe

## this function is useful for saving reference.jsons for a given structure
def output_reference_json(ref_data,measures,profile,resample_points,sourceID,data_dir,filename):
    
    # loop through structures in dataframe
    for st in ref_data.structureID.unique():
        # set up important measures
        reference_json = []
        tmp = {}
        tmp['structurename'] = st
        tmp['source'] = sourceID
        # loop through measures
        for meas in measures:
            # grab data
            tmp[meas] = {}
            if profile:
                gb_frame = ref_data.loc[ref_data['structureID'] == st][['nodeID',meas]].dropna().groupby('nodeID')[meas]
            else:
                gb_frame = ref_data.loc[ref_data['structureID'] == st][[meas]].dropna()[meas]
            
            # if resample_points is a value, resamples references and computes multiple summary measures.
            # else, will just output the entire data. this second option is really only useful for non-profile/series data
            data_tmp = []
            if resample_points:                
                mean_tmp = resample(gb_frame.mean().values.tolist(),resample_points).tolist()
                min_tmp = resample(gb_frame.min().values.tolist(),resample_points).tolist()
                max_tmp = resample(gb_frame.max().values.tolist(),resample_points).tolist()
                sd_tmp = resample(gb_frame.std().values.tolist(),resampSNRle_points).tolist()
                five_tmp = resample(gb_frame.quantile(q=.05).values.tolist(),resample_points).tolist()
                twofive_tmp = resample(gb_frame.quantile(q=.25).values.tolist(),resample_points).tolist()
                sevenfive_tmp = resample(gb_frame.quantile(q=.75).values.tolist(),resample_points).tolist()
                ninefive_tmp = resample(gb_frame.quantile(q=.95).values.tolist(),resample_points).tolist()
                tmp[meas]['mean'] = mean_tmp
                tmp[meas]['min'] = min_tmp
                tmp[meas]['max'] = max_tmp
                tmp[meas]['sd'] = sd_tmp
                tmp[meas]['5_percentile'] = five_tmp
                tmp[meas]['25_percentile'] = twofive_tmp
                tmp[meas]['75_percentile'] = sevenfive_tmp
                tmp[meas]['95_percentile'] = ninefive_tmp
            else:
                data_tmp = gb_frame.values.tolist()
                tmp[meas]['data'] = data_tmp
        reference_json.append(tmp)

        if data_dir:
            with open(data_dir+'/'+filename+'_'+st+'.json','w') as ref_out_f:
                json.dump(reference_json,ref_out_f)
    
    return reference_json

## this function is used to build the reference dataset removing any subjects identified as outliers. the dataframe may or may not be useful
def build_reference_data(data,outliers,profile,data_dir,filename):
    
    # set up dataframe
    reference_data = pd.DataFrame()

    # loop through structures and measures and set data
    for s in outliers.structureID.unique():
        for m in outliers.measures.unique():
            if profile:
                meas = ['structureID','subjectID','nodeID',m]
            else:
                meas = ['structureID','subjectID',m]
            tmpdata = data[(data["structureID"] == s) & (~data['subjectID'].isin(outliers.loc[outliers['structureID'] == s].loc[outliers['measures'] == m].subjectID.unique()))][meas].reset_index(drop=True)
            reference_data = pd.concat([reference_data,tmpdata])
    # if not profile, will compute average
    if not profile:
        reference_data = reference_data.groupby(['structureID','subjectID']).mean().reset_index()

    if data_dir:
        reference_data.to_csv(data_dir+'/'+filename+'.csv',index=False)

    return reference_data

## this function will identify if a given subjects' data is an outlier based on distance from reference and a threshold percentage
def compute_outliers(distances,threshold):
    
    # set up dataframe
    outliers = pd.DataFrame()
    
    # loop through structureas and measures and identify outliers based on thereshold distance
    for i in distances.structureID.unique():
        for m in distances.measures.unique():
            tmpdata = distances.loc[distances['structureID'] == i].loc[distances['measures'] == m]
            outliers = pd.concat([outliers,tmpdata[tmpdata['distance'] > np.percentile(tmpdata['distance'],threshold)]])
            
    return outliers

## this function calls compute_outliers, create_distance_dataframe, and build_reference_data and output_reference_json to actually generate the outliers
## and final reference datasets
def outlier_detection(data,structures,groupby_measure,measures,threshold,dist_metric,build_outliers,profile,resample_points,sourceID,data_dir,filename):
    
    # set up important lists
    outliers_subjects = []
    outliers_structures = []
    outliers_measures = []
    outliers_metrics = []

    # compute distances and identify outliers
    distances = create_distance_dataframe(data,structures,groupby_measure,measures,dist_metric)
    outliers_dataframe = compute_outliers(distances,threshold)
    
    # if building references, build the reference data. otherwise, output a blank array
    if build_outliers:
        reference_dataframe = build_reference_data(data,outliers_dataframe,profile,data_dir,filename)
        reference_json = output_reference_json(reference_dataframe,measures,profile,resample_points,sourceID,data_dir,filename)
    else:
        reference_dataframe = []
        reference_json = []
        
    return distances, outliers_dataframe, reference_dataframe, reference_json

## this function is useful in identifying subjects who may have had a flipped profile as compared to a reference profile.
## calls compute_references, compute_distance.
## logic: if the distance of a subject's tract profile from a reference profile is positive and greater than a threshold percentage, then it's likely
## the data has been flipped. needs more work for all use cases. works well for easy examples like uncinate
def profile_flip_check(data,subjects,structures,test_measure,flip_measures,dist_metric,threshold,outPath):
    
    # set up important lists
    flipped_subjects = []
    flipped_structures = []
    distance = []
    flipped_distance = []

    # loop through structures
    for i in structures:
        print(i)
        # set data frame for structure, including a copy that has the test_measure flipped
        struc_data = data.loc[data['structureID'] == i]
        flipped_struc_data = struc_data.copy()
        flipped_struc_data[test_measure] = flipped_struc_data.groupby('subjectID',sort=False).apply(lambda x: np.flip(x['fa'])).tolist()

        # build reference data
        references_data = compute_references(struc_data,'nodeID','nodeID',flip_measures)

        # compute distances for normal data and for flipped. then compute difference
        dist = compute_distance(struc_data,references_data[0],test_measure,dist_metric)
        dist_flipped = compute_distance(flipped_struc_data,references_data[0],test_measure,dist_metric)
        differences = dist - dist_flipped

        # identify threshold of distances based on percentile. identify those that have positive differences and are greater than the threshold.
        # if so, append information
        percentile_threshold = np.percentile(differences,threshold)
        for m in range(len(differences)):
            if differences[m] > 0 and differences[m] > percentile_threshold:
                flipped_subjects = np.append(flipped_subjects,subjects[m])
                flipped_structures = np.append(flipped_structures,i)
                distance = np.append(distance,dist[m])
                flipped_distance = np.append(flipped_distance,dist_flipped[m])

    # generate ouput dataframe containing flipped subject data
    output_summary = pd.DataFrame()
    output_summary['flipped_subjects'] = flipped_subjects
    output_summary['flipped_structures'] = flipped_structures
    output_summary['distance'] = distance
    output_summary['flipped_distance'] = flipped_distance

    if outPath:
        output_summary.to_csv(outPath+'_flipped_profiles.csv',index=False)
        
# this function will merge the structural and diffusion data for the reference datasets
def merge_structural_diffusion_json(data,structuralPath,diffusionPath,outPath):
    for i in data.structureID.unique():
        print(i)
        with open(structuralPath+'_'+i+'.json','r') as structural_f:
            structural = json.load(structural_f)

        with open(diffusionPath+'_'+i+'.json','r') as diffusion_f:
            diffusion = json.load(diffusion_f)

        merged = [{**structural[0],**diffusion[0]}]

        if outPath:
            with open(outPath+'_'+i+'.json','w') as out_f:
                json.dump(merged,out_f)

### adjacency-matrix related fuctions for computing network values locally
# this function creates a datframe for the connectivity matrix from a network.igraph object
def build_connectivity_matrix(network,output_array=False):
    if 'weight' in network.attributes():
        conn_mat = pd.DataFrame(network.get_adjacency(attribute='weight').data)
    else:
        conn_mat = pd.DataFrame(network.get_adjacency().data)
            
    labels = network.get_vertex_dataframe()
    conn_mat = conn_mat.rename(columns=labels.name,index=labels.name)

    if output_array:
        conn_mat = conn_mat.values

    return conn_mat

# this function will build a dataframe of the LOCAL network measures computed from a network.igraph object
def build_local_measures_df(network):
    local_measurements = network.get_vertex_dataframe().reset_index() #local
    # labels = network.get_vertex_dataframe()
    # local_measurements['name'] = labels['name']

    return local_measurements

# this function will build a dataframe of the GLOBAL network measures computed from a network.igraph object
def build_global_measures_df(network):
	global_measurements = pd.DataFrame()
	for i in network.attributes():
		global_measurements[i] = [network[i]]

	return global_measurements

# this function will binarize an adjacency matrix
def binarize_matrices(data):
    
    # use brain connectivity toolbox to binarize data
    bin_data = [ bct.utils.binarize(data[f]) for f in data.keys() ]
    
    return bin_data

# this function will threshold an adjacency matrix based on a percentage threshold of subjects with a binary 1 in that node pair
def threshold_matrices(data,bin_data,thresholdPercentageSubjects):
    
    # compute sum of matrices
    sum_mat = np.zeros(np.shape(bin_data)[1:])
    
    for i in bin_data:
        sum_mat = sum_mat + i
        
    # compute threshold value
    thrs = thresholdPercentageSubjects*len(bin_data)
    
    # loop through data and make those nodes that dont meet threshold 0
    for i in data.keys():
        data[i][sum_mat < thrs] = 0
        
    return data

# this function will compute the mean within-node functional connectivity
def compute_mean_network_connectivity(data,networks,indices,out_path):

    mean_data = []
    subs = []
    nets = []

    for l in data.keys():
        for n in networks:
            tmpdata = []
            subs = np.append(subs,l)
            nets = np.append(nets,n)
            for i in indices[n]:
                for j in indices[n]:
                    if i != j:
                        tmpdata = np.append(tmpdata,data[l][int(i)][int(j)])
            mean_data = np.append(mean_data,np.mean(tmpdata))

    out_df = pd.DataFrame()
    out_df['subjectID'] = [ f.split('_sess1')[0] for f in subs ]
    out_df['FC'] = mean_data
    out_df = pd.merge(out_df,subjects_data,on='subjectID')
    out_df['structureID'] = nets

    if out_path:
        out_df.to_csv(out_path,index=False)
        
    return out_df

# this function will compute the mean network matrix
def compute_mean_network(data):
    
    mean_network = np.array(np.zeros(np.shape(data[list(data.keys())[0]])))
    
    for i in data.keys():
        mean_network = mean_network + data[i]
        
    mean_network = mean_network / len(data.keys())
    
    return mean_network
