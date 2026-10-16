"""HTTP/DB integration proof against an existing local demo stack (not a unit test)."""
import json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.db import SessionLocal
from app.models import BookingHold,Conversation
from sqlalchemy import select,text,func
report={}
with SessionLocal() as db:
    report['properties']=db.scalar(text('SELECT count(*) FROM properties'))
    report['room_types']=db.scalar(text('SELECT count(*) FROM room_types'))
    report['graph_checkpoints']=db.scalar(text('SELECT count(*) FROM checkpoints'))
    report['committed_holds']=db.scalar(select(func.count()).select_from(BookingHold))
    report['state_version_max']=db.scalar(select(func.max(Conversation.version)))
    # Group live claims by room-night to verify the demo load did not overbook.
    overbooked=db.execute(text('''
      WITH occupancy AS (
        SELECT h.room_type_id, d::date AS night, count(*) AS held
        FROM booking_holds h CROSS JOIN LATERAL generate_series(h.check_in::timestamp,(h.check_out-1)::timestamp,interval '1 day') d
        WHERE h.expires_at > (now() AT TIME ZONE 'UTC')
        GROUP BY h.room_type_id, d
      )
      SELECT count(*) FROM occupancy o JOIN room_inventory i ON i.room_type_id=o.room_type_id
      WHERE o.held + COALESCE((SELECT sum(r.units) FROM reservations r WHERE r.room_type_id=o.room_type_id AND r.check_in<=o.night AND r.check_out>o.night),0)
        + COALESCE((SELECT a.blocked_units FROM room_availability a WHERE a.room_type_id=o.room_type_id AND a.night=o.night),0)>i.units
    ''' )).scalar()
    report['overbooked_room_nights']=overbooked
assert report['properties']==3 and report['room_types']==9
assert report['graph_checkpoints']>0 and report['committed_holds']>0
assert report['overbooked_room_nights']==0,report
path=Path(__file__).resolve().parents[1]/'reports/runtime.json';path.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
