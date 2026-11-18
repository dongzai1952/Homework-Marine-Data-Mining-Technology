"""Versioned, non-destructive entry points. Historical benchmark scripts stay byte-identical.

History verification and error analysis use only the Python standard library.
Only run-main / run-pilot / run-supplement execute performance measurements.
"""
from pathlib import Path
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import math
import re
import shutil
import statistics as st
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MAIN_ID = 'formal_20261117_01'
SUPP_ID = 'boundary_20261118_01'
MAIN = Path('results/formal') / MAIN_ID
SUPP = Path('results/supplement') / SUPP_ID

def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def save(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def require(ok, message):
    if not ok:
        raise ValueError(message)

def local(rel):
    p = (ROOT / str(rel).replace('\\', '/')).resolve()
    require(p.is_relative_to(ROOT.resolve()), 'Path escapes repository: ' + str(rel))
    return p

def verify_history():
    checked = {}
    def check(p, expected):
        p = p.resolve()
        require(p.is_relative_to(ROOT.resolve()), 'Refuse historical absolute path')
        require(sha(p) == expected, 'SHA256 mismatch: ' + str(p))
        checked[p.relative_to(ROOT).as_posix()] = expected
    for entry in read(ROOT/MAIN/'artifact_manifest.json')['files']:
        check(local(entry['path']), entry['sha256'])
    for name in ['artifact_manifest.json', 'freeze_manifest.json']:
        for rel, digest in read(ROOT/SUPP/name)['files'].items():
            check(local(SUPP/rel), digest)
    cfg = read(ROOT/MAIN/'config_frozen.json')
    raw = read(ROOT/MAIN/'measurements.json')
    check(ROOT/'formal_experiment.py', cfg['script_sha256'])
    check(ROOT/MAIN/'config_frozen.json', raw['config_sha256'])
    for source in cfg['pilot_sources']:
        p = ROOT/'results/pilot'/source['name']
        check(p, source['sha256'])
        require(read(p)['summary'] == source['summary'], 'Pilot summary mismatch')
        check(ROOT/'archive/pilot_parquet_original.py', read(p)['script_sha256'])
    sc = read(ROOT/SUPP/'config_frozen.json')
    check(ROOT/'supplement_boundary.py', sc['script_sha256'])
    # Old absolute source paths are evidence only. Explicitly map known suffixes locally.
    optional_data = []
    for original, digest in sc['source_files'].items():
        parts = original.replace('\\', '/').split('/')
        starts = [i for i, v in enumerate(parts) if v in ('data', 'results')]
        require(len(starts) == 1, 'Unrecognized historical source: ' + original)
        rel = '/'.join(parts[starts[0]:])
        p = local(rel)
        if rel.startswith('data/') and not p.exists():
            optional_data.append({'path': rel, 'status': 'absent; history review does not require raw data'})
        else:
            check(p, digest)
    require(len(raw['samples']) == len(cfg['counts'])*2*cfg['repeats'], 'Missing main samples')
    audit = read(ROOT/MAIN/'criteria_audit.json')
    for days in [1, 7]:
        for point in audit['windows'][str(days)]['points']:
            samples = [x for x in raw['samples'] if x['days']==days and x['n']==point['n']]
            require(len(samples)==5, 'Expected five paired repeats')
            pcts = []
            for x in samples:
                require(x['all_results_match'], 'Recorded correctness failure')
                require(x['offset_sequence']==cfg['sequences'][x['repeat']][:x['n']], 'Query sequence mismatch')
                require(math.isclose(x['sorted_total_s'], raw['R_median_s']+x['sorted_query_batch_s']), 'Total mismatch')
                pcts.append(100*(x['random_query_batch_s']-x['sorted_total_s'])/x['random_query_batch_s'])
            require(math.isclose(st.median(pcts),point['median_pct'],abs_tol=1e-10), 'Percentage mismatch')
            require(sum(p>=10 for p in pcts)==point['at_least_10pct_repeats'], 'Threshold mismatch')
    result = {'benchmark_rerun': False, 'root': str(ROOT), 'checked_sha256': checked,
              'main_pairs_checked':len(raw['samples']), 'main_percentage_points_checked':38,
              'optional_raw_data': optional_data,
              'scope':'Stored hashes, recorded checks, query sequences and main arithmetic; not re-executed query correctness or physical IO verification.'}
    return result

def error_analysis(out):
    verify_history()
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    cfg = read(ROOT/MAIN/'config_frozen.json')
    m = read(ROOT/MAIN/'measurements.json')
    R = m['R_median_s']
    combinations = []
    for source in cfg['pilot_sources']:
        for days in [1,7]:
            s = source['summary'][str(days)]
            r, t = s['pilot_reorder_median_s'], s['sorted']['median_s']
            points = []
            for n in cfg['counts']:
                rows = [x for x in m['samples'] if x['days']==days and x['n']==n]
                Q = st.median(x['sorted_query_batch_s'] for x in rows)
                T = st.median(x['sorted_total_s'] for x in rows)
                require(math.isclose(T,R+Q), 'Median identity failed')
                eq = (n*t-Q)/Q*100
                er = (r-R)/R*100
                et = (r+n*t-T)/T*100
                require(math.isclose(et,R/T*er+Q/T*eq,abs_tol=1e-10), 'Error decomposition failed')
                points.append({'n':n, 'observed_query_median_s':Q,'observed_total_median_s':T,
                               'predicted_query_s':n*t,'predicted_total_s':r+n*t,
                               'R_share_pct':R/T*100,'query_signed_error_pct':eq,
                               'query_abs_error_pct':abs(eq),'total_signed_error_pct':et,
                               'total_abs_error_pct':abs(et),'R_signed_error_pct':er,
                               'query_signed_contribution_pp':Q/T*eq,'R_signed_contribution_pp':R/T*er})
            combinations.append({'pilot':source['name'],'days':days,'pilot_R_s':r,'pilot_t_s':t,
                                 'max_total_error':max(points,key=lambda p:p['total_abs_error_pct']),
                                 'max_query_error':max(points,key=lambda p:p['query_abs_error_pct']),
                                 'points':points})
    result = {'analysis_date':'2026-11-18', 'stage':'This round, after report v1 and boundary supplement; post-hoc diagnostic only',
              'benchmark_rerun':False,'analysis_script_sha256':sha(__file__),
              'original_total_error_limit_pct':20,'query_error_pass_fail_threshold':None,
              'observed_R_s':R,'aggregation':'Absolute error against median of five observed batches per N; all 19 N, both pilots, both window lengths retained.',
              'formulas':{'total':'100*abs(pilot_R + N*pilot_t - (R+Q))/(R+Q)',
                          'query':'100*abs(N*pilot_t-Q)/Q','R_share':'100*R/(R+Q)',
                          'signed_decomposition':'e_total = R/(R+Q)*e_R + Q/(R+Q)*e_query'},
              'input_sha256':{p.as_posix():sha(ROOT/p) for p in [MAIN/'config_frozen.json', MAIN/'measurements.json', MAIN/'criteria_audit.json']},
              'combinations':combinations}
    save(out/'error_comparison.json',result)
    lines=['# 本轮事后分析：总耗时与查询阶段误差','',
           '全部计算来自历史记录；未重新计时。原 20% 门槛仅用于排序方案总耗时，查询阶段仅作诊断。', '',
           '| 预实验来源 | 窗口 | 最大总耗时误差 | 所在 N | 最大查询阶段误差 | 所在 N |',
           '|---|---:|---:|---:|---:|---:|']
    for c in combinations:
        a,b=c['max_total_error'],c['max_query_error']
        lines.append(f"| {c['pilot']} | {c['days']} 天 | {a['total_abs_error_pct']:.4f}% | {a['n']} | {b['query_abs_error_pct']:.4f}% | {b['n']} |")
    lines+=['','## 全部已测次数（每个误差对应五轮实测中位数）','',
            '| 来源 | 天数 | N | 排序占比 % | 总耗时误差 % | 查询阶段误差 % |',
            '|---|---:|---:|---:|---:|---:|']
    for c in combinations:
        for p in c['points']:
            lines.append(f"| {c['pilot']} | {c['days']} | {p['n']} | {p['R_share_pct']:.4f} | {p['total_abs_error_pct']:.4f} | {p['query_abs_error_pct']:.4f} |")
    (out/'error_comparison.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return result

def create_workspace(dest):
    verify_history()
    dest = Path(dest).resolve()
    require(not dest.exists(), 'Workspace must not already exist')
    dest.mkdir(parents=True)
    for name in ['results','archive','tools']:
        shutil.copytree(ROOT/name,dest/name)
    for p in [*ROOT.glob('*.py'), *ROOT.glob('requirements*.txt')]:
        shutil.copy2(p,dest/p.name)
    save(dest/'replay_v2.json',{'version':2,'source_root_at_creation':str(ROOT),
         'adapter_sha256':sha(__file__),'copied_files_sha256':{p.relative_to(dest).as_posix():sha(p) for p in dest.rglob('*') if p.is_file()},
         'note':'Isolated workspace. Historical sources copied unchanged. Raw data must be generated; no timings executed by workspace creation.'})
    return {'workspace':str(dest),'benchmark_rerun':False}

def require_workspace():
    require((ROOT/'replay_v2.json').is_file(),'Use create-workspace first; never run benchmarks in the historical repository')

def check_runtime():
    import duckdb
    require(duckdb.__version__=='2.0.0','Use pinned duckdb==2.0.0; do not silently change data/hash semantics')
    return duckdb

def generate_data():
    require_workspace()
    duckdb = check_runtime()
    require(not (ROOT/'data').exists(),'Refuse to overwrite existing data; create a new workspace')
    raw = ROOT/'data/pilot/1000000/random.parquet'
    sorted_file = ROOT/'data/formal'/MAIN_ID/'time_sorted.parquet'
    raw.parent.mkdir(parents=True)
    sorted_file.parent.mkdir(parents=True)
    con = duckdb.connect()
    con.execute('SET threads=1')
    con.execute("SET memory_limit='1GB'")
    con.execute('SET preserve_insertion_order=true')
    def q(p): return "'"+p.as_posix().replace("'","''")+"'"
    con.execute(f"SET temp_directory={q(ROOT/'data/temp')}")
    # Exact generator SQL, extracted from the preserved historical pilot (no eval).
    source = (ROOT/'pilot_parquet.py').read_text(encoding='utf-8')
    begin = source.index('    gen = f"""')+len('    gen = f"""')
    gen = source[begin:source.index('"""',begin)].replace('{args.rows}','1000000')
    require('{' not in gen and '}' not in gen,'Unexpected generator template; review before use')
    opts='(FORMAT PARQUET, COMPRESSION ZSTD, COMPRESSION_LEVEL 3, ROW_GROUP_SIZE 65536)'
    con.execute(f'COPY ({gen}) TO {q(raw)} {opts}')
    con.execute(f'COPY (SELECT * FROM read_parquet({q(raw)}) ORDER BY event_time, observation_id) TO {q(sorted_file)} {opts}')
    con.close()
    expected={raw:read(ROOT/MAIN/'config_frozen.json')['raw_sha256'],
              sorted_file:read(ROOT/MAIN/'preparation.json')['sorted_sha256']}
    results={p.relative_to(ROOT).as_posix():{'sha256':sha(p),'expected_sha256':digest,'matches':sha(p)==digest} for p,digest in expected.items()}
    save(ROOT/'data_generation_v2.json',{'benchmark_rerun':False,'performance_timing_collected':False,
         'purpose':'Regenerate exact historical inputs only; sorting here is not a cost measurement',
         'duckdb':duckdb.__version__,'generator_script_sha256':sha(ROOT/'pilot_parquet.py'),
         'generator_sql':gen,'files':results})
    require(all(x['matches'] for x in results.values()),'Generated bytes differ from history. Stop; do not replace historical data or timings. See data_generation_v2.json')
    return results

def load_module(filename):
    spec=importlib.util.spec_from_file_location('historical_'+Path(filename).stem,ROOT/filename)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def valid_id(value):
    require(bool(re.fullmatch(r'[A-Za-z0-9_-]+',value)),'Use a simple ASCII run ID')
    require(value not in (MAIN_ID,SUPP_ID,'pilot_1m_run1','pilot_1m_run2'),'Historical IDs are protected')
    return value

def provenance(action, run_id):
    p=ROOT/'replay_logs'/f'{action}_{run_id}.json'
    save(p,{'action':action,'run_id':run_id,'recorded_at':dt.datetime.now(dt.timezone.utc).isoformat(),
            'adapter_sha256':sha(__file__),'python':sys.version,
            'source_sha256':{f:sha(ROOT/f) for f in ['pilot_parquet.py','formal_experiment.py','supplement_boundary.py']},
            'note':'Separate versioned interface; historical source code is unchanged. A start record alone does not prove completion.'})

def run_main(run_id):
    require_workspace(); valid_id(run_id); check_runtime()
    require(not (ROOT/'results/formal'/run_id).exists(),'Output already exists')
    provenance('run-main',run_id)
    subprocess.run([sys.executable,str(ROOT/'formal_experiment.py'),'--run-id',run_id],check=True,cwd=ROOT)

def run_pilot(label):
    require_workspace(); valid_id(label); check_runtime()
    require(not (ROOT/'results/pilot'/f'{label}.json').exists(),'Output already exists')
    provenance('run-pilot',label)
    subprocess.run([sys.executable,str(ROOT/'pilot_parquet.py'),'--rows','1000000','--label',label],check=True,cwd=ROOT)

def supplement(phase,run_id):
    require_workspace(); valid_id(run_id); check_runtime()
    m=load_module('supplement_boundary.py')
    # Redirect only run identity/output. Main inputs/cost stay the historical reference,
    # matching the original supplemental design. Newly prepared source paths are local.
    m.RUN=run_id; m.OUT=ROOT/'results/supplement'/run_id
    if phase=='prepare':
        require(not m.OUT.exists(),'Output already exists')
        provenance('prepare-supplement',run_id)
        m.prepare()
        save(m.OUT/'interface_v2.json',{'adapter_sha256':sha(__file__),'run_id':run_id,
             'main_reference':MAIN_ID,'R_policy':'Reuse historical R exactly as original supplement',
             'historical_script_sha256':sha(ROOT/'supplement_boundary.py')})
    elif phase=='run':
        info=read(m.OUT/'interface_v2.json')
        require(info['adapter_sha256']==sha(__file__),'Adapter changed after prepare')
        provenance('run-supplement',run_id)
        m.run()
    else:
        require((m.OUT/'measurements.json').is_file(),'Run has no measurements')
        require(not (m.OUT/'summary.json').exists(),'Refuse to overwrite a derived summary')
        m.analyze()

def analyze_main(run_id):
    require_workspace();valid_id(run_id)
    folder=ROOT/'results/formal'/run_id
    require((folder/'measurements.json').is_file(),'Run has no measurements')
    require(not (folder/'summary.json').exists(),'Refuse to overwrite a derived summary')
    subprocess.run([sys.executable,str(ROOT/'plot_formal.py'),'--run-id',run_id],check=True,cwd=ROOT)
    save(folder/'artifact_manifest.json',{'files':[{'path':p.relative_to(ROOT).as_posix(),
          'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(folder.iterdir()) if p.is_file()]})
    module=load_module('audit_criteria.py')
    module.FOLDER=folder
    module.main()

def render_history(dest):
    # Windows legacy fonts are deliberately kept; absence fails explicitly.
    require(Path('C:/Windows/Fonts/msyh.ttc').exists(),'Legacy chart reproduction requires Windows Microsoft YaHei font')
    create_workspace(dest)
    dest=Path(dest).resolve()
    env_args=[sys.executable]
    # Verify audit inputs before the plotting code rewrites derived figures/summary.
    subprocess.run(env_args+[str(dest/'audit_criteria.py')],check=True,cwd=dest)
    subprocess.run(env_args+[str(dest/'plot_formal.py')],check=True,cwd=dest)
    subprocess.run(env_args+[str(dest/'supplement_boundary.py'),'analyze'],check=True,cwd=dest)
    return {'output':str(dest),'benchmark_rerun':False,'note':'Regenerated derived figures only. Original repository untouched; copied manifests may differ after rendering.'}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    sub=ap.add_subparsers(dest='command',required=True)
    p=sub.add_parser('verify-history');p.add_argument('--out')
    p=sub.add_parser('analyze-errors');p.add_argument('--out',required=True)
    p=sub.add_parser('create-workspace');p.add_argument('--workspace',required=True)
    sub.add_parser('generate-data')
    p=sub.add_parser('run-main');p.add_argument('--run-id',required=True)
    p=sub.add_parser('analyze-main');p.add_argument('--run-id',required=True)
    p=sub.add_parser('run-pilot');p.add_argument('--label',required=True)
    for name in ['prepare-supplement','run-supplement','analyze-supplement']:
        p=sub.add_parser(name);p.add_argument('--run-id',required=True)
    p=sub.add_parser('render-history');p.add_argument('--out',required=True)
    args=ap.parse_args()
    if args.command=='verify-history':
        result=verify_history()
        if args.out: save(Path(args.out),result)
        print(json.dumps({'ok':True,'hashes_checked':len(result['checked_sha256']),
                          'main_pairs_checked':result['main_pairs_checked'],'optional_data':result['optional_raw_data']},ensure_ascii=False))
    elif args.command=='analyze-errors':
        result=error_analysis(args.out)
        print(json.dumps([{'pilot':c['pilot'],'days':c['days'],
                          'max_total_error_pct':c['max_total_error']['total_abs_error_pct'],
                          'max_query_error_pct':c['max_query_error']['query_abs_error_pct']} for c in result['combinations']],ensure_ascii=False))
    elif args.command=='create-workspace': print(json.dumps(create_workspace(args.workspace),ensure_ascii=False))
    elif args.command=='generate-data': print(json.dumps(generate_data(),ensure_ascii=False))
    elif args.command=='run-main': run_main(args.run_id)
    elif args.command=='analyze-main': analyze_main(args.run_id)
    elif args.command=='run-pilot': run_pilot(args.label)
    elif args.command=='prepare-supplement': supplement('prepare',args.run_id)
    elif args.command=='run-supplement': supplement('run',args.run_id)
    elif args.command=='analyze-supplement': supplement('analyze',args.run_id)
    elif args.command=='render-history': print(json.dumps(render_history(args.out),ensure_ascii=False))

if __name__=='__main__':
    main()
