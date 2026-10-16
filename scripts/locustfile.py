"""Run ONLY against a disposable, seeded demo database with a configured live OpenAI model.
locust -f scripts/locustfile.py --host http://localhost:8000 --headless -u 8 -r 2 -t 30s --csv reports/locust
Covers property search, concurrent chat/search+availability, and shared last-unit hold contention.
"""
from locust import HttpUser, task, between
from uuid import uuid4
from datetime import date,timedelta
import os

class Guest(HttpUser):
    wait_time=between(.2,.6)
    def on_start(self): self.start_session()
    def start_session(self):
        r=self.client.post('/api/sessions',name='create_session')
        if r.status_code!=201: self.sid=None;return
        data=r.json();self.sid=data['session_id'];self.headers={'Authorization':'Bearer '+data['token']}
        self.stage=0
    def chat(self,message,name):
        return self.client.post('/api/chat',name=name,headers=self.headers,json={'session_id':self.sid,'message':message,'idempotency_key':str(uuid4())})
    @task(2)
    def hotels(self): self.client.get('/api/properties',name='hotel_search')
    @task(3)
    def booking(self):
        if not self.sid: self.start_session();return
        # Shared dates and private-pool single-unit villas create real contention.
        arrival=date.today()+timedelta(days=int(os.environ.get("MIRA_LOAD_OFFSET_DAYS","40")));departure=arrival+timedelta(days=2)
        if self.stage==0:
            r=self.chat(f'Goa {arrival} to {departure} for 2 adults private pool','chat_search_and_availability')
            if r.status_code==200 and r.json()['state']['latest_recommendations']:self.stage=1
        elif self.stage==1:
            r=self.chat('Select option 1','chat_select')
            if r.status_code==200:self.stage=2
        else:
            self.chat('Confirm hold','chat_hold_contention');self.start_session()

# Capture final counters explicitly: periodic CSV snapshots can precede the last requests.
from locust import events
from pathlib import Path
import json

@events.quitting.add_listener
def final_report(environment, **kwargs):
    stats=environment.stats.total
    data={"kind":"short_local_locust_probe_not_capacity_benchmark","configured_users":getattr(environment.parsed_options,"num_users",None),"users_at_shutdown":environment.runner.user_count if environment.runner else 0,"mode":"openai","requests":stats.num_requests,"failures":stats.num_failures,"failure_rate":stats.fail_ratio,"observed_rps":stats.total_rps,"median_ms":stats.median_response_time,"p95_ms":stats.get_response_time_percentile(.95),"operations":[]}
    for (name,method),entry in sorted(environment.stats.entries.items()):
        data['operations'].append({"method":method,"name":name,"requests":entry.num_requests,"failures":entry.num_failures,"median_ms":entry.median_response_time,"p95_ms":entry.get_response_time_percentile(.95)})
    path=Path(__file__).resolve().parents[1]/'reports/locust-final.json'
    path.write_text(json.dumps(data,indent=2))
