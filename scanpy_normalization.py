from itertools import combinations

import multiprocessing
import scanpy.api as sc
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.preprocessing import quantile_transform
from scipy.sparse import csc_matrix
from scipy.sparse import coo_matrix

from granatum_sdk import Granatum

# import pandas as pd
# import seaborn as sns


nans = np.array([np.nan, np.nan])
zeros = np.array([0, 0])


def trim_extreme(x, a, b):
    low = np.percentile(x, a)
    high = np.percentile(x, b)
    filtered = x[(x > low) & (x < high)]
    return filtered.copy()


def make_plot(adata, log_trans=False):
    violin_data = []
    for cell in adata.X:
        filtered = cell.toarray().flatten()
        #filtered = trim_extreme(filtered, 5, 95)
        if log_trans:
            #cell = np.log1p(cell)
            filtered = np.log1p(filtered)
        if filtered.shape[0] == 0:
            #cell = zeros
            filtered = zeros

        violin_data.append(filtered)

    plt.figure()
    plt.boxplot(violin_data)
    plt.xlabel('Cells')
    plt.ylabel('Expression lvl (log transformed)')
    plt.tight_layout()

def quantile_normalization(mat):
    # double argsort for getting the corresponding ranks for
    # each element in the vector

    # rank_mat = np.argsort(np.argsort(mat, 1), 1, kind='stable')
    rank_mat = np.argsort(np.argsort(mat, 1), 1)
    medians = np.median(np.sort(mat, 1), 0)
    normalized = np.zeros_like(mat)

    for i in range(rank_mat.shape[0]):
       normalized[i, :] = medians[rank_mat[i, :]]

    # normalized = quantile_transform(mat, copy=False)

    #return normalized.tolist()
    return sc.AnnData(csc_matrix(normalized))

def pandas_from_ann_data(adata):
    matrix = adata.X.T.toarray().tolist()
    sampleIds = adata.obs_names.tolist()
    geneIds = adata.var_names.tolist()
    sparse_matrix = coo_matrix(matrix)
    df = pd.DataFrame.sparse.from_spmatrix(sparse_matrix, index=geneIds, columns=sampleIds)
    return df

def ann_from_pandas(df):
    matrix = df.where((pd.notnull(df)), 0).values.tolist()
    geneIds = df.index.values.tolist()
    sampleIds = df.columns.values.tolist()

    sparse_matrix = coo_matrix(matrix).tocsc()
    adata = sc.AnnData(sparse_matrix.transpose())

    adata.var_names = geneIds
    adata.obs_names = sampleIds
    return adata
 
def order_of_elems(test1, added_noise=0.1, rng=np.random.default_rng(0)):
    test1 = (test1+rng.normal(0, added_noise, test1.shape[0])).sort_values(kind="stable", ascending=False)
    test1.values[:] = np.arange(test1.shape[0])
    return test1.sort_index(kind="stable")

def rank_normalization(data, added_noise=0.1, rng=np.random.default_rng(0)):
    return data.T.apply(order_of_elems, added_noise=added_noise, rng=rng).T

def main():
    gn = Granatum()

    adata = gn.ann_data_from_assay(gn.get_import('assay'))
    num_cells_to_sample = gn.get_arg('num_cells_to_sample')
    method = gn.get_arg('method')
    log_trans_when_plot = gn.get_arg('log_trans_when_plot')
    seed = gn.get_arg('seed')

    if num_cells_to_sample > adata.shape[0]:
        num_cells_to_sample = adata.shape[0]

    # sampled_cells_idxs = np.sort(np.random.choice(adata.shape[0], num_cells_to_sample, replace=False))
    sampled_cells_idxs = np.arange(0, min(num_cells_to_sample, adata.shape[0]), 1)

    make_plot(adata[sampled_cells_idxs, :], log_trans=log_trans_when_plot)
    gn.add_current_figure_to_results(
        'Before normalization: Each bar in the box plot represents one cell.',
        height=350,
        dpi=75 * 40 / max(40, num_cells_to_sample)
    ) 

    if method == 'quantile':
        adata2 = quantile_normalization(adata.X.toarray())
        adata2.var_names = adata.var_names.tolist()
        adata2.obs_names = adata.obs_names.tolist()
        adata = adata2
    elif method == 'quantile_df':
        df = pandas_from_ann_data(adata)
        df_sorted = pd.DataFrame(np.sort(df.values, axis=0, kind='stable'), index=df.index, columns=df.columns)
        df_mean = df_sorted.mean(axis=1)
        df_mean.index = np.arange(1, len(df_mean) + 1)
        df_qn = df.rank(method="min").stack().astype(int).map(df_mean).unstack()
        adata = ann_from_pandas(df_qn)
    elif method == 'rank':
        df = pandas_from_ann_data(adata)
        df = rank_normalization(df.copy(), added_noise=0.1, rng=np.random.default_rng(seed))
        adata = ann_from_pandas(df)
    elif method == 'scanpy':
        sc.pp.normalize_total(adata)
    else:
        raise ValueError()

    make_plot(adata[sampled_cells_idxs, :], log_trans=log_trans_when_plot)
    gn.add_current_figure_to_results(
        'After normalization: Each bar in the box plot represents one cell.',
        height=350,
        dpi=75 * 40 / max(40, num_cells_to_sample)
    )

    gn.export_statically(gn.assay_from_ann_data(adata), 'Normalized assay')

    gn.commit()


if __name__ == '__main__':
    main()
