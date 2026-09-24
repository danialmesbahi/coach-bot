"""Read-only, bounded summary of current and rotated private JSONL diagnostics.

Run: python scripts/review_diagnostics.py --since 2026-09-22T08:30:00Z
No raw messages, tokens, bodies or customer files are included in the report.
"""
import argparse
import json
from datetime import datetime,timezone
from pathlib import Path


def timestamp(value):
    if not isinstance(value,str): raise ValueError('Expected an ISO timestamp')
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def summarize(directory,since=None):
    groups={};bad=0;files=[];count=0;dropped=0;latest={}
    for path in sorted(Path(directory).glob('*.jsonl*')):
        if not path.is_file(): continue
        files.append(path.name)
        with path.open(encoding='utf-8',errors='replace') as stream:
            for line in stream:
                try:
                    row=json.loads(line);when=timestamp(row['time'])
                    if since and when<since: continue
                    if not isinstance(row.get('event'),str): raise ValueError()
                except (ValueError,TypeError,KeyError):
                    bad+=1;continue
                service=path.name.split('.jsonl')[0]
                count+=1
                latest[service]=max(latest.get(service,''),when.isoformat())
                event=row['event'][:100]
                if event=='diagnostics_dropped' and type(row.get('dropped')) is int: dropped+=max(0,row['dropped'])
                key=(service,event,str(row.get('exception',''))[:100],str(row.get('error_code',''))[:100],str(row.get('route',''))[:100],str(row.get('level',''))[:10])
                # Fixed metadata keys only; don't echo arbitrary JSON or exception messages.
                item=groups.setdefault(key,{'service':service,'event':event,'exception':key[2],'code':key[3],'route':key[4],'level':key[5],
                    'count':0,'first':when.isoformat(),'last':when.isoformat(),'max_ms':0})
                item['count']+=1;item['first']=min(item['first'],when.isoformat());item['last']=max(item['last'],when.isoformat())
                elapsed=row.get('elapsed_ms',0)
                if type(elapsed) in (int,float):item['max_ms']=max(item['max_ms'],elapsed)
    return {'files':files,'records':count,'malformed_lines':bad,'reported_dropped':dropped,'latest_by_service':latest,
            'events':sorted(groups.values(),key=lambda r:r['last'],reverse=True),
            'limits':'Not a proof of bug-free operation. Successful activity is in audit_logs and analytics_buckets; visual defects need screenshots.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',default=str(Path(__file__).resolve().parents[1]/'artifacts'/'diagnostics'))
    parser.add_argument('--since',type=timestamp)
    args=parser.parse_args()
    print(json.dumps(summarize(args.directory,args.since),ensure_ascii=False,indent=2))
