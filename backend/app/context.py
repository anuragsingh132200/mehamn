"""Bounded context built from authoritative state and scoped recent messages."""
from datetime import datetime
from zoneinfo import ZoneInfo
from .config import settings

AMENITIES=["wifi","private_pool","shared_pool","beach_access","parking","kitchenette","family_suite","balcony","villa","restaurant"]

def build_context(message,state,history=(),tool_results=(),round_number=0):
    recent=[{"role":m["role"],"content":m["content"][:settings.context_message_chars]} for m in list(history)[-settings.recent_message_window:]]
    # Exclude historical token usage, session credentials and internal flags/policies.
    data=state.model_dump(mode="json",exclude={"messages","model_usage","last_tool_results"})
    return {"current_date":datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat(),"timezone":"Asia/Kolkata","state":data,"recent_messages":recent,"latest_message":message,"amenity_keys":AMENITIES,"verified_tool_results":list(tool_results)[-settings.context_tool_window:],"planning_round":round_number,"single_room_booking":True,"fictional_collection":True}
