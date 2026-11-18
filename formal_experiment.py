"""Measure complete query batches. No fitted/extrapolated timing is used as observation."""
from pathlib import Path
import argparse
import datetime as dt
import hashlib
import importlib.metadata
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

COUNTS = [1, 10, 20, 22, 23, 24, 25, 26, 28, 29, 30, 31, 32, 33, 34, 36, 40, 50, 100]
OFFSETS = [2, 6, 10, 14, 18, 22]
PILOT_OFFSETS = [0, 4, 8, 12, 16, 20, 23]
REPEATS = 5
SEED = 2026111701

def stamp():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()

def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def save(p, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')

def quoted(p):
    return "'" + Path(p).as_posix().replace("'", "''") + "'"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run-id', default='formal_20261117_01')
    args = ap.parse_args()
    if any(x in args.run_id for x in ['/', '\\', '..']):
        raise ValueError('run-id must be a simple folder name')
    out = ROOT / 'results' / 'formal' / args.run_id
    if out.exists():
        raise FileExistsError('Never overwrite an existing experiment: ' + str(out))
    out.mkdir(parents=True)
    data = ROOT / 'data' / 'formal' / args.run_id
    data.mkdir(parents=True, exist_ok=False)
    raw = ROOT / 'data' / 'pilot' / '1000000' / 'random.parquet'
    sorted_file = data / 'time_sorted.parquet'
    raw_sha = sha(raw)
    pilots = []
    for name in ['pilot_1m_run1.json', 'pilot_1m_run2.json']:
        p = ROOT / 'results' / 'pilot' / name
        obj = json.loads(p.read_text(encoding='utf-8'))
        pilots.append({'name': name, 'sha256': sha(p), 'summary': obj['summary']})
    assert not set(OFFSETS) & set(PILOT_OFFSETS)
    rng = random.Random(SEED)
    sequences = []
    for rep in range(REPEATS):
        seq = []
        while len(seq) < max(COUNTS):
            block = OFFSETS.copy()
            rng.shuffle(block)
            seq.extend(block)
        sequences.append(seq[:max(COUNTS)])
    schedule = []
    for rep in range(REPEATS):
        cases = [(w, n) for w in [1, 7] for n in COUNTS]
        rng.shuffle(cases)
        for w, n in cases:
            order = ['random', 'sorted'] if (rep + COUNTS.index(n) + (w == 7)) % 2 == 0 else ['sorted', 'random']
            schedule.append({'repeat': rep, 'days': w, 'n': n, 'layout_order': order})
    config = {
        'created_at': stamp(), 'run_id': args.run_id, 'status': 'planned_before_timing',
        'rows': 1_000_000, 'counts': COUNTS, 'windows_days': [1,7], 'repeats': REPEATS,
        'heldout_offsets': OFFSETS, 'pilot_offsets': PILOT_OFFSETS,
        'sequences': sequences, 'schedule': schedule, 'seed': SEED,
        'frozen_pilot_estimates': {'1': [24,24], '7': [30,31]}, 'pilot_sources': pilots,
        'raw_path': str(raw), 'raw_sha256': raw_sha, 'script_sha256': sha(__file__),
        'python': platform.python_version(), 'platform': platform.platform(), 'cpu_logical_count': os.cpu_count(),
        'duckdb': duckdb.__version__, 'threads':1, 'memory_limit':'1GB',
        'compression':'ZSTD level 3', 'row_group_rows':65536,
        'cache_regime':'explicitly warmed repeated query workload; no cache flushing',
        'timing':'perf_counter_ns around actual N execute/fetchone calls; result validation outside timer',
        'reorder':'three full read/sort/write COPY calls; median is main R, all three retained',
        'sorted_total':'measured R_median + measured whole-batch query elapsed; not one contiguous wall-clock interval',
        'crossing_rule':'smallest sampled N with median paired savings >0 and all larger sampled N also >0; report adjacent sampled bracket, not interpolation',
        'stronger_crossing_rule':'smallest sampled N where all 5 paired repeats save time and this remains true at all larger sampled N',
        'uncertainty':'min/max of five repeats are a descriptive range, not confidence intervals',
        'prewarm_cost_excluded': True, 'durable_fsync_not_guaranteed': True,
        'notes':['Original pilot ran on C:; formal data and output on E:. Frozen predictions are not recalibrated.',
                 'Heldout queries are new date windows over the same frozen data, not an independent dataset.',
                 'All conditions and sequences frozen before timing; all repeats retained.']}
    save(out / 'config_frozen.json', config)
    log = (out / 'events.jsonl').open('x', encoding='utf-8')
    def emit(event, **kw):
        entry = {'at':stamp(), 'event':event, **kw}
        log.write(json.dumps(entry, ensure_ascii=False) + '\n')
        log.flush()
        print(json.dumps(entry, ensure_ascii=False), flush=True)
    con = duckdb.connect()
    for setting in ["SET threads=1", "SET memory_limit='1GB'", "SET preserve_insertion_order=true",
                    'SET temp_directory=' + quoted(data / 'temp')]:
        con.execute(setting)
    emit('frozen', counts=COUNTS, repeats=REPEATS, expected_query_calls=sum(COUNTS)*REPEATS*4)
    reorder = []
    for i in range(3):
        t = time.perf_counter_ns()
        con.execute(f"COPY (SELECT * FROM read_parquet({quoted(raw)}) ORDER BY event_time, observation_id) TO {quoted(sorted_file)} (FORMAT PARQUET, COMPRESSION ZSTD, COMPRESSION_LEVEL 3, ROW_GROUP_SIZE 65536)")
        elapsed = (time.perf_counter_ns()-t)/1e9
        reorder.append(elapsed)
        emit('reorder', index=i, elapsed_s=elapsed)
    R = st.median(reorder)
    con.execute(f'CREATE VIEW raw_data AS SELECT * FROM read_parquet({quoted(raw)})')
    con.execute(f'CREATE VIEW sorted_data AS SELECT * FROM read_parquet({quoted(sorted_file)})')
    counts = {v:con.execute(f'SELECT count(*), count(DISTINCT observation_id) FROM {v}').fetchone()
              for v in ['raw_data','sorted_data']}
    assert all(x == (1_000_000,1_000_000) for x in counts.values())
    mismatch = con.execute("""SELECT count(*) FROM raw_data a FULL OUTER JOIN sorted_data b USING(observation_id)
      WHERE a.observation_id IS NULL OR b.observation_id IS NULL
      OR a.event_time IS DISTINCT FROM b.event_time OR a.station_id IS DISTINCT FROM b.station_id
      OR a.latitude_microdeg IS DISTINCT FROM b.latitude_microdeg
      OR a.longitude_microdeg IS DISTINCT FROM b.longitude_microdeg
      OR a.temperature_centi_c IS DISTINCT FROM b.temperature_centi_c""").fetchone()[0]
    assert mismatch == 0
    metadata = {}
    for layout,p in [('random',raw),('sorted',sorted_file)]:
        rows = con.execute(f"SELECT row_group_id,row_group_num_rows,stats_min,stats_max FROM parquet_metadata({quoted(p)}) WHERE path_in_schema='event_time' ORDER BY row_group_id").fetchall()
        metadata[layout] = [{'id':r[0],'rows':r[1],'min':r[2],'max':r[3]} for r in rows]
    assert [r['rows'] for r in metadata['random']] == [r['rows'] for r in metadata['sorted']]
    sqls, answers, checks, pruning = {}, {}, [], []
    for w in [1,7]:
        for offset in OFFSETS:
            begin = dt.datetime(2026,6,1) + dt.timedelta(days=offset)
            end = begin + dt.timedelta(days=w)
            results = {}
            for layout,view in [('random','raw_data'),('sorted','sorted_data')]:
                sql = f"SELECT count(*),sum(temperature_centi_c),avg(temperature_centi_c)/100.0 FROM {view} WHERE event_time>=TIMESTAMP '{begin}' AND event_time<TIMESTAMP '{end}'"
                sqls[(w,offset,layout)] = sql
                results[layout] = con.execute(sql).fetchone()
                groups = metadata[layout]
                skipped = sum(dt.datetime.fromisoformat(g['max']) < begin or dt.datetime.fromisoformat(g['min']) >= end for g in groups)
                pruning.append({'days':w,'offset':offset,'layout':layout,'total_groups':len(groups),'metadata_skippable_groups':skipped})
            a,b = results['random'],results['sorted']
            assert a[:2] == b[:2] and math.isclose(a[2],b[2],rel_tol=1e-12,abs_tol=1e-10)
            answers[(w,offset)] = a
            checks.append({'days':w,'offset':offset,'begin':str(begin),'end':str(end),
                           'count':a[0],'sum_centi_c':a[1],'mean_c':a[2],'identical':True})
    preparation = {'reorder_s':reorder,'R_median_s':R,'full_table_mismatches':mismatch,
                   'unique_counts':counts,'query_checks':checks,'metadata':metadata,
                   'metadata_pruning_estimates':pruning,'sorted_sha256':sha(sorted_file),
                   'sizes_bytes':{'random':raw.stat().st_size,'sorted':sorted_file.stat().st_size}}
    save(out/'preparation.json', preparation)
    emit('verified', full_table_mismatches=mismatch, query_windows=len(checks), R_median_s=R)
    samples = []
    start_experiment = time.perf_counter()
    for case_index, case in enumerate(schedule):
        rep,w,n = case['repeat'],case['days'],case['n']
        offsets = sequences[rep][:n]
        # Equal explicit warm-up for both layouts immediately before each measured pair.
        for layout in case['layout_order']:
            for offset in OFFSETS:
                con.execute(sqls[(w,offset,layout)]).fetchone()
        elapsed_by_layout = {}
        for layout in case['layout_order']:
            batch_sql = [sqls[(w,offset,layout)] for offset in offsets]
            actual_results = []
            start_ns = time.perf_counter_ns()
            for sql in batch_sql:
                actual_results.append(con.execute(sql).fetchone())
            elapsed = (time.perf_counter_ns()-start_ns)/1e9
            for offset, actual in zip(offsets,actual_results):
                expected = answers[(w,offset)]
                assert actual[:2] == expected[:2]
                assert math.isclose(actual[2],expected[2],rel_tol=1e-12,abs_tol=1e-10)
            elapsed_by_layout[layout] = elapsed
        rec = {**case,'offset_sequence':offsets, 'random_query_batch_s':elapsed_by_layout['random'],
               'sorted_query_batch_s':elapsed_by_layout['sorted'], 'R_median_s':R,
               'sorted_total_s':R+elapsed_by_layout['sorted'],
               'paired_saving_s':elapsed_by_layout['random']-R-elapsed_by_layout['sorted'],
               'all_results_match':True}
        samples.append(rec)
        log.write(json.dumps({'event':'batch_pair','at':stamp(),**rec},ensure_ascii=False)+'\n')
        log.flush()
        if (case_index+1)%10 == 0 or case_index+1 == len(schedule):
            emit('progress', completed_pairs=case_index+1,total_pairs=len(schedule),
                 measured_query_calls=sum(2*r['n'] for r in samples),elapsed_s=time.perf_counter()-start_experiment)
    assert sha(raw) == raw_sha
    result = {'run_id':args.run_id,'finished_at':stamp(),'config_sha256':sha(out/'config_frozen.json'),
              'reorder_s':reorder,'R_median_s':R,'samples':samples,'pairs':len(samples),
              'actual_measured_query_calls':sum(2*r['n'] for r in samples),
              'all_results_match':True,'input_unchanged':True,'elapsed_experiment_s':time.perf_counter()-start_experiment}
    save(out/'measurements.json', result)
    emit('complete', output=str(out), pairs=len(samples), R_median_s=R)
    log.close()

if __name__ == '__main__':
    main()
