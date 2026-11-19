"""Verify published course artifacts without authentication; no timing runs."""
from pathlib import Path
import argparse, hashlib, json, urllib.request, urllib.parse, datetime

REPO='dongzai1952/Homework-Marine-Data-Mining-Technology'
ROOT=Path(__file__).resolve().parents[1]
FILES=[
    '模拟海洋观测表的Parquet排序收益边界_正式版.pdf',
    'paper/main.pdf',
    'paper/main.tex',
    'AI聊天记录.md',
    'report/figures/01_main_cumulative.png',
    'results/formal/formal_20261117_01/measurements.json',
    'results/supplement/boundary_20261118_01/measurements.json',
    'results/posthoc/error_metrics_v2/error_comparison.json',
]
def get(url):
    request=urllib.request.Request(url,headers={'User-Agent':'course-public-verification','Cache-Control':'no-cache'})
    with urllib.request.urlopen(request,timeout=30) as response:
        return response.status, response.read()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,help='Optional NEW JSON path; existing files are never overwritten')
    args=parser.parse_args()
    if args.out and args.out.exists(): parser.error('--out must not exist')
    result={'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'authentication':'none; no Authorization header or cookies','repository':f'https://github.com/{REPO}','checks':[],'ok':False}
    try:
        status,raw=get(f'https://api.github.com/repos/{REPO}')
        repo=json.loads(raw)
        assert repo['private'] is False and repo['visibility']=='public', 'Repository is not public'
        result.update(repository_api_status=status,visibility=repo['visibility'])
        status,raw=get(f'https://api.github.com/repos/{REPO}/commits/main')
        commit=json.loads(raw)['sha']; result['verified_commit']=commit
        # Stable commit URL avoids a moving branch while checking exact bytes.
        for name in FILES:
            local=(ROOT/name).read_bytes()
            url=f'https://raw.githubusercontent.com/{REPO}/{commit}/'+urllib.parse.quote(name,safe='/')
            code,remote=get(url)
            expected=hashlib.sha256(local).hexdigest(); actual=hashlib.sha256(remote).hexdigest()
            result['checks'].append({'file':name,'url':url,'status':code,'bytes':len(remote),'sha256':actual,'matches_local':actual==expected})
            assert actual==expected, f'Byte mismatch: {name}'
        result['ok']=True
    except Exception as exc:
        result['error']=str(exc)
    text=json.dumps(result,ensure_ascii=False,indent=2)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(text+'\n',encoding='utf-8')
    raise SystemExit(0 if result['ok'] else 1)

if __name__=='__main__': main()
