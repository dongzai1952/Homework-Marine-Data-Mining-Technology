"""Build paper-only materials from historical JSON/SVG. Never run database queries.

verify: standard library only; compare current numeric macros, paired table and figure hashes.
generate: write a NEW directory; additionally requires requirements-materials.txt.
"""
from pathlib import Path
import argparse, hashlib, json, math, shutil, statistics as st

PAPER=Path(__file__).resolve().parents[1]
read=lambda p:json.loads(Path(p).read_text(encoding='utf8'))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(condition,message):
    if not condition: raise ValueError(message)

def build_numbers(ROOT):
    main=ROOT/'results/formal/formal_20261117_01'
    supp=ROOT/'results/supplement/boundary_20261118_01'
    m=read(main/'measurements.json');a=read(main/'criteria_audit.json');s=read(supp/'measurements.json');sm=read(supp/'summary.json')
    e=read(ROOT/'results/posthoc/error_metrics_v2/error_comparison.json')
    R=m['R_median_s'];macros={};evidence={}
    def add(name,value,source,fmt=None):
        macros[name]=format(value,fmt) if fmt else str(value)
        evidence[name]={'value':value,'formatted':macros[name],'source':source}
    add('SortCost',R,'main measurements: R_median_s','.7f')
    for days,label in [(1,'One'),(7,'Seven')]:
        points=[]
        for n in sorted({x['n'] for x in m['samples']}):
            rows=[x for x in m['samples'] if x['days']==days and x['n']==n]
            p=[100*(x['random_query_batch_s']-R-x['sorted_query_batch_s'])/x['random_query_batch_s'] for x in rows]
            points.append((n,p))
        allpositive=next(n for i,(n,p) in enumerate(points) if all(all(v>0 for v in q) for _,q in points[i:]))
        anypositive=next(n for n,p in points if any(v>0 for v in p))
        allten=next(n for n,p in points if all(v>=10 for v in p))
        require(allpositive==a['windows'][str(days)]['first_sustained_all_five_positive_n'], 'Main net threshold mismatch')
        require(allten==a['windows'][str(days)]['first_all_five_10pct_n'], 'Main 10% threshold mismatch')
        add('Main'+label+'NetN',allpositive,'raw main batches: all five positive and sustained')
        add('Main'+label+'AnyN',anypositive,'raw main batches: any positive')
        add('Main'+label+'TenN',allten,'raw main batches: all five >=10%')
        atnet=[x for x in m['samples'] if x['days']==days and x['n']==allpositive]
        add('Main'+label+'NetPct',st.median(100*(x['random_query_batch_s']-x['sorted_total_s'])/x['random_query_batch_s'] for x in atnet),'raw paired percentage at net N','.2f')
        add('Main'+label+'SavingMs',1000*st.median(x['paired_saving_s'] for x in atnet),'raw paired saving at net N','.2f')
        for n,tag in [(1,'Single'),(100,'Hundred'),(28,'TwentyEight')]:
            rows=[x for x in m['samples'] if x['days']==days and x['n']==n]
            for k,suffix in [('random_query_batch_s','Raw'),('sorted_query_batch_s','Query'),('sorted_total_s','Total')]:
                add('Main'+label+tag+suffix,st.median(x[k] for x in rows),'main raw median: '+k+' days='+str(days)+' N='+str(n),'.6f')
    for cls,label in [('inside','Inside'),('cross','Cross')]:
        pts=[]
        for n in sorted({x['n'] for x in s['batch_samples']}):
            rows=[x for x in s['batch_samples'] if x['class']==cls and x['n']==n]
            pp=[100*(x['random_batch_s']-(R+x['sorted_batch_s']))/x['random_batch_s'] for x in rows]
            pts.append((n,pp))
            if n in [24,26,27,28]:
                # Names are letters only for TeX control sequences.
                num={24:'TwentyFour',26:'TwentySix',27:'TwentySeven',28:'TwentyEight'}[n]
                add('Supp'+label+num+'Pct',st.median(pp),'supp raw paired percentage N='+str(n),'.2f')
                add('Supp'+label+num+'Pass',sum(x>=10 for x in pp),'supp raw passes N='+str(n))
        medn=next(n for n,p in pts if st.median(p)>=10);alln=next(n for n,p in pts if all(v>=10 for v in p))
        require(alln==sm['batches'][cls]['thresholds_10pct']['first_all_five'], 'Supplement threshold mismatch')
        add('Supp'+label+'MedianN',medn,'supp raw first median>=10%')
        add('Supp'+label+'AllN',alln,'supp raw first all five>=10%')
        for key,suffix in [('sorted_s','QueryMs'),('saving_s','SavingMs')]:
            add('Supp'+label+suffix,sm['single_classes'][cls][key]['median'],'supp summary: median of six window medians (unit ms)','.2f')
        rows=[x for x in s['batch_samples'] if x['class']==cls and x['n']==28]
        for key,suffix in [('random_batch_s','Raw'),('sorted_batch_s','Query')]:
            add('Supp'+label+'TwentyEight'+suffix,st.median(x[key] for x in rows),'supp raw batch N=28 '+key,'.6f')
    for idx,c in enumerate(e['combinations']):
        tag=['PilotOneDayOne','PilotOneDaySeven','PilotTwoDayOne','PilotTwoDaySeven'][idx]
        for key,suffix,metric in [('max_total_error','Total','total_abs_error_pct'),('max_query_error','Query','query_abs_error_pct')]:
            add(tag+suffix+'Max',c[key][metric],'posthoc errors '+c['pilot']+' '+str(c['days'])+' days','.2f')
            add(tag+suffix+'MaxN',c[key]['n'],'posthoc argmax '+key)
        for n,nlabel in [(1,'Single'),(100,'Hundred')]:
            v=next(p for p in c['points'] if p['n']==n)
            for key,suffix in [('R_share_pct','Share'),('total_abs_error_pct','TotalErr'),('query_abs_error_pct','QueryErr')]:
                add(tag+nlabel+suffix,v[key],'posthoc point N='+str(n),'.2f')
    return macros,evidence

def paired_table(root):
    folder=root/'results/supplement/boundary_20261118_01'
    raw=read(folder/'measurements.json');summary=read(folder/'summary.json')
    rows=[]
    for pair in range(6):
        differences=[]
        for rep in range(9):
            samples={x['class']:x for x in raw['single_samples'] if x['pair']==pair and x['repeat']==rep}
            require(set(samples)=={'inside','cross'},'Missing pair')
            differences.append(1000*((samples['inside']['random_s']-samples['inside']['sorted_s'])-(samples['cross']['random_s']-samples['cross']['sorted_s'])))
        med=st.median(differences);positive=sum(v>0 for v in differences)
        saved=summary['matched_single_differences'][pair]
        require(math.isclose(med,saved['inside_minus_cross_saving_ms']['median'],abs_tol=1e-10),'Paired median differs from history')
        require(positive==saved['positive_repeats'],'Paired rounds differ from history')
        rows.append({'pair':pair+1,'median_ms':med,'positive_rounds':positive,'all_differences_ms':differences})
    lines=[r'\begin{table}[htbp]',r'\centering\small',r'\caption{六对窗口的同轮查询阶段节省差值}\label{tab:paired-saving}',r'\begin{tabular}{@{}crcc@{}}',r'\toprule',r'窗口对 & 差值中位数（毫秒） & 差值为正的轮数 & 总轮数\\',r'\midrule']
    lines += [f"{x['pair']} & {x['median_ms']:.4f} & {x['positive_rounds']} & 9\\\\" for x in rows]
    lines += [r'\bottomrule',r'\end{tabular}',r'\tabnote{每轮差值为 $(U_{\text{组内}}-S_{\text{组内}})-(U_{\text{跨界}}-S_{\text{跨界}})$，先逐轮配对再取九轮中位数；单位为毫秒，未扣除重排成本。正值表示该轮组内窗口的查询阶段节省更多。}',r'\end{table}']
    return '\n'.join(lines)+'\n',rows

def validate_errors(root):
    folder=root/'results/formal/formal_20261117_01'
    cfg=read(folder/'config_frozen.json');m=read(folder/'measurements.json')
    e=read(root/'results/posthoc/error_metrics_v2/error_comparison.json');checked=0
    for c in e['combinations']:
        source=next(v for v in cfg['pilot_sources'] if v['name']==c['pilot'])['summary'][str(c['days'])]
        for point in c['points']:
            q=st.median(x['sorted_query_batch_s'] for x in m['samples'] if x['days']==c['days'] and x['n']==point['n'])
            t=m['R_median_s']+q;predq=point['n']*source['sorted']['median_s'];predt=source['pilot_reorder_median_s']+predq
            require(math.isclose(point['query_abs_error_pct'],100*abs(predq-q)/q,abs_tol=1e-10),'Query error mismatch')
            require(math.isclose(point['total_abs_error_pct'],100*abs(predt-t)/t,abs_tol=1e-10),'Total error mismatch')
            checked+=1
    require(checked==76,'Expected all 76 error points')

SOURCES={'main':'results/formal/formal_20261117_01/cumulative_time.svg','supplement':'results/supplement/boundary_20261118_01/boundary_comparison.svg'}
CROPS={'main_day1.pdf':('main',[20,90,505,358]),'main_day7.pdf':('main',[508,90,1000,358]),'supp_single.pdf':('supplement',[0,50,405,356]),'supp_batch.pdf':('supplement',[810,50,1224,356])}
INPUTS=['results/formal/formal_20261117_01/measurements.json','results/formal/formal_20261117_01/criteria_audit.json','results/formal/formal_20261117_01/config_frozen.json','results/supplement/boundary_20261118_01/measurements.json','results/supplement/boundary_20261118_01/summary.json','results/posthoc/error_metrics_v2/error_comparison.json',*SOURCES.values()]

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command',choices=['verify','generate'])
    ap.add_argument('--project-root',type=Path,default=PAPER.parent)
    ap.add_argument('--out',type=Path)
    args=ap.parse_args();root=args.project_root.resolve()
    validate_errors(root);macros,evidence=build_numbers(root);table,pairs=paired_table(root)
    macro_text='% Generated from existing JSON only; values are not measurements from this authoring task.\n'+''.join('\\newcommand{\\'+k+'}{'+v+'}\n' for k,v in macros.items())
    if args.command=='verify':
        require(args.out is None,'verify is read-only; do not pass --out')
        require((PAPER/'data_macros.tex').read_text(encoding='utf8')==macro_text,'Numeric macro mismatch')
        require(read(PAPER/'audit/numeric_sources.json')==evidence,'Numeric ledger mismatch')
        require((PAPER/'generated/paired_savings.tex').read_text(encoding='utf8')==table,'Paired table mismatch')
        conversion=read(PAPER/'audit/material_generation.json')
        for rel,h in conversion['input_sha256'].items():require(sha(root/rel)==h,'Historical input changed: '+rel)
        for rel,h in conversion['figure_sha256'].items():require(sha(PAPER/rel)==h,'Paper figure changed: '+rel)
        for name,rel in SOURCES.items():require(sha(PAPER/'figures/source'/f'{name}.svg')==sha(root/rel),'Original SVG mismatch')
        print(json.dumps({'ok':True,'macros':len(macros),'paired_windows':len(pairs),'error_points':76,'new_timing':False}))
        return
    require(args.out is not None,'generate requires --out to a NEW directory')
    out=args.out.resolve();require(not out.exists(),'Never overwrite existing output')
    require(not out.is_relative_to(root/'results'),'Do not generate inside historical results')
    require(not out.is_relative_to(PAPER),'Do not generate inside current paper')
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPDF
    from pypdf import PdfReader,PdfWriter
    import importlib.metadata as md
    out.mkdir(parents=True);(out/'audit').mkdir();(out/'generated').mkdir();(out/'figures/source').mkdir(parents=True)
    (out/'data_macros.tex').write_text(macro_text,encoding='utf8')
    (out/'generated/paired_savings.tex').write_text(table,encoding='utf8')
    for name,obj in [('numeric_sources.json',evidence),('paired_savings.json',pairs)]:
        (out/'audit'/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf8')
    for name,rel in SOURCES.items():
        source=out/'figures/source'/f'{name}.svg';shutil.copy2(root/rel,source)
        renderPDF.drawToFile(svg2rlg(str(source)),str(source.with_suffix('.pdf')))
    for filename,(name,rect) in CROPS.items():
        page=PdfReader(out/'figures/source'/f'{name}.pdf').pages[0]
        height=float(page.mediabox.height);x0,y0,x1,y1=rect
        page.cropbox.lower_left=(x0,height-y1);page.cropbox.upper_right=(x1,height-y0);page.mediabox=page.cropbox
        writer=PdfWriter();writer.add_page(page)
        with (out/'figures'/filename).open('wb') as f:writer.write(f)
    record={'new_timing':False,'script_sha256':sha(__file__),'input_sha256':{p:sha(root/p) for p in INPUTS},'numeric_macros':len(macros),'paired_windows':6,'posthoc_error_points':76,'crops_top_origin_pt':CROPS,'versions':{n:md.version(n) for n in ['svglib','reportlab','pypdf']},'figure_sha256':{p.relative_to(out).as_posix():sha(p) for p in (out/'figures').rglob('*') if p.is_file()},'note':'Existing SVG paths only; no data or axes altered. PDF byte hashes may change with library versions/metadata; inspect rendered output.'}
    (out/'audit/material_generation.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'output':str(out),'macros':len(macros),'paired_windows':6,'new_timing':False},ensure_ascii=True))

if __name__=='__main__':main()
