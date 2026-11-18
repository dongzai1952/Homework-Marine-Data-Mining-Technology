"""Audit existing JSON only. Does not connect to DuckDB or execute any query."""
from pathlib import Path
import hashlib
import json
import os
import statistics as st
import sys

ROOT = Path(__file__).resolve().parent
FOLDER = ROOT / 'results' / 'formal' / 'formal_20261117_01'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    original = json.loads((FOLDER/'artifact_manifest.json').read_text(encoding='utf-8'))
    protected = {ROOT/x['path']:x['sha256'] for x in original['files']}
    for path,digest in protected.items():
        assert sha(path)==digest, f'Historical artifact changed: {path}'
    raw=json.loads((FOLDER/'measurements.json').read_text(encoding='utf-8'))
    config=json.loads((FOLDER/'config_frozen.json').read_text(encoding='utf-8'))
    assert raw['config_sha256']==sha(FOLDER/'config_frozen.json')
    ns=config['counts']
    audit={'purpose':'Restore the previously discussed 10% practical-benefit rule and disclose status of 20% forecast-error checking.',
           'benchmark_rerun':False,'original_artifacts_unchanged':True,
           'R_s':raw['R_median_s'],
           'percentage_formula':'100 * (T_random_batch - (R + T_sorted_query_batch)) / T_random_batch',
           'aggregation':'Compute percentage per paired repeat, then take median of five. Also retain min/max and counts.',
           'categories':'p >= 10: sorted at least 10% faster; -10 < p < 10: near tie; p <= -10: sorted at least 10% slower.',
           'important':'Positive net saving and at least 10% saving are different thresholds. Earlier summary omitted the near-tie label.',
           'windows':{},
           'forecast_review':{
               'checked_in_previous_analysis':False,
               'per_N_prediction_table_saved_before_formal':False,
               'single_primary_pilot_selection_frozen':False,
               'historical_prediction_inputs_available':True,
               'status':'Supplementary retrospective audit using only pre-formal frozen predictor inputs; not a completed preregistered single-forecast validation.',
               'formula':'predicted_sorted_total(N) = pilot_reorder_median_s + N * pilot_sorted_query_median_s',
               'error_formula':'100 * abs(predicted_total - observed_total) / observed_total',
               'evaluation':'Both pilot sources evaluated separately, all measured N retained; medians and all-repeat maximum errors reported. No fitted coefficients or selection by formal results.',
               'sources':[]}}
    for w in [1,7]:
        points=[]
        for n in ns:
            records=[x for x in raw['samples'] if x['days']==w and x['n']==n]
            percentages=[100*(x['random_query_batch_s']-x['sorted_total_s'])/x['random_query_batch_s'] for x in records]
            med=st.median(percentages)
            points.append({'n':n,'median_pct':med,'min_pct':min(percentages),'max_pct':max(percentages),
                           'positive_repeats':sum(x>0 for x in percentages),'at_least_10pct_repeats':sum(x>=10 for x in percentages),
                           'paired_percentages':percentages,
                           'category':'at_least_10pct_faster' if med>=10 else 'near_tie' if med>-10 else 'at_least_10pct_slower'})
        def first(pred):
            return next((p['n'] for p in points if pred(p)),None)
        def sustained(pred):
            return next((p['n'] for i,p in enumerate(points) if all(pred(v) for v in points[i:])),None)
        audit['windows'][str(w)]={'points':points,
            'first_any_repeat_positive_n':first(lambda p:p['positive_repeats']>0),
            'first_sustained_median_positive_n':sustained(lambda p:p['median_pct']>0),
            'first_sustained_all_five_positive_n':sustained(lambda p:p['positive_repeats']==5),
            'first_median_10pct_n':first(lambda p:p['median_pct']>=10),
            'first_all_five_10pct_n':first(lambda p:p['at_least_10pct_repeats']==5)}
    for source in config['pilot_sources']:
        source_path=ROOT/'results'/'pilot'/source['name']
        assert sha(source_path)==source['sha256']
        result={'source':source['name'],'source_sha256':source['sha256'],'windows':{}}
        for w in [1,7]:
            s=source['summary'][str(w)]
            r=s['pilot_reorder_median_s']; t=s['sorted']['median_s']
            values=[]
            for n in ns:
                predicted=r+n*t  # Neither input comes from formal measurements.
                actuals=[x['sorted_total_s'] for x in raw['samples'] if x['days']==w and x['n']==n]
                actual_med=st.median(actuals)
                values.append({'n':n,'predicted_s':predicted,'observed_median_s':actual_med,
                               'median_total_error_pct':100*abs(predicted-actual_med)/actual_med,
                               'repeat_errors_pct':[100*abs(predicted-a)/a for a in actuals]})
            worst=max(values,key=lambda x:x['median_total_error_pct'])
            max_all=max(e for x in values for e in x['repeat_errors_pct'])
            result['windows'][str(w)]={'historical_R_s':r,'historical_t_sorted_s':t,
                'max_error_against_median_pct':worst['median_total_error_pct'],
                'worst_n':worst['n'],'max_error_any_repeat_pct':max_all,
                'all_median_errors_within_20pct':all(v['median_total_error_pct']<=20 for v in values),
                'all_repeat_errors_within_20pct':max_all<=20,'values':values}
        audit['forecast_review']['sources'].append(result)
    (FOLDER/'criteria_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')

    sys.path.insert(0,str(ROOT/'.deps'))
    os.environ['MPLCONFIGDIR']=str(ROOT/'.cache'/'matplotlib')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    font=Path('C:/Windows/Fonts/msyh.ttc')
    font_manager.fontManager.addfont(str(font))
    plt.rcParams.update({'font.family':font_manager.FontProperties(fname=str(font)).get_name(),
                         'axes.unicode_minus':False,'font.size':11,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,2,figsize=(13,5.4))
    for ax,w in zip(axes,[1,7]):
        points=[p for p in audit['windows'][str(w)]['points'] if 20<=p['n']<=40]
        x=[p['n'] for p in points]; y=[p['median_pct'] for p in points]
        lo=min(p['min_pct'] for p in points)-3; hi=max(p['max_pct'] for p in points)+3
        ax.axhspan(-10,10,color='#F3DFB3',alpha=.5,label='接近打平：降幅介于 −10% 与 10%')
        ax.axhline(0,color='#555555',ls=':',lw=1.2,label='0%：刚抵消重排成本')
        ax.axhline(10,color='#236A9F',ls='--',lw=1.4,label='10%：达到约定收益门槛')
        ax.plot(x,y,'o-',color='#237653',lw=1.8,ms=4,label='5 轮配对降幅中位数')
        ax.fill_between(x,[p['min_pct'] for p in points],[p['max_pct'] for p in points],color='#237653',alpha=.15)
        for n in [audit['windows'][str(w)]['first_sustained_median_positive_n'],audit['windows'][str(w)]['first_median_10pct_n']]:
            p=next(p for p in points if p['n']==n)
            ax.annotate(f"{n} 次：{p['median_pct']:.2f}%",(n,p['median_pct']),xytext=(-12,20),textcoords='offset points',fontsize=10,
                        arrowprops={'arrowstyle':'-','color':'#555555'})
        ax.set_xlim(19,41); ax.set_ylim(lo,hi)
        ax.set_xticks([20,24,28,32,36,40])
        ax.set_xlabel('连续查询次数 N'); ax.set_ylabel('排序方案总耗时降低比例（%）')
        ax.set_title(f'每次查询 {w} 天',loc='left',fontsize=14)
        ax.grid(alpha=.15)
    handles,labels=axes[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='upper center',bbox_to_anchor=(.52,.91),ncol=2,fontsize=9,frameon=False)
    fig.suptitle('恢复原先的 10% 门槛：刚回本仍可能接近打平',fontsize=18,x=.08,ha='left',y=.99)
    fig.text(.08,.025,'百分比以不排序总时间为分母，逐轮配对计算后取中位数；阴影为 5 轮范围。仅复核既有数据，未重跑。',fontsize=9,color='#555555')
    fig.tight_layout(rect=[.015,.065,.99,.81])
    fig.savefig(FOLDER/'criteria_audit.png',dpi=180)
    plt.close(fig)
    for path,digest in protected.items():
        assert sha(path)==digest, f'Historical artifact changed after audit: {path}'
    print(json.dumps({'original_artifacts_verified':len(protected),
        'thresholds':{w:{k:v for k,v in d.items() if k!='points'} for w,d in audit['windows'].items()},
        'prediction_max_error_against_median_pct':{s['source']:{w:v['max_error_against_median_pct'] for w,v in s['windows'].items()} for s in audit['forecast_review']['sources']}},ensure_ascii=False))

if __name__=='__main__':
    main()
