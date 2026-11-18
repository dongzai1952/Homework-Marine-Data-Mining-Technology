"""Reproducible local pilot; Python 3.12+, duckdb==2.0.0, no report generation."""
from pathlib import Path
import argparse
import datetime as dt
import hashlib
import json
import math
import platform
import random
import statistics as stats
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'work' / 'python_packages'))
import duckdb

def quantile(xs, p):
    ys = sorted(xs)
    pos = (len(ys) - 1) * p
    lo = int(pos)
    return ys[lo] + (ys[min(lo + 1, len(ys) - 1)] - ys[lo]) * (pos - lo)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rows', type=int, default=1_000_000)
    ap.add_argument('--label', default='pilot_1m')
    args = ap.parse_args()
    folder = ROOT / 'work' / 'parquet_pilot' / str(args.rows)
    folder.mkdir(parents=True, exist_ok=True)
    raw, ordered = folder / 'random.parquet', folder / 'time_sorted.parquet'
    out = ROOT / 'outputs' / (args.label + '.json')
    con = duckdb.connect()
    con.execute("SET threads=1")
    con.execute("SET memory_limit='1GB'")
    con.execute("SET temp_directory='" + (folder / 'temp').as_posix() + "'")
    con.execute("SET preserve_insertion_order=true")
    def path(p):
        return "'" + p.as_posix().replace("'", "''") + "'"
    def copy(sql, p):
        con.execute(f"COPY ({sql}) TO {path(p)} (FORMAT PARQUET, COMPRESSION ZSTD, COMPRESSION_LEVEL 3, ROW_GROUP_SIZE 65536)")

    # Hash inputs produce reproducible pseudo-random timestamps, independent of row ID.
    # Seed/domain separators and DuckDB version are recorded; no realistic ocean claim.
    gen = f"""SELECT i::BIGINT AS observation_id,
      TIMESTAMP '2026-06-01' + (hash(i, 1729, 'time') % 2592000)::BIGINT * INTERVAL '1 second' AS event_time,
      (hash(i, 1729, 'station') % 1000)::INTEGER AS station_id,
      (10000000 + hash(i, 1729, 'lat') % 35000001)::INTEGER AS latitude_microdeg,
      (110000000 + hash(i, 1729, 'lon') % 30000001)::INTEGER AS longitude_microdeg,
      (500 + hash(i, 1729, 'temp') % 2501)::INTEGER AS temperature_centi_c
      FROM range({args.rows}) AS t(i)"""
    start = time.perf_counter()
    copy(gen, raw)
    generation_s = time.perf_counter() - start
    print(json.dumps({'stage': 'generated', 'rows': args.rows, 'seconds': generation_s}), flush=True)
    reorder = []
    for rep in range(3):
        start = time.perf_counter()
        copy(f'SELECT * FROM read_parquet({path(raw)}) ORDER BY event_time, observation_id', ordered)
        reorder.append(time.perf_counter() - start)
    print(json.dumps({'stage': 'sorted', 'reorder_seconds': reorder}), flush=True)
    con.execute(f'CREATE VIEW raw_data AS SELECT * FROM read_parquet({path(raw)})')
    con.execute(f'CREATE VIEW sorted_data AS SELECT * FROM read_parquet({path(ordered)})')

    counts = {}
    for view in ['raw_data', 'sorted_data']:
        counts[view] = con.execute(f'SELECT count(*), count(DISTINCT observation_id) FROM {view}').fetchone()
        assert counts[view] == (args.rows, args.rows)
    mismatches = con.execute("""SELECT count(*) FROM raw_data a FULL OUTER JOIN sorted_data b
      USING (observation_id) WHERE a.observation_id IS NULL OR b.observation_id IS NULL
      OR a.event_time IS DISTINCT FROM b.event_time
      OR a.station_id IS DISTINCT FROM b.station_id
      OR a.latitude_microdeg IS DISTINCT FROM b.latitude_microdeg
      OR a.longitude_microdeg IS DISTINCT FROM b.longitude_microdeg
      OR a.temperature_centi_c IS DISTINCT FROM b.temperature_centi_c""").fetchone()[0]
    assert mismatches == 0

    metadata = {}
    for name, p in [('random', raw), ('sorted', ordered)]:
        meta = con.execute(f"""SELECT row_group_id, row_group_num_rows, stats_min, stats_max
          FROM parquet_metadata({path(p)}) WHERE path_in_schema='event_time' ORDER BY row_group_id""").fetchall()
        metadata[name] = [{'group': r[0], 'rows': r[1], 'min': r[2], 'max': r[3]} for r in meta]
    assert [r['rows'] for r in metadata['random']] == [r['rows'] for r in metadata['sorted']]

    starts = [0, 4, 8, 12, 16, 20, 23]
    queries, correctness, pruning = {}, [], []
    for days in [1, 7]:
        queries[days] = {'random': [], 'sorted': []}
        for day in starts:
            begin = dt.datetime(2026, 6, 1) + dt.timedelta(days=day)
            end = begin + dt.timedelta(days=days)
            result = {}
            for layout, view in [('random', 'raw_data'), ('sorted', 'sorted_data')]:
                sql = f"""SELECT count(*), sum(temperature_centi_c), avg(temperature_centi_c)/100.0
                  FROM {view} WHERE event_time >= TIMESTAMP '{begin}' AND event_time < TIMESTAMP '{end}'"""
                queries[days][layout].append(sql)
                result[layout] = con.execute(sql).fetchone()
                groups = metadata[layout]
                skipped = sum(dt.datetime.fromisoformat(g['max']) < begin or dt.datetime.fromisoformat(g['min']) >= end for g in groups)
                pruning.append({'days': days, 'start': str(begin), 'layout': layout,
                                'groups': len(groups), 'metadata_skippable_groups': skipped})
            assert result['random'][:2] == result['sorted'][:2]
            assert math.isclose(result['random'][2], result['sorted'][2], rel_tol=1e-12, abs_tol=1e-10)
            correctness.append({'days': days, 'start': str(begin), 'count': result['random'][0],
                                'sum_centi_c': result['random'][1], 'avg_c': result['random'][2]})
    # Explicitly warmed, repeated-query experiment. No cold-cache or durable-fsync claim.
    for _ in range(2):
        for days in [1, 7]:
            for layout in ['random', 'sorted']:
                for sql in queries[days][layout]:
                    con.execute(sql).fetchone()
    rng = random.Random(20261117)
    batches = []
    for rep in range(9):
        windows = [1, 7]
        rng.shuffle(windows)
        for days in windows:
            order = ['random', 'sorted'] if rep % 2 == 0 else ['sorted', 'random']
            indices = list(range(len(starts))) * 5
            rng.shuffle(indices)
            for layout in order:
                start = time.perf_counter_ns()
                for idx in indices:
                    con.execute(queries[days][layout][idx]).fetchone()
                elapsed = (time.perf_counter_ns() - start) / 1e9
                batches.append({'repeat': rep, 'days': days, 'layout': layout,
                                'order': order.index(layout), 'queries': len(indices),
                                'batch_s': elapsed, 'per_query_s': elapsed / len(indices)})
        print(json.dumps({'stage': 'timing', 'repeat_completed': rep + 1}), flush=True)
    summary = {}
    bootstrap = random.Random(42)
    for days in [1, 7]:
        a = [r['per_query_s'] for r in batches if r['days'] == days and r['layout'] == 'random']
        b = [r['per_query_s'] for r in batches if r['days'] == days and r['layout'] == 'sorted']
        delta = [x-y for x,y in zip(a,b)]
        boot = [stats.median(bootstrap.choices(delta, k=len(delta))) for _ in range(5000)]
        def describe(values):
            return {'median_s': stats.median(values), 'iqr_over_median':
                    (quantile(values,.75)-quantile(values,.25))/stats.median(values)}
        ci = [quantile(boot,.025), quantile(boot,.975)]
        sa, sb = describe(a), describe(b)
        delta_median = stats.median(delta)
        summary[str(days)] = {
            'random': sa, 'sorted': sb,
            'median_paired_saving_s': delta_median,
            'paired_saving_bootstrap95_s': ci,
            'sorted_faster_pairs': sum(d > 0 for d in delta), 'pairs': len(delta),
            'median_latency_ratio': sa['median_s']/sb['median_s'],
            'pilot_reorder_median_s': stats.median(reorder),
            'illustrative_break_even_queries': math.ceil(stats.median(reorder)/delta_median) if delta_median>0 else None,
            'timing_stable': max(sa['iqr_over_median'],sb['iqr_over_median']) <= .20,
            'clear_positive_difference': ci[0] > 0 and sum(d>0 for d in delta)>=8,
            'clear_negative_difference': ci[1] < 0 and sum(d<0 for d in delta)>=8,
        }
    result = {'label': args.label, 'rows': args.rows, 'duckdb': duckdb.__version__,
              'python': platform.python_version(), 'platform': platform.platform(),
              'threads': 1, 'memory_limit': '1GB', 'row_group_size': 65536,
              'compression': 'ZSTD level 3', 'seed': 1729, 'cache_regime': 'warmed repeated queries',
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'generation_s_excluded': generation_s, 'reorder_s': reorder,
              'sizes_bytes': {'random':raw.stat().st_size,'sorted':ordered.stat().st_size},
              'full_table_mismatch_count': mismatches,'unique_id_counts': counts,
              'query_correctness': correctness, 'row_group_metadata': metadata,
              'metadata_pruning_estimates_not_measured_io': pruning,
              'batches': batches, 'summary': summary}
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(out), 'summary':summary},ensure_ascii=False), flush=True)

if __name__ == '__main__':
    main()
