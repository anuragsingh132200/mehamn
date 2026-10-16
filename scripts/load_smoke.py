"""Small HTTP load probe; reports measured latency/throughput, not capacity claims."""
import argparse,json,time,statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import date,timedelta
from pathlib import Path
from uuid import uuid4
import httpx
p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:8000');p.add_argument('--workers',type=int,default=6);p.add_argument('--iterations',type=int,default=3);args=p.parse_args()
health=httpx.get(args.url+"/health").json()
if not health.get("model_configured"):raise SystemExit("Configure OPENAI_API_KEY before a live HTTP load probe.")
rows=[]

def worker(index):
    local=[]
    with httpx.Client(base_url=args.url,timeout=90) as client:
        def request(method,path,name,**kw):
            tick=time.perf_counter()
            try:
                r=client.request(method,path,**kw)
                local.append({'operation':name,'latency_ms':(time.perf_counter()-tick)*1000,'status':r.status_code,'success':r.is_success})
                r.raise_for_status();return r.json()
            except Exception as exc:
                if not local or local[-1]['operation']!=name:local.append({'operation':name,'latency_ms':(time.perf_counter()-tick)*1000,'status':0,'success':False})
                return None
        for _ in range(args.iterations):
            request('GET','/api/properties','hotel_search')
            s=request('POST','/api/sessions','session_create')
            if not s:continue
            headers={'Authorization':'Bearer '+s['token']}
            def chat(message,name):return request('POST','/api/chat',name,headers=headers,json={'session_id':s['session_id'],'message':message,'idempotency_key':str(uuid4())})
            # All workers share future dates, so the first villa's last unit is contested.
            start=date.today()+timedelta(days=45);end=start+timedelta(days=2)
            found=chat(f'Goa {start} to {end} for 2 adults private pool','chat_search_and_availability')
            if found and found['state']['latest_recommendations']:
                chosen=chat('Select option 1','chat_select')
                if chosen:chat('Confirm hold','chat_hold_contention')
    return local
start=time.perf_counter()
with ThreadPoolExecutor(max_workers=args.workers) as pool:
    for r in pool.map(worker,range(args.workers)):rows.extend(r)
elapsed=time.perf_counter()-start
summary={}
for op in sorted(set(r['operation'] for r in rows)):
    subset=[r for r in rows if r['operation']==op];lat=sorted(r['latency_ms'] for r in subset)
    summary[op]={'requests':len(subset),'median_ms':round(statistics.median(lat),2),'p95_ms':round(lat[min(len(lat)-1,int(len(lat)*.95))],2),'failure_rate':sum(not r['success'] for r in subset)/len(subset)}
result={'mode':health.get('llm_mode'),'kind':'local_smoke_not_capacity_benchmark','workers':args.workers,'iterations_each':args.iterations,'elapsed_seconds':round(elapsed,3),'requests':len(rows),'throughput_rps':round(len(rows)/elapsed,2),'http_failure_rate':sum(not r['success'] for r in rows)/len(rows) if rows else 1,'operations':summary,'note':'HTTP 200 may contain a correct business rejection due to inventory contention. Booking safety is asserted separately in PostgreSQL concurrency tests.'}
path=Path(__file__).resolve().parents[1]/'reports/load-smoke.json';path.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
raise SystemExit(0 if rows and all(r['success'] for r in rows) else 1)
