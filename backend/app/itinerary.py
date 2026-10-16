"""Fictional catalog planning: no external claims, prices, routes or reservations."""
import json
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from .itinerary_schemas import Activity,ItineraryResult,DayPlan,Stop

DISCLAIMER='Fictional demo itinerary. Venues and activities are invented; opening hours, travel times, prices, accessibility and availability are not verified. No activities or transport have been booked.'

@lru_cache(maxsize=1)
def catalog():
    rows=json.loads((Path(__file__).parent/'data/goa_itinerary.json').read_text())
    return tuple(Activity.model_validate(row) for row in rows)

def create_plan(arg):
    from .tools import BusinessError
    p=arg.preferences
    if p.days is None or p.region is None:raise BusinessError('Please specify an itinerary duration and Goa area first.')
    if set(p.interests)&set(p.avoid):raise BusinessError('An activity category is both requested and excluded. Please clarify your interests.')
    options=[a for a in catalog() if a.region==p.region and a.category not in p.avoid and (not p.family_friendly or a.family_friendly)]
    if p.interests:options=[a for a in options if a.category in p.interests]
    if not options:raise BusinessError('No fictional activities match these preferences. Please broaden your interests or exclusions.')
    # Interleave categories so interests are spread across days, not consumed in blocks.
    categories=list(dict.fromkeys(a.category for a in options))
    ordered=[]
    while options:
        for category in categories:
            match=next((a for a in options if a.category==category),None)
            if match:ordered.append(match);options.remove(match)
    slots={'relaxed':['morning','evening'],'balanced':['morning','afternoon','evening'],'busy':['morning','late_morning','afternoon','evening']}[p.pace]
    days=[];cursor=0
    for index in range(p.days):
        activities=ordered[cursor:cursor+len(slots)];cursor+=len(activities)
        days.append(DayPlan(day=index+1,date=arg.start_date+timedelta(days=index) if arg.start_date else None,stops=[Stop(slot=slot,activity=a) for slot,a in zip(slots,activities)],note='The matching demo catalog is exhausted; remaining time is left free.' if len(activities)<len(slots) else None))
    return ItineraryResult(region=p.region,pace=p.pace,preferences=p,days=days,disclaimer=DISCLAIMER).model_dump(mode='json')
