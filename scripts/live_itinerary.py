"""Small paid live-model itinerary probe against the running demo API."""
import json, os, time
from pathlib import Path
from uuid import uuid4
import httpx

root=Path(__file__).resolve().parents[1]
report={'mode':'live_openai_http','checks':[],'turns':[]}
def check(name,condition):
    report['checks'].append({'name':name,'passed':bool(condition)})
    assert condition,name

try:
    with httpx.Client(base_url=os.environ.get('MIRA_LIVE_URL','http://127.0.0.1:8000'),timeout=120) as client:
        session=client.post('/api/sessions');session.raise_for_status();session=session.json()
        headers={'Authorization':'Bearer '+session['token']}
        def chat(message):
            start=time.perf_counter()
            reply=client.post('/api/chat',headers=headers,json={'session_id':session['session_id'],'message':message,'idempotency_key':str(uuid4())})
            reply.raise_for_status();data=reply.json()
            report['turns'].append({'message':message,'seconds':round(time.perf_counter()-start,2),'response':data['response'],'state':data['state']})
            check('grounded reply without fallback',not data['state']['response_degraded'])
            return data['state']
        state=chat('Plan a three-day relaxed South Goa itinerary for a family, focused on beaches and culture. Exclude adventure. This is only an itinerary, no hotel booking.')
        plan=state['itinerary']
        check('duration, region and pace',len(plan['days'])==3 and plan['region']=='south_goa' and plan['pace']=='relaxed')
        stops=[s['activity'] for d in plan['days'] for s in d['stops']]
        check('interests and family suitability',bool(stops) and all(a['family_friendly'] and a['category'] in ('beach','culture') for a in stops))
        check('no booking mutation',not state['hold'] and not state['quote'] and not state['latest_recommendations'])
        state=chat('Make that itinerary busy instead. Keep the same area, interests and adventure exclusion.')
        check('revision preserves preferences',state['itinerary']['pace']=='busy' and state['itinerary']['region']=='south_goa' and set(state['itinerary_preferences']['interests'])=={'beach','culture'} and 'adventure' in state['itinerary_preferences']['avoid'])
        saved=client.get('/api/sessions/'+session['session_id'],headers=headers);saved.raise_for_status()
        check('saved across session reload',saved.json()['state']['itinerary']==state['itinerary'])
        state=chat('Change this itinerary to nature activities only, still three days in South Goa.')
        check('new interests replace previous interests',state['itinerary_preferences']['interests']==['nature'] and all(s['activity']['category']=='nature' for d in state['itinerary']['days'] for s in d['stops']))
    report['status']='passed'
except Exception as exc:
    report['status']='failed';report['error']=str(exc)
finally:
    (root/'reports').mkdir(exist_ok=True)
    (root/'reports/live-itinerary.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='turns'},indent=2))
if report['status']!='passed':raise SystemExit(1)
