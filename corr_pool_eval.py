"""
Calculates the best performing parameter values with given testing data as specified in file
Autocalibration-Parametersweep-Testing.xlsx
"""
import sys, re, argparse, os, subprocess as sp, warnings, numpy as np, math
# import modin.pandas as pd
import pandas as pd
#from jinja2 import Template as ji
import jinja2 as ji
import ruamel.yaml as yaml
from usac_eval import ji_env, get_time_fixed_kp, insert_opt_lbreak, prepare_io
import inspect

def filter_take_end_frames(**vars):
    return vars['data'].loc[vars['data']['Nr'] > 119]


def filter_max_pool_size(**vars):
    return vars['data'].loc[vars['data']['stereoParameters_maxPoolCorrespondences'] == 40000]


def calc_rt_diff_frame_to_frame(**vars):
    if 'partitions' not in vars:
        raise ValueError('Partitions are necessary.')
    for key in vars['partitions']:
        if key not in vars['data_separators']:
            raise ValueError('All partition names must be included in the data separators.')
    if 'xy_axis_columns' not in vars:
        raise ValueError('xy_axis_columns are necessary.')
    if len(vars['data_separators']) != (len(vars['partitions']) + 2):
        raise ValueError('Wrong number of data separators.')

    needed_cols = vars['eval_columns'] + vars['it_parameters'] + vars['data_separators']
    df = vars['data'][needed_cols]
    grpd_cols = vars['data_separators'] + vars['it_parameters']
    df_grp = df.groupby(grpd_cols)
    grp_keys = df_grp.groups.keys()
    eval_log = {}
    eval_cols_log_scaling = []
    for eval in vars['eval_columns']:
        eval_log[eval] = []
    for grp in grp_keys:
        tmp = df_grp.get_group(grp)
        for eval in vars['eval_columns']:
            eval_log[eval].append(True if np.abs(np.log10(np.abs(tmp[eval].min())) -
                                                 np.log10(np.abs(tmp[eval].max()))) > 1 else False)
    for eval in vars['eval_columns']:
        if any(eval_log[eval]):
            eval_cols_log_scaling.append(True)
        else:
            eval_cols_log_scaling.append(False)

    from statistics_and_plot import replaceCSVLabels
    ret = {'data': df,
           'it_parameters': vars['it_parameters'],
           'eval_columns': vars['eval_columns'],
           'eval_cols_lname': [replaceCSVLabels(a) for a in vars['eval_columns']],
           'eval_cols_log_scaling': eval_cols_log_scaling,
           'units': vars['units'],
           'eval_init_input': None,
           'xy_axis_columns': [],
           'partitions': vars['partitions']}
    for key in vars['data_separators']:
        if key not in vars['partitions']:
            ret['xy_axis_columns'].append(key)
    return ret


def calc_rt_diff2_frame_to_frame(**vars):
    if 'partitions' not in vars:
        raise ValueError('Partitions are necessary.')
    for key in vars['partitions']:
        if key not in vars['data_separators']:
            raise ValueError('All partition names must be included in the data separators.')
    if 'xy_axis_columns' not in vars:
        raise ValueError('xy_axis_columns are necessary.')
    if len(vars['data_separators']) != (len(vars['partitions']) + 2):
        raise ValueError('Wrong number of data separators.')
    if 'keepEval' in vars:
        for i in vars['keepEval']:
            if i not in vars['eval_columns']:
                raise ValueError('Label ' + i + ' not found in \'eval_columns\'')

    needed_cols = vars['eval_columns'] + vars['it_parameters'] + vars['data_separators']
    df = vars['data'][needed_cols]
    grpd_cols = [a for a in vars['data_separators'] if a != 'Nr'] + vars['it_parameters']
    df_grp = df.groupby(grpd_cols)
    grp_keys = df_grp.groups.keys()
    data_list = []
    eval_columns_diff = [a + '_diff' for a in vars['eval_columns']]
    if 'keepEval' in vars:
        eval_columns_diff1 = eval_columns_diff + vars['keepEval']
    else:
        eval_columns_diff1 = eval_columns_diff
    eval_log = {}
    eval_cols_log_scaling = []
    for evalv in eval_columns_diff1:
        eval_log[evalv] = []
    for grp in grp_keys:
        tmp = df_grp.get_group(grp)
        tmp.set_index('Nr', inplace=True)
        row_iterator = tmp.iterrows()
        _, last = next(row_iterator)
        tmp1 = []
        for i, row in row_iterator:
            tmp1.append(row[vars['eval_columns']] - last[vars['eval_columns']])
            tmp1[-1].index = eval_columns_diff
            if 'keepEval' in vars:
                for i1 in vars['keepEval']:
                    tmp1[-1][i1] = row[i1]
            tmp1[-1]['Nr'] = i
            tmp1[-1] = tmp1[-1].append(row[[a for a in grpd_cols if a != 'Nr']])
            last = row
        data_list.append(pd.concat(tmp1, axis=1).T)

        for evalv in eval_columns_diff1:
            eval_log[evalv].append(True if np.abs(np.log10(np.abs(data_list[-1][evalv].min())) -
                                                  np.log10(np.abs(data_list[-1][evalv].max()))) > 1 else False)
    data_new = pd.concat(data_list, ignore_index=True)
    for evalv in eval_columns_diff1:
        if any(eval_log[evalv]):
            eval_cols_log_scaling.append(True)
        else:
            eval_cols_log_scaling.append(False)

    # data_new.columns = [a + '_diff' if a in vars['eval_columns'] else a for a in data_new.columns]
    units = [(a[0] + '_diff', a[1]) for a in vars['units']]
    if 'keepEval' in vars:
        units1 = [a for a in vars['units'] if a[0] in vars['keepEval']]
        units += units1

    from statistics_and_plot import replaceCSVLabels
    ret = {'data': data_new,
           'it_parameters': vars['it_parameters'],
           'eval_columns': eval_columns_diff1,
           'eval_cols_lname': [replaceCSVLabels(a) for a in eval_columns_diff1],
           'eval_cols_log_scaling': eval_cols_log_scaling,
           'units': units,
           'eval_init_input': None,
           'xy_axis_columns': [],
           'partitions': vars['partitions']}
    for key in vars['data_separators']:
        if key not in vars['partitions']:
            ret['xy_axis_columns'].append(key)
    return ret


def get_mean_data_parts(df, nr_parts):
    img_min = df['Nr'].min()
    img_max = df['Nr'].max()
    ir = img_max - img_min
    if ir <= 0:
        return {}, False
    elif ir <= nr_parts:
        nr_parts = ir + 1
    ir_part = round(ir / float(nr_parts) + 1e-6, 0)
    parts = [[img_min + a * ir_part, img_min + (a + 1) * ir_part] for a in range(0, nr_parts)]
    parts[-1][1] = img_max + 1
    if parts[-1][1] - parts[-1][0] <= 0:
        parts.pop()
    data_parts = []
    mean_dd = []
    # print('Limit:', len(inspect.stack()), 'Min:', img_min, 'Max:',
    #       img_max, 'ir_part:', ir_part, 'nr_parts:', nr_parts, 'parts:', parts)
    for sl in parts:
        if sl[1] - sl[0] <= 1:
            tmp = df.set_index('Nr')
            data_parts.append(tmp.loc[[sl[0]],:])
            data_parts[-1].reset_index(inplace=True)
            mean_dd.append(data_parts[-1]['Rt_diff2'].values[0])
        else:
            data_parts.append(df.loc[(df['Nr'] >= sl[0]) & (df['Nr'] < sl[1])])
            # A negative value indicates a decreasing error value and a positive number an increasing error
            # if data_parts[-1].shape[0] < 3:
            #     print('Smaller')
            # elif data_parts[-1].isnull().values.any():
            #     print('nan found')
            mean_dd.append(data_parts[-1]['Rt_diff2'].mean())
    data = {'data_parts': data_parts, 'mean_dd': mean_dd}
    return data, True


def get_converge_img(df, nr_parts, th_diff2=0.33, th_diff3=0.02):
    data, succ = get_mean_data_parts(df, nr_parts)
    if not succ:
        return df, False
    data_parts = data['data_parts']
    # A negative value indicates a decreasing error value and a positive number an increasing error
    mean_dd = data['mean_dd']

    error_gets_smaller = [False] * len(data_parts)
    nr_parts1 = nr_parts
    while not any(error_gets_smaller) and nr_parts1 < 10:
        for i, val in enumerate(mean_dd):
            if val < 0:
                error_gets_smaller[i] = True
        if not any(error_gets_smaller) and nr_parts1 < 10:
            nr_parts1 += 1
            data, succ = get_mean_data_parts(df, nr_parts1)
            if not succ:
                return df, False
            data_parts = data['data_parts']
            mean_dd = data['mean_dd']
            error_gets_smaller = [False] * len(data_parts)
        else:
            break
    if not any(error_gets_smaller):
        df1, succ = get_converge_img(data_parts[0], nr_parts, th_diff2, th_diff3)
        if not succ:
            return df1, False
        else:
            data, succ = get_mean_data_parts(df1, nr_parts)
            if not succ:
                return df1, False
            data_parts = data['data_parts']
            mean_dd = data['mean_dd']
            error_gets_smaller = [False] * len(data_parts)
            for i, val in enumerate(mean_dd):
                if val < 0:
                    error_gets_smaller[i] = True
            if not any(error_gets_smaller):
                return data_parts[0].loc[[data_parts[0]['Nr'].idxmin()], :], False

    l1 = len(mean_dd) - 1
    l2 = l1 - 1
    sel_parts = []
    last = 0
    for i, val in enumerate(mean_dd):
        if not error_gets_smaller[i]:
            last = 0
            continue
        if i < l1:
            if not error_gets_smaller[i + 1]:
                sel_parts.append(i)
                break
            diff1 = (abs(mean_dd[i + 1]) - abs(val)) / abs(val)
            if diff1 > 0:
                last = i + 2
            else:
                last = 0
                if i < l2:
                    if not error_gets_smaller[i + 2]:
                        sel_parts.append(i + 1)
                        break
                    diff2 = (abs(mean_dd[i + 2]) - abs(mean_dd[i + 1])) / abs(mean_dd[i + 1])
                    if abs(diff2) < th_diff3 and mean_dd[i + 1] < th_diff2 * mean_dd[0]:
                        sel_parts.append(i + 1)
                        break
                    else:
                        last = i + 3
                else:
                    sel_parts.append(i + 1)
                    break
        else:
            sel_parts.append(i)
    if sel_parts:
        return get_converge_img(data_parts[sel_parts[0]], nr_parts, th_diff2, th_diff3)
    elif last != 0:
        return get_converge_img(data_parts[min(last, l1)], nr_parts, th_diff2, th_diff3)
    else:
        return get_converge_img(data_parts[0], nr_parts, th_diff2, th_diff3)


def eval_corr_pool_converge(**keywords):
    if 'res_par_name' not in keywords:
        raise ValueError('Missing parameter res_par_name')
    if 'eval_columns' not in keywords:
        raise ValueError('Missing parameter eval_columns')
    if 'partition_x_axis' not in keywords:
        raise ValueError('Missing parameter eval_columns')
    if keywords['partition_x_axis'] not in keywords['partitions']:
        raise ValueError('Partition ' + keywords['partition_x_axis'] + ' not found in partitions')
    needed_evals = ['poolSize', 'poolSize_diff', 'R_diffAll_diff', 't_angDiff_deg_diff', 'R_diffAll', 't_angDiff_deg']
    if not all([a in keywords['eval_columns'] for a in needed_evals]):
        raise ValueError('Some specific entries within parameter eval_columns is missing')

    keywords = prepare_io(**keywords)
    needed_cols = needed_evals + keywords['partitions'] + keywords['xy_axis_columns'] + keywords['it_parameters']
    tmp = keywords['data'].loc[:, needed_cols]

    # comb_vars = ['R_diffAll', 't_angDiff_deg']
    # comb_diff_vars = ['R_diffAll_diff', 't_angDiff_deg_diff']
    # tmp_mm = tmp.loc[:,comb_vars]
    # row = tmp_mm.loc[tmp_mm['Nr'].idxmin()]
    # row['Nr'] -= 1
    # row[comb_vars] -= row[comb_diff_vars]
    # tmp_mm = tmp_mm.append(row)
    # min_vals = tmp_mm.abs().min()
    # max_vals = tmp_mm.abs().max()
    # r_vals = max_vals - min_vals
    # tmp2 = tmp_mm.div(r_vals, axis=1)
    # tmp['Rt_diff_single'] = (tmp2[comb_vars[0]] + tmp2[comb_vars[1]]) / 2

    tmp = combine_rt_diff2(tmp)
    print_evals = ['Rt_diff2'] + [a for a in keywords['eval_columns'] if a != 'poolSize']

    grpd_cols = keywords['partitions'] + \
                [a for a in keywords['xy_axis_columns'] if a != 'Nr'] + \
                keywords['it_parameters']
    df_grp = tmp.groupby(grpd_cols)
    grp_keys = df_grp.groups.keys()
    data_list = []
    # mult = 5
    # while mult > 1:
    #     try:
    #         sys.setrecursionlimit(mult * sys.getrecursionlimit())
    #         break
    #     except:
    #         mult -= 1
    for grp in grp_keys:
        tmp1 = df_grp.get_group(grp)
        tmp2, succ = get_converge_img(tmp1, 3, 0.33, 0.02)
        data_list.append(tmp2)
    data_new = pd.concat(data_list, ignore_index=True)

    df_grp = data_new.groupby(keywords['partitions'])
    grp_keys = df_grp.groups.keys()
    for grp in grp_keys:
        tmp1 = df_grp.get_group(grp)
        tmp1 = tmp1.drop(keywords['partitions'] + ['Nr'])
        tmp1.set_index(keywords['it_parameters'] + [a for a in keywords['xy_axis_columns'] if a != 'Nr'], inplace=True)
        tmp1 = tmp1.unstack(level=-1)
        if len(keywords['it_parameters']) > 1:
            itpars_name = '-'.join(keywords['it_parameters'])
            it_idxs = ['-'.join(a) for a in tmp1.index]
            tmp1.index = it_idxs
        else:
            itpars_name = keywords['it_parameters'][0]
            it_idxs = [a for a in tmp1.index]
        comb_cols = ['-'.join(a) for a in tmp1.columns]
        tmp1.columns = comb_cols

        t_main_name = 'converge_poolSizes_with_inlrat_part' + \
                      '_'.join([keywords['partitions'][i][:min(4, len(keywords['partitions'][i]))] + '-' +
                                a[:min(3, len(a))] for i, a in enumerate(map(str, grp))]) + '_for_opts_' + itpars_name
        t_mean_name = 'data_' + t_main_name + '.csv'
        ft_mean_name = os.path.join(keywords['tdata_folder'], t_mean_name)
        with open(ft_mean_name, 'a') as f:
            f.write('# Correspondence pool sizes for converging differences from frame to '
                    'frame of R & t errors and their inlier ratio '
                    'for data partition ' + '_'.join([keywords['partitions'][i] + '-' +
                                                      a for i, a in enumerate(map(str, grp))]) + '\n')
            f.write('# Different parameters: ' + itpars_name + '\n')
            tmp.to_csv(index=True, sep=';', path_or_buf=f, header=True, na_rep='nan')


    grpd_cols = keywords['partitions'] + keywords['it_parameters']
    df_grp = data_new.groupby(grpd_cols)
    grp_keys = df_grp.groups.keys()
    data_list = []
    for grp in grp_keys:
        tmp1 = df_grp.get_group(grp)
        if tmp1.shape[0] < 4:
            poolsize_med = tmp1['poolSize'].median()
            data_list.append(tmp1.loc[[tmp1['poolSize'] == poolsize_med], :])
        else:
            hist, bin_edges = np.histogram(tmp1['poolSize'].values, bins='auto', density=True)
            idx = np.argmax(hist)
            take_edges = bin_edges[idx:(idx + 2)]
            tmp2 = tmp1.loc[[(tmp1['poolSize'] >= take_edges[0] & tmp1['poolSize'] <= take_edges[1])], :]
            if tmp2.shape[0] > 1:
                poolsize_med = tmp2['poolSize'].median()
                data_list.append(tmp2.loc[[tmp2['poolSize'] == poolsize_med], :])
            else:
                data_list.append(tmp2)
    data_new2 = pd.concat(data_list, ignore_index=True)
    data_new2.drop(keywords['xy_axis_columns'], axis=1, inplace=True)
    dataseps = [a for a in keywords['partitions'] if a != keywords['partition_x_axis']] + keywords['it_parameters']
    l1 = len(dataseps)
    data_new2.set_index([keywords['partition_x_axis']] + dataseps, inplace=True)
    data_new2.unstack(level=-l1)
    comb_cols = ['-'.join(a) for a in data_new2.columns]
    data_new2.columns = comb_cols


    df_grp = tmp.groupby(keywords['partitions'])
    grp_keys = df_grp.groups.keys()
    for grp in grp_keys:
        tmp1 = df_grp.get_group(grp)
        tmp1 = tmp1.drop(keywords['partitions'], axis=1, inplace=True)
        tmp1 = tmp1.groupby(keywords['it_parameters'])
        grp_keys1 = tmp1.groups.keys()
        grp_list = []
        for grp1 in grp_keys1:
            tmp2 = tmp1.get_group(grp1)
            #take mean for same corrPool size
            tmp2 = tmp2.sort_values(by='poolSize')
            row_iterator = tmp2.iterrows()
            i_last, last = next(row_iterator)
            mean_rows = []
            for i, row in row_iterator:
                if last['poolSize'] == row['poolSize']:
                    if mean_rows:
                        if mean_rows[-1][-1] == i_last:
                            mean_rows[-1].append(i)
                        else:
                            mean_rows.append([i_last, i])
                    else:
                        mean_rows.append([i_last, i])
                last = row
                i_last = i
            if mean_rows:
                mean_rows_data = []
                for val in mean_rows:
                    mean_rows_data.append(tmp2.loc[val, :].mean(axis=0))
                    for val1 in keywords['it_parameters']:
                        mean_rows_data[-1][val1] = tmp2.loc[val, val1]
                    for val1 in keywords['xy_axis_columns']:
                        mean_rows_data[-1][val1] = tmp2.loc[val, val1]
                mean_rows1 = []
                for val in mean_rows:
                    mean_rows1 += val
                tmp2.drop(mean_rows1, axis=0, inplace=True)
                tmp3 = pd.concat(mean_rows_data, axis=1).T
                tmp2 = pd.concat([tmp2, tmp3], ignore_index=True)
                tmp2 = tmp2.sort_values(by='poolSize')
            grp_list.append(tmp2)
        tmp1 = pd.concat(grp_list, ignore_index=True)
        if len(keywords['it_parameters']) > 1:
            tmp1 = tmp1.set_index(keywords['it_parameters']).T
            itpars_name = '-'.join(keywords['it_parameters'])
            itpars_cols = ['-'.join(a) for a in tmp1.columns]
            tmp1.columns = itpars_cols
            tmp1.columns.name = itpars_name
            tmp1 = tmp1.T.reset_index()
        else:
            itpars_name = keywords['it_parameters'][0]
            itpars_cols = tmp1[itpars_name].values
        itpars_cols = list(dict.fromkeys(itpars_cols))
        tmp1.set_index(keywords['xy_axis_columns'] + [itpars_name], inplace=True)
        tmp1 = tmp1.unstack(level=-1)
        tmp1.reset_index(inplace=True)
        tmp1.drop(keywords['xy_axis_columns'], axis=1, inplace=True)
        col_names = ['-'.join(a) for a in tmp1.columns]
        tmp1.columns = col_names
        sections = [[b for b in col_names if a in b] for a in print_evals]
        x_axis = [[b for d in itpars_cols if d in c for b in col_names if d in b and 'poolSize' in b] for a in sections
                  for c in a]

        t_main_name = 'double_Rt_diff_vs_poolSize_part' + \
                      '_'.join([keywords['partitions'][i][:min(4, len(keywords['partitions'][i]))] + '-' +
                                a[:min(3, len(a))] for i, a in enumerate(map(str, grp))]) + '_for_opts_' + itpars_name
        t_mean_name = 'data_' + t_main_name + '.csv'
        ft_mean_name = os.path.join(keywords['tdata_folder'], t_mean_name)
        with open(ft_mean_name, 'a') as f:
            f.write('# Differences from frame to frame for R & t errors vs correspondence pool sizes '
                    'for data partition ' + '_'.join([keywords['partitions'][i] + '-' +
                                                      a for i, a in enumerate(map(str, grp))]) + '\n')
            f.write('# Different parameters: ' + itpars_name + '\n')
            tmp.to_csv(index=False, sep=';', path_or_buf=f, header=True, na_rep='nan')


def combine_rt_diff2(df):
    comb_vars = ['R_diffAll', 't_angDiff_deg']
    comb_diff_vars = ['R_diffAll_diff', 't_angDiff_deg_diff']
    tmp_mm = df[comb_diff_vars]
    tmp3 = (df[comb_vars[0]] * tmp_mm[comb_diff_vars[0]] / df[comb_vars[0]].abs() +
            df[comb_vars[1]] * tmp_mm[comb_diff_vars[1]] / df[comb_vars[1]].abs()) / 2
    min_vals = tmp3.min()
    max_vals = tmp3.max()
    r_vals = max_vals - min_vals
    if np.isclose(r_vals, 0, atol=1e-06):
        df['Rt_diff2'] = tmp3
    else:
        df['Rt_diff2'] = tmp3 / r_vals

    return df



