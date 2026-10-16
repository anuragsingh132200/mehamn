"""Typed itinerary preferences and fictional, server-rendered plan records."""
from datetime import date as CalendarDate
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field

class Record(BaseModel):
    model_config=ConfigDict(extra='forbid')
Interest=Literal['beach','culture','food','nature','relaxation','adventure']
Region=Literal['north_goa','south_goa']
Pace=Literal['relaxed','balanced','busy']

class ItineraryPreferences(Record):
    days:int|None=Field(None,ge=1,le=7)
    interests:list[Interest]=Field(default_factory=list,max_length=6)
    avoid:list[Interest]=Field(default_factory=list,max_length=6)
    pace:Pace='balanced'
    region:Region|None=None
    family_friendly:bool=False

class PlanArguments(Record):
    days:int|None=Field(None,ge=1,le=7)
    interests:list[Interest]|None=Field(None,max_length=6)
    avoid:list[Interest]|None=Field(None,max_length=6)
    pace:Pace|None=None
    region:Region|None=None
    family_friendly:bool|None=None

class BuildInput(Record):
    preferences:ItineraryPreferences
    start_date:CalendarDate|None=None

class Activity(Record):
    id:str
    name:str
    region:Region
    category:Interest
    family_friendly:bool
    description:str
    fictional:Literal[True]=True

class Stop(Record):
    slot:Literal['morning','late_morning','afternoon','evening']
    activity:Activity

class DayPlan(Record):
    day:int=Field(ge=1,le=7)
    date:CalendarDate|None=None
    stops:list[Stop]=Field(max_length=4)
    note:str|None=None

class ItineraryResult(Record):
    fictional:Literal[True]=True
    stale:bool=False
    region:Region
    pace:Pace
    preferences:ItineraryPreferences
    days:list[DayPlan]=Field(min_length=1,max_length=7)
    disclaimer:str
