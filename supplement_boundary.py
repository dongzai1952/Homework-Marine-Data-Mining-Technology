"""Post-main boundary supplement. Separate prepare, run and analyze stages."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import math
import os
import platform
import random
import statistics as st
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / '.deps'))
import duckdb

RUN = 'boundary_20261118_01'
OUT = ROOT / 'results' / 'supplement' / RUN
MAIN = ROOT / 'results' / 'formal' / 'formal_20261117_01'
RAW = ROOT / 'data' / 'pilot' / '1000000' / 'random.parquet'
SORTED = ROOT / 'data' / 'formal' / 'formal_20261117_01' / 'time_sorted.parquet'
NS = [20,22,24,26,27,28,29,30,31,32,34,36,40,50]
CLASSES = ['inside', 'cross']

def now():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def save(name, x):
    (OUT/name).write_text(json.dumps(x, ensure_ascii=False, indent=2), encoding='utf-8')

def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))

def quote(p):
    return "'" + Path(p).as_posix().replace("'", "''") + "'"

def connect():
    c = duckdb.connect()
    c.execute('SET threads=1')
    c.execute("SET memory_limit='1GB'")
    c.execute('SET preserve_insertion_order=true')
    for label, p in [('random',RAW), ('sorted',SORTED)]:
        c.execute(f'CREATE VIEW {label}_data AS SELECT * FROM read_parquet({quote(p)})')
    return c

def sql(w, label):
    return (f'SELECT count(*),sum(temperature_centi_c),avg(temperature_centi_c)/100.0 FROM {label}_data '
            f"WHERE event_time >= TIMESTAMP '{w['begin']}' AND event_time < TIMESTAMP '{w['end']}'")

def same(a,b):
    return tuple(a[:2]) == tuple(b[:2]) and math.isclose(a[2],b[2], rel_tol=1e-12,abs_tol=1e-10)

def prepare():
    OUT.mkdir(parents=True, exist_ok=False)
    original = read(MAIN/'preparation.json')
    assert sha(SORTED) == original['sorted_sha256']
    assert sha(RAW) == read(MAIN/'config_frozen.json')['raw_sha256']
    con = connect()
    metadata = {}
    for label,p in [('random',RAW),('sorted',SORTED)]:
        groups = con.execute(f"SELECT row_group_id,row_group_num_rows,stats_min,stats_max FROM parquet_metadata({quote(p)}) WHERE path_in_schema='event_time' ORDER BY row_group_id").fetchall()
        metadata[label] = [{'id':x[0],'rows':x[1],'min':x[2],'max':x[3]} for x in groups]
    assert metadata == original['metadata']
    groups = metadata['sorted']
    windows = []
    for pair,gid in enumerate([1,3,5,7,9,11]):
        g = groups[gid]
        lo,hi = (dt.datetime.fromisoformat(g[k]) for k in ['min','max'])
        center = (lo+(hi-lo)/2).replace(microsecond=0)
        boundary = dt.datetime.fromisoformat(groups[gid+1]['min'])
        for cls,mid in [('inside',center),('cross',boundary)]:
            begin,end = mid-dt.timedelta(hours=12),mid+dt.timedelta(hours=12)
            candidates = {label:[v['id'] for v in gs if dt.datetime.fromisoformat(v['max']) >= begin and dt.datetime.fromisoformat(v['min']) < end] for label,gs in metadata.items()}
            assert candidates['sorted'] == ([gid] if cls == 'inside' else [gid,gid+1])
            assert len(candidates['random']) == 16
            w = {'id':f'{cls}_{pair+1}','pair':pair,'class':cls,'begin':str(begin),'end':str(end),
                 'duration_hours':24,'candidate_group_ids':candidates}
            a,b = con.execute(sql(w,'random')).fetchone(),con.execute(sql(w,'sorted')).fetchone()
            assert same(a,b)
            w['expected'] = list(a)
            w['correctness_checked_without_timing'] = True
            windows.append(w)
    matches = []
    for pair in range(6):
        a,b = [w['expected'][0] for w in windows if w['pair']==pair]
        difference = 100*abs(a-b)/((a+b)/2)
        matches.append({'pair':pair,'inside_rows':a,'cross_rows':b,'relative_count_gap_pct':difference})
        assert difference <= 3, 'Pre-timing count-matching gate failed; do not benchmark or replace windows.'
    rng = random.Random(2026111801)
    singles = []
    for rep in range(9):
        pairs = list(range(6)); rng.shuffle(pairs)
        for pair in pairs:
            order = CLASSES if (rep+pair)%2==0 else CLASSES[::-1]
            for cls in order:
                singles.append({'repeat':rep,'window_id':f'{cls}_{pair+1}',
                                'layout_order':['random','sorted'] if (rep+pair+(cls=='cross'))%2==0 else ['sorted','random']})
    sequences=[]
    for rep in range(5):
        seq=[]
        while len(seq)<max(NS):
            b=list(range(6));rng.shuffle(b);seq.extend(b)
        sequences.append(seq[:max(NS)])
    batches=[]
    for rep in range(5):
        counts=NS.copy();rng.shuffle(counts)
        for n in counts:
            order=CLASSES if (rep+NS.index(n))%2==0 else CLASSES[::-1]
            for cls in order:
                batches.append({'repeat':rep,'n':n,'class':cls,
                                'window_ids':[f'{cls}_{p+1}' for p in sequences[rep][:n]],
                                'layout_order':['random','sorted'] if (rep+NS.index(n)+(cls=='cross'))%2==0 else ['sorted','random']})
    save('windows_frozen.json', {'selected_at':now(),'metadata':metadata,'windows':windows,'count_matching':matches})
    cfg = {
        'created_at':now(),'run_id':RUN,'status':'frozen_before_supplement_timing',
        'provenance':'Supplement proposed after seeing main results. Not an original preregistered main hypothesis.',
        'selection':'Six fixed full row groups 1,3,5,7,9,11 (zero based). Inside: 24 h centered at midpoint of group min/max, rounded down to whole second. Cross: 24 h centered on next group min. No timing used to select.',
        'matching_gate':'Untimed exact hit counts; each pair absolute difference / pair mean <=3%. If fail, stop; no timing-based reselection.',
        'window_file_sha256':sha(OUT/'windows_frozen.json'),'script_sha256':sha(__file__),
        'source_files':{str(p):sha(p) for p in [RAW,SORTED,MAIN/'preparation.json',MAIN/'config_frozen.json',MAIN/'criteria_audit.json']},
        'python':platform.python_version(),'duckdb':duckdb.__version__,'platform':platform.platform(),
        'threads':1,'memory_limit':'1GB','R_s':original['R_median_s'],
        'R_source':'Reuse historical measured median read-sort-write cost from main experiment. No new sorting. Total is historical R plus newly timed batch, not contiguous end-to-end timing.',
        'counts':NS,'single_repeats':9,'batch_repeats':5,'seed':2026111801,
        'single_schedule':singles,'batch_sequences':sequences,'batch_schedule':batches,
        'warmup':'Before each single pair, run that window once on each layout. Before each class batch pair, run its six windows on each layout. Warmups excluded; no cache flush.',
        'timer':'perf_counter_ns around execute/fetchone; singles individually measured, batches actual N executions; results checked after timer.',
        'single_analysis':'For each window median of 9 paired (raw - sorted) savings. Report six window medians and median across them. For matched locations, compare inside saving minus cross saving per repeat, then median of nine; report all six directions and ranges. No significance test or invented practical threshold.',
        'percentage':'100*(raw_batch-(R+sorted_batch))/raw_batch per repeat; summarize median, min/max, positive and >=10% counts.',
        'categories':'p>=10 benefit; -10<p<10 near tie; p<=-10 slower. 10% is the existing practical convention, not statistical significance.',
        'crossing':'Report first sampled N with median >=10 and first with all five >=10; also report sustained versions requiring every larger measured N. Do not interpolate unmeasured counts.',
        'class_comparison':'At each same N and repeat compare the two classes percentages; report median difference and all rounds. Median-based category disagreement is observed judgment change; distinguish all-five support. Threshold equality on this grid does not prove equivalence.',
        'historical_comparison':'Main 1-day first all-five >=10 at N=28 is contextual only. Current inside vs cross is primary; no historical run mixing to estimate current query effects.',
        'correctness':'Same query on both layouts: count and integer sum exact, mean rel_tol=1e-12 abs_tol=1e-10. Every timed result matches its untimed reference. Input hashes unchanged.',
        'stopping':'Run frozen schedule once, keep every round. No result-driven reruns, new counts, or additional factors.',
        'limitations':['Synthetic 1M rows, six pairs, warm cache, same machine and data.', 'Candidate groups from metadata are not measured physical IO.', 'Different date windows and hit counts are close, not identical; no proof of isolated causation.', 'Five repetitions are descriptive ranges, not confidence intervals.', 'Historical fixed R is not remeasured today.']}
    save('config_frozen.json',cfg)
    table='\n'.join(f"| {w['id']} | {w['begin']} | {w['end']} | {w['candidate_group_ids']['sorted']} | {w['expected'][0]} |" for w in windows)
    protocol=f'''# 行组边界补充实验：计时前冻结方案

冻结时间：{cfg['created_at']}。本问题在看到主实验结果后提出，独立保存，不改写主实验。

问题：同样查连续 24 小时，候选行组为 1 或 2，是否改变单次节省时间及累计总耗时至少降低 10% 的判断？

选窗：固定零起算行组 1、3、5、7、9、11；组内窗口以该组时间范围中点为中心；跨组窗口以下一组最小时间为中心；均向两边各取 12 小时。按元数据选，不按速度选。精确命中行数只在计时前核对，每对差异除以均值必须 <=3%，否则停止。没有因速度删除窗口。

|窗口|起点（含）|终点（不含）|排序文件候选行组|命中行数|
|---|---|---|---|---|
{table}

未排序文件所有窗口候选行组均为 16。编号为零起算。元数据候选数不是实测磁盘读块数。

控制：原两个 Parquet 文件及 SHA256 不变、同一查询聚合、单线程、1GB 内存上限、显式预热。成本 R 固定用原实测中位数 {cfg['R_s']} 秒（不重新排序）。因此累计量为历史 R 加本轮整批实测查询时间，不是新的连续端到端计时。

单次：每窗口 9 次成对测量，交替布局/类别顺序；每个窗口取 9 次“未排序减排序”的中位数，再汇总六窗口中位数，并保留每对差值和所有轮次。不额外设置单次差异的显著性门槛。

整批：N={NS}，每类每个 N 5 轮；两类对应相同位置编号序列，各布局使用完全相同窗口序列；每次实际执行 N 条查询，不能以单次均值乘 N 代替。每轮随机排列 N，类别及布局顺序交替。

判断：每轮 p=100×[未排序整批时间−(R+排序整批时间)]/未排序整批时间。p>=10% 达标，-10%<p<10% 接近打平，p<=-10% 更慢。逐轮算 p 后取五轮中位数，并列出范围和 5 轮达标数。分别记录首次中位数达标、首次全部达标，以及在后续已测 N 持续达标的位置。只说已测次数；不插值。相同 N 两类中位数分类不同，记为本轮观察到判断变化，再说明是否五轮都支持；阈值一样不能证明没有差别。

正确性：两布局 count 与整数 sum 完全相同，avg 容差相对 1e-12、绝对 1e-10；所有计时结果在计时结束后核对。预热、核对、连接初始化不计时。输入哈希末尾复核。保存全部轮次；不依据结果挑选或重跑。

局限：模拟数据、预热、小文件、六对窗口、记录数接近但不同；类别间日期不同；元数据不是 IO 计量；五轮范围不是置信区间；R 是历史固定成本。本补充不做新的预测模型或预测误差验证，原 20% 误差检查仍是事后补充复核。
'''
    (OUT/'protocol_frozen.md').write_text(protocol,encoding='utf-8')
    save('freeze_manifest.json',{'at':now(),'files':{f:sha(OUT/f) for f in ['config_frozen.json','windows_frozen.json','protocol_frozen.md']}})
    print(json.dumps({'out':str(OUT),'matched_counts':matches,'counts':NS,'single_pairs':len(singles),'batch_pairs':len(batches),'config_sha256':sha(OUT/'config_frozen.json')},ensure_ascii=False),flush=True)
    con.close()

def run():
    cfg=read(OUT/'config_frozen.json')
    assert sha(__file__)==cfg['script_sha256']
    for f,h in read(OUT/'freeze_manifest.json')['files'].items(): assert sha(OUT/f)==h
    for f,h in cfg['source_files'].items(): assert sha(f)==h
    assert not (OUT/'events.jsonl').exists(), 'Never rerun or overwrite existing timing.'
    log=(OUT/'events.jsonl').open('x',encoding='utf-8')
    def emit(kind,**kw):
        rec={'at':now(),'event':kind,**kw};log.write(json.dumps(rec,ensure_ascii=False)+'\n');log.flush()
    windows={w['id']:w for w in read(OUT/'windows_frozen.json')['windows']}
    con=connect()
    queries={(wid,l):sql(w,l) for wid,w in windows.items() for l in ['random','sorted']}
    emit('timing_started',config_sha256=sha(OUT/'config_frozen.json'),freeze_manifest_sha256=sha(OUT/'freeze_manifest.json'))
    singles=[];batches=[]
    for case in cfg['single_schedule']:
        wid=case['window_id'];w=windows[wid]
        for label in case['layout_order']: con.execute(queries[wid,label]).fetchone()
        values={}
        for label in case['layout_order']:
            t=time.perf_counter_ns();a=con.execute(queries[wid,label]).fetchone();elapsed=(time.perf_counter_ns()-t)/1e9
            assert same(a,w['expected']);values[label]=elapsed
        rec={**case,'class':w['class'],'pair':w['pair'],'random_s':values['random'],'sorted_s':values['sorted'],'saving_s':values['random']-values['sorted'],'correct':True}
        singles.append(rec);emit('single_pair',**rec)
    print('All 108 single-query pairs completed and verified.',flush=True)
    for index,case in enumerate(cfg['batch_schedule']):
        for label in case['layout_order']:
            for wid,w in windows.items():
                if w['class']==case['class']: con.execute(queries[wid,label]).fetchone()
        values={}
        for label in case['layout_order']:
            batch=[queries[wid,label] for wid in case['window_ids']];answers=[]
            t=time.perf_counter_ns()
            for query in batch: answers.append(con.execute(query).fetchone())
            elapsed=(time.perf_counter_ns()-t)/1e9
            for wid,a in zip(case['window_ids'],answers): assert same(a,windows[wid]['expected'])
            values[label]=elapsed
        total=cfg['R_s']+values['sorted']
        rec={**case,'random_batch_s':values['random'],'sorted_batch_s':values['sorted'],'sorted_total_s':total,'saving_pct':100*(values['random']-total)/values['random'],'correct':True}
        batches.append(rec);emit('batch_pair',**rec)
        if (index+1)%10==0: print(f'Completed {index+1}/{len(cfg["batch_schedule"])} batch pairs',flush=True)
    for f,h in cfg['source_files'].items(): assert sha(f)==h
    result={'finished_at':now(),'config_sha256':sha(OUT/'config_frozen.json'),'R_s':cfg['R_s'],'single_samples':singles,'batch_samples':batches,'all_results_match':True,'all_source_hashes_unchanged':True,'actual_timed_query_calls':2*len(singles)+2*sum(x['n'] for x in batches)}
    save('measurements.json',result);emit('completed',actual_timed_query_calls=result['actual_timed_query_calls'])
    log.close();con.close()
    print(json.dumps({k:v for k,v in result.items() if k not in ['single_samples','batch_samples']},ensure_ascii=False),flush=True)

def describe(values):
    return {'median':st.median(values),'min':min(values),'max':max(values),'values':values}

def analyze():
    cfg=read(OUT/'config_frozen.json');m=read(OUT/'measurements.json')
    assert m['config_sha256']==sha(OUT/'config_frozen.json')
    windows=read(OUT/'windows_frozen.json')['windows']
    result={'provenance':cfg['provenance'],'R_s':cfg['R_s'],'single_windows':[], 'single_classes':{},'matched_single_differences':[],'batches':{},'batch_class_differences':[],'all_results_match':m['all_results_match']}
    for w in windows:
        samples=[s for s in m['single_samples'] if s['window_id']==w['id']]
        result['single_windows'].append({'id':w['id'],'class':w['class'],'pair':w['pair'],'rows':w['expected'][0], **{key:describe([s[key]*1000 for s in samples]) for key in ['random_s','sorted_s','saving_s']},'unit':'ms'})
    for cls in CLASSES:
        ws=[w for w in result['single_windows'] if w['class']==cls]
        result['single_classes'][cls]={key:describe([w[key]['median'] for w in ws]) for key in ['random_s','sorted_s','saving_s']}
    for pair in range(6):
        diffs=[]
        for rep in range(9):
            s={v['class']:v for v in m['single_samples'] if v['pair']==pair and v['repeat']==rep}
            diffs.append(1000*(s['inside']['saving_s']-s['cross']['saving_s']))
        result['matched_single_differences'].append({'pair':pair,'inside_minus_cross_saving_ms':describe(diffs),'positive_repeats':sum(v>0 for v in diffs)})
    def category(p): return '>=10%' if p>=10 else 'near_tie' if p>-10 else '<=-10%'
    for cls in CLASSES:
        points=[]
        for n in cfg['counts']:
            samples=[s for s in m['batch_samples'] if s['class']==cls and s['n']==n]
            p=[s['saving_pct'] for s in samples]
            points.append({'n':n,'percentage':describe(p),'random_batch_s':describe([s['random_batch_s'] for s in samples]),'sorted_batch_s':describe([s['sorted_batch_s'] for s in samples]),'sorted_total_s':describe([s['sorted_total_s'] for s in samples]),'positive_repeats':sum(v>0 for v in p),'at_least_10pct_repeats':sum(v>=10 for v in p),'category':category(st.median(p))})
        thresholds={}
        for label,pred in [('median',lambda p:p['percentage']['median']>=10),('all_five',lambda p:p['at_least_10pct_repeats']==5)]:
            thresholds['first_'+label]=next((p['n'] for p in points if pred(p)),None)
            thresholds['sustained_'+label]=next((p['n'] for i,p in enumerate(points) if all(pred(q) for q in points[i:])),None)
        result['batches'][cls]={'points':points,'thresholds_10pct':thresholds}
    for n in cfg['counts']:
        diffs=[]
        for rep in range(5):
            s={v['class']:v for v in m['batch_samples'] if v['n']==n and v['repeat']==rep}
            diffs.append(s['inside']['saving_pct']-s['cross']['saving_pct'])
        points={c:next(p for p in result['batches'][c]['points'] if p['n']==n) for c in CLASSES}
        result['batch_class_differences'].append({'n':n,'inside_minus_cross_percentage_points':describe(diffs),'median_categories_differ':points['inside']['category']!=points['cross']['category']})
    save('summary.json',result)
    os.environ['MPLCONFIGDIR']=str(ROOT/'.cache'/'matplotlib')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    font_manager.fontManager.addfont('C:/Windows/Fonts/msyh.ttc')
    plt.rcParams.update({'font.family':font_manager.FontProperties(fname='C:/Windows/Fonts/msyh.ttc').get_name(),'axes.unicode_minus':False,'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    colors={'inside':'#1976a3','cross':'#d56a2c'};names={'inside':'组内：1 个候选行组','cross':'跨界：2 个候选行组'}
    fig,axes=plt.subplots(1,3,figsize=(17,5.3))
    for cls in CLASSES:
        ws=[w for w in result['single_windows'] if w['class']==cls]
        x=[w['pair']+1 for w in ws];y=[w['sorted_s']['median'] for w in ws]
        axes[0].plot(x,y,'o-',color=colors[cls],label=names[cls])
        axes[0].vlines(x,[w['sorted_s']['min'] for w in ws],[w['sorted_s']['max'] for w in ws],colors=colors[cls],alpha=.35)
        y=[w['saving_s']['median'] for w in ws]
        axes[1].plot(x,y,'o-',color=colors[cls],label=names[cls])
        axes[1].vlines(x,[w['saving_s']['min'] for w in ws],[w['saving_s']['max'] for w in ws],colors=colors[cls],alpha=.35)
        ps=result['batches'][cls]['points'];x=[p['n'] for p in ps];y=[p['percentage']['median'] for p in ps]
        axes[2].plot(x,y,'o-',color=colors[cls],label=names[cls],markersize=4)
        axes[2].fill_between(x,[p['percentage']['min'] for p in ps],[p['percentage']['max'] for p in ps],color=colors[cls],alpha=.14)
    axes[0].set(title='排序文件：单次查询实测耗时',xlabel='元数据选定的窗口对',ylabel='毫秒（点为 9 轮中位数）')
    axes[1].set(title='单次节省 = 未排序 − 排序',xlabel='元数据选定的窗口对',ylabel='毫秒（点为 9 轮成对差值中位数）')
    axes[2].axhspan(-10,10,color='#efcf68',alpha=.12)
    axes[2].axhline(10,color='#555',linestyle='--',label='原定 10% 门槛')
    axes[2].axhline(0,color='#aaa',linewidth=.8)
    axes[2].set(title='实际执行整批后的总耗时降幅',xlabel='每批实际查询次数 N',ylabel='降幅 %（含固定历史排序成本）')
    for ax in axes: ax.grid(alpha=.18);ax.legend(fontsize=8)
    fig.suptitle('主实验后提出的补充：固定 24 小时，仅比较行组边界位置',fontsize=15)
    fig.text(.5,.015,'全部轮次保留；线段/阴影为实测范围，不是置信区间。累计量 = 历史 R 0.5079524 秒 + 本轮整批实测查询时间。',ha='center',fontsize=9)
    fig.tight_layout(rect=[0,.045,1,.94]);fig.savefig(OUT/'boundary_comparison.png',dpi=160);fig.savefig(OUT/'boundary_comparison.svg');plt.close(fig)
    save('artifact_manifest.json',{'created_at':now(),'files':{p.name:sha(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='artifact_manifest.json'},'script_sha256':sha(__file__)})
    print(json.dumps({'single_classes_ms':result['single_classes'],'matched_pair_saving_difference_medians_ms':[v['inside_minus_cross_saving_ms']['median'] for v in result['matched_single_differences']],'thresholds':{c:result['batches'][c]['thresholds_10pct'] for c in CLASSES},'points':{c:[{'n':p['n'],'pct':p['percentage']['median'],'range':[p['percentage']['min'],p['percentage']['max']],'passes':p['at_least_10pct_repeats']} for p in result['batches'][c]['points']] for c in CLASSES}},ensure_ascii=False),flush=True)

if __name__=='__main__':
    {'prepare':prepare,'run':run,'analyze':analyze}[sys.argv[1]]()
