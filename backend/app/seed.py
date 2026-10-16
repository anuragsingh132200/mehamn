"""Exactly three fictional hotels, nine room types. Idempotent deterministic seed."""
from uuid import uuid5, NAMESPACE_URL
from datetime import date
from .db import SessionLocal
from .models import Property, RoomType, RoomInventory, AddOn, PricingPolicy, RoomAvailability, Reservation

def sid(value): return str(uuid5(NAMESPACE_URL, "mehman-fictional/" + value))
HOTELS = [
    ("tide", "Tide & Palm Retreat", "Candolim, North Goa", "A quiet coastal hideaway, a short stroll from Candolim beach.", ["wifi", "shared_pool", "beach_access"], [("Garden King", 2, 6500, ["balcony"]), ("Family Courtyard Suite", 5, 11000, ["family_suite", "balcony"]), ("Private Pool Villa", 4, 18000, ["private_pool", "villa"])]),
    ("casa", "Casa Maré", "Anjuna, North Goa", "A sun-washed boutique stay among Anjuna’s palms.", ["wifi", "shared_pool", "restaurant"], [("Courtyard Queen", 2, 4800, []), ("Family Loft", 4, 8500, ["family_suite"]), ("Plunge Pool Villa", 3, 15000, ["private_pool", "villa"])]),
    ("lagoon", "Lagoon House", "Palolem, South Goa", "Slow mornings and spacious suites near the southern shore.", ["wifi", "beach_access", "parking"], [("Palm Studio", 2, 5200, ["kitchenette"]), ("Lagoon Family Suite", 6, 10500, ["family_suite", "kitchenette"]), ("Pool Residence", 5, 21000, ["private_pool", "villa", "kitchenette"])])]

def seed(db):
    for slug, name, location, description, amenities, rooms in HOTELS:
        pid = sid(slug)
        if db.get(Property, pid): continue
        db.add(Property(id=pid, name=name + " · Fictional", location=location, description=description, amenities=amenities, policies={"cancellation": "Free cancellation until 7 days before arrival; thereafter one night's base rate is charged.", "check_in": "Check-in from 14:00; checkout by 11:00.", "pets": "Pets are not permitted.", "children": "Children count toward room capacity. No extra beds are available.", "breakfast": "Breakfast is an optional paid add-on.", "pool_heating": None}))
        db.flush()
        db.add(PricingPolicy(id=sid(slug+"policy"), property_id=pid))
        db.add(AddOn(id=sid(slug+"breakfast"), property_id=pid, name="Breakfast", price_minor=65000, basis="guest-night"))
        db.add(AddOn(id=sid(slug+"transfer"), property_id=pid, name="Airport transfer", price_minor=180000, basis="stay"))
        for i, (rname, cap, price, extras) in enumerate(rooms):
            rid = sid(slug + str(i))
            db.add(RoomType(id=rid, property_id=pid, name=rname, description=f"{rname} with space for up to {cap} guests. Fictional inventory.", capacity=cap, nightly_minor=price*100, amenities=amenities+extras))
            db.flush()
            db.add(RoomInventory(id=sid(rid+"inv"), room_type_id=rid, units=1 if "private_pool" in extras else 4))
    db.flush()
    # Fixed dates make the seed reproducible; these records also demonstrate restrictions/reservations.
    if not db.get(Reservation, sid("reservation")):
        db.add(Reservation(id=sid("reservation"), room_type_id=sid("tide2"), check_in=date(2026,12,24), check_out=date(2026,12,27), units=1))
        db.add(RoomAvailability(id=sid("closure"), room_type_id=sid("casa2"), night=date(2026,12,31), blocked_units=0, closed=True))

if __name__ == "__main__":
    with SessionLocal.begin() as db: seed(db)
    print("Seeded 3 fictional properties and 9 room types.")
