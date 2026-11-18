"""Read-only analysis of frozen measurements; makes charts, not a written report."""
from pathlib import Path
import argparse
import json
import math
import os
import statistics as st
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.deps'))
os.environ['MPLCONFIGDIR'] = str(ROOT/'.cache'/'matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--run-id',default='formal_20261117_01')
    args=ap.parse_args()
    folder=ROOT/'results'/'formal'/args.run_id
    raw=json.loads((folder/'measurements.json').read_text(encoding='utf-8'))
    config=json.loads((folder/'config_frozen.json').read_text(encoding='utf-8'))
    prep=json.loads((folder/'preparation.json').read_text(encoding='utf-8'))
    ns=config['counts']; R=raw['R_median_s']
    assert len(raw['samples'])==len(ns)*2*config['repeats']
    assert raw['actual_measured_query_calls']==sum(ns)*config['repeats']*4
    for sample in raw['samples']:
        assert sample['offset_sequence']==config['sequences'][sample['repeat']][:sample['n']]
        assert math.isclose(sample['sorted_total_s'],R+sample['sorted_query_batch_s'])
    windows={}
    def crossing(rows, key):
        for i,row in enumerate(rows):
            if row[key] and all(x[key] for x in rows[i:]):
                return {'first_sampled_n':row['n'],'preceding_sampled_n':rows[i-1]['n'] if i else 0}
        return None
    for w in [1,7]:
        points=[]
        for n in ns:
            records=[x for x in raw['samples'] if x['days']==w and x['n']==n]
            assert sorted(x['repeat'] for x in records)==list(range(config['repeats']))
            a=[x['random_query_batch_s'] for x in records]
            b=[x['sorted_total_s'] for x in records]
            q=[x['sorted_query_batch_s'] for x in records]
            delta=[x['paired_saving_s'] for x in records]
            p={'n':n,'random_median_s':st.median(a),'random_min_s':min(a),'random_max_s':max(a),
               'sorted_total_median_s':st.median(b),'sorted_total_min_s':min(b),'sorted_total_max_s':max(b),
               'sorted_query_median_s':st.median(q),'paired_saving_median_s':st.median(delta),
               'paired_saving_min_s':min(delta),'paired_saving_max_s':max(delta),
               'sorted_wins':sum(x>0 for x in delta),'repeats':len(records),
               'median_positive':st.median(delta)>0,'all_positive':all(x>0 for x in delta),
               'median_curves_sorted_lower':st.median(b)<st.median(a)}
            points.append(p)
        sensitivity=[]
        for r in raw['reorder_s']:
            rows=[]
            for n in ns:
                ds=[x['random_query_batch_s']-r-x['sorted_query_batch_s'] for x in raw['samples'] if x['days']==w and x['n']==n]
                rows.append({'n':n,'positive':st.median(ds)>0})
            sensitivity.append({'R_s':r,'crossing':crossing(rows,'positive')})
        windows[str(w)]={'points':points,'median_paired_crossing':crossing(points,'median_positive'),
                         'median_curves_crossing':crossing(points,'median_curves_sorted_lower'),
                         'all_five_crossing':crossing(points,'all_positive'),
                         'R_sensitivity':sensitivity}
    summary={'run_id':args.run_id,'R_median_s':R,'reorder_s':raw['reorder_s'],
             'frozen_pilot_estimates':config['frozen_pilot_estimates'],'windows':windows,
             'verification':{'all_results_match':raw['all_results_match'],'input_unchanged':raw['input_unchanged'],
                             'pairs':raw['pairs'],'actual_measured_query_calls':raw['actual_measured_query_calls']},
             'warning':'Crossings are empirical sampled brackets; curves connect measured points. R+batch is a cost sum, not one continuous timer. Shading is repeat min/max, not a confidence interval.'}
    (folder/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    font=Path('C:/Windows/Fonts/msyh.ttc')
    if font.exists():
        font_manager.fontManager.addfont(str(font))
        plt.rcParams['font.family']=font_manager.FontProperties(fname=str(font)).get_name()
    plt.rcParams.update({'axes.unicode_minus':False,'font.size':11,'axes.spines.top':False,
                         'axes.spines.right':False,'figure.facecolor':'white','savefig.facecolor':'white'})
    fig,axes=plt.subplots(2,2,figsize=(14,9.5))
    blue='#236A9F'; orange='#C55C24'
    for col,w in enumerate([1,7]):
        pts=windows[str(w)]['points']
        x=np.array([0]+ns)
        a=np.array([0]+[p['random_median_s'] for p in pts])
        b=np.array([R]+[p['sorted_total_median_s'] for p in pts])
        for row in [0,1]:
            ax=axes[row,col]
            ax.plot(x,a,'o-',color=blue,ms=3,lw=1.6,label='不排序：整批查询实测')
            ax.plot(x,b,'s-',color=orange,ms=3,lw=1.6,label='排序：一次重排 + 整批查询实测')
            ax.fill_between(x,[0]+[p['random_min_s'] for p in pts],[0]+[p['random_max_s'] for p in pts],color=blue,alpha=.12)
            ax.fill_between(x,[R]+[p['sorted_total_min_s'] for p in pts],[R]+[p['sorted_total_max_s'] for p in pts],color=orange,alpha=.12)
            pred=config['frozen_pilot_estimates'][str(w)]
            if pred[0]==pred[1]:
                ax.axvline(pred[0],color='#666666',ls=':',lw=1.4,label=f'预试验估计：{pred[0]} 次')
            else:
                ax.axvspan(pred[0],pred[1],color='#888888',alpha=.2,label=f'预试验估计：{pred[0]}–{pred[1]} 次')
            ax.set_xlabel('连续执行的查询次数 N')
            ax.set_ylabel('累计时间（秒，含一次重排成本）')
            ax.grid(alpha=.18)
            if row==0:
                ax.set_xlim(0,102)
                ax.set_ylim(bottom=0)
                ax.set_title(f'每次查询 {w} 天：全部测量次数',fontsize=14,loc='left',pad=12)
                ax.legend(fontsize=9,loc='upper left')
            else:
                ax.set_xlim(19,41)
                values=[p[k] for p in pts if 20<=p['n']<=40 for k in ['random_min_s','random_max_s','sorted_total_min_s','sorted_total_max_s']]
                lo,hi=min(values),max(values)
                ax.set_ylim(max(0,lo-(hi-lo)*.1),hi+(hi-lo)*.12)
                ax.set_xticks([20,24,28,32,36,40])
                cross=windows[str(w)]['median_paired_crossing']
                label=f"配对中位数回本区间：({cross['preceding_sampled_n']}, {cross['first_sampled_n']}] 次" if cross else '测量范围内未发现持续回本'
                ax.set_title(f'交点附近放大  ·  {label}',fontsize=12,loc='left',pad=10)
    fig.suptitle('Parquet 排序回本验证：累计查询逐批实测',fontsize=20,x=.075,ha='left',y=.99)
    fig.text(.075,.943,f'100 万行 · 1 线程 · 预热后查询 · 每点 5 轮 · 本轮一次重排 R = {R:.3f} 秒',fontsize=11,color='#444444')
    fig.text(.075,.025,'点为 5 轮中位数，阴影为最小–最大范围；连线仅连接实测点。排序总时间为实测 R 与整批查询时间之和。',fontsize=10,color='#555555')
    fig.tight_layout(rect=[.025,.055,.99,.925],h_pad=2.4,w_pad=2.4)
    fig.savefig(folder/'cumulative_time.png',dpi=180)
    fig.savefig(folder/'cumulative_time.svg')
    plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(13,4.8))
    for ax,w in zip(axes,[1,7]):
        ps=windows[str(w)]['points']
        xs=[p['n'] for p in ps]
        mids=[p['paired_saving_median_s'] for p in ps]
        ax.plot(xs,mids,'o-',color='#237653',ms=4)
        ax.fill_between(xs,[p['paired_saving_min_s'] for p in ps],[p['paired_saving_max_s'] for p in ps],color='#237653',alpha=.15)
        ax.axhline(0,color='#555555',lw=1)
        pred=config['frozen_pilot_estimates'][str(w)]
        ax.axvline(pred[0],ls=':',color='#888888')
        if pred[1]!=pred[0]: ax.axvline(pred[1],ls=':',color='#888888')
        ax.set_xlim(19,41)
        local=[p[k] for p in ps if 20<=p['n']<=40 for k in ['paired_saving_min_s','paired_saving_max_s']]
        spread=max(local)-min(local)
        ax.set_ylim(min(local)-.1*spread,max(local)+.1*spread)
        ax.set_title(f'每次查询 {w} 天',loc='left')
        ax.set_xlabel('连续查询次数 N'); ax.set_ylabel('净节省时间（秒）')
        ax.grid(alpha=.18)
    fig.suptitle('回本附近：正值表示排序方案总时间更少',fontsize=17,x=.08,ha='left')
    fig.text(.08,.025,'净节省 = 不排序整批耗时 − 重排成本 R − 排序后整批耗时；点为配对差值中位数，阴影为 5 轮范围。',fontsize=9)
    fig.tight_layout(rect=[.02,.07,.99,.92])
    fig.savefig(folder/'net_saving_zoom.png',dpi=180)
    plt.close(fig)
    brief={'R_median_s':R,'reorder_s':raw['reorder_s'],'verification':summary['verification']}
    for w in ['1','7']:
        brief[w]={k:windows[w][k] for k in ['median_paired_crossing','median_curves_crossing','all_five_crossing','R_sensitivity']}
        brief[w]['selected_points']=[p for p in windows[w]['points'] if p['n'] in [20,22,23,24,25,26,28,29,30,31,32,33,34,36,40,100]]
    print(json.dumps(brief,ensure_ascii=False),flush=True)

if __name__=='__main__':
    main()
