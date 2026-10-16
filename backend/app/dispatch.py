"""Allowlisted LLM tool adapter. Identity, money, permissions and mutations stay server-owned."""
from copy import deepcopy
from decimal import Decimal
from sqlalchemy import select
from . import models as m,schemas as s
from .agent_schemas import RecommendationReference,NegotiationProposal,StatePatch
from .tools import BusinessError,money,fingerprint,nights
from .db import now
from .itinerary_schemas import BuildInput,ItineraryPreferences,ItineraryResult

TOOL_DESCRIPTIONS={
    "plan_itinerary":"Create or revise a saved fictional Goa day-by-day plan from duration, region, interests, exclusions, pace and family suitability. It does not reserve activities or change a hotel booking.",
    "search_properties":"Search current hard requirements and return available rooms with full verified quotes.",
    "select_room":"Select a known recommendation and validate its quote/availability, without a hold.",
    "check_availability":"Check each stay night for a known room.",
    "get_room_details":"Read recorded capacity, amenities and description for a known room.",
    "calculate_price":"Reprice a referenced room against current requirements and tax.",
    "get_policy":"Read a property policy, preserving unknown values.",
    "evaluate_discount":"Preview an interpreted concession using configured policy.",
    "create_negotiation_offer":"Persist a policy-validated offer; never directly approve manager-only discounts.",
    "create_escalation_flag":"Record one classified review request with an application-owned reason code.",
    "request_human_handoff":"Persist a handoff for one classified review request.",
    "cancel_booking_hold":"Cancel the current session’s temporary hold after an explicit cancellation request; release inventory without refunds or external reservation changes.",
    "create_booking_hold":"Create a temporary hold only for a previously presented, explicitly confirmed quote.",
}

class Dispatcher:
    def __init__(self,db,state,tools,key):
        self.db,self.state,self.tools,self.key=db,state,tools,key
        self.previous=state.model_copy(deep=True)
        self.interpretation=None
        self.round=0
        self.executed=[]
        self.reviewed={}
        self.facts=[]
        self.quote_changed=False

    def resolve(self,reference):
        if reference.source=="recommendation":
            current=self.state.latest_recommendations or self.state.recommendation_references
            prior=self.previous.latest_recommendations or self.previous.recommendation_references
            cards=current if self.round>0 or not prior else prior
            index=reference.index-1
            if index>=len(cards):raise BusinessError("That option is not available. Please choose a current recommendation.")
            return deepcopy(cards[index])
        rid=self.state.selected_room_type_id or self.previous.selected_room_type_id
        if not rid:raise BusinessError("Please select a room first so I can use a verified quote.")
        room=self.tools.room(rid);prop=self.db.get(m.Property,room.property_id)
        return {"room_type_id":room.id,"property_id":prop.id,"room_name":room.name,"property_name":prop.name,"quote":self.state.quote or self.previous.quote}

    def apply_addons(self,interpretation,new):
        if not interpretation.add_on_changes:return new
        target=self.resolve(interpretation.reference or RecommendationReference())
        ids=set(new.add_on_ids)
        for change in interpretation.add_on_changes:
            name={"breakfast":"Breakfast","airport_transfer":"Airport transfer"}[change.name]
            addon=self.db.scalar(select(m.AddOn).where(m.AddOn.property_id==target['property_id'],m.AddOn.name==name))
            if not addon:raise BusinessError("That add-on is not listed at this property.")
            if change.operation=="add":ids.add(addon.id)
            else:ids.discard(addon.id)
        return new.model_copy(update={"add_on_ids":sorted(ids)})

    def execute(self,call):
        if call.tool not in TOOL_DESCRIPTIONS:raise BusinessError("This action is not permitted.")
        self.executed.append(call.tool)
        handler=getattr(self,"do_"+call.tool)
        return handler(call.arguments)

    def do_search_properties(self,args):
        req=self.state.booking_requirements
        missing=[label for field,label in [("destination","destination"),("check_in","arrival date"),("check_out","departure date"),("adults","adult count")] if getattr(req,field) is None]
        if missing:raise BusinessError("To check inventory, please share your "+", ".join(missing)+".")
        result=self.tools.run("search_properties",s.SearchInput(requirements=req))
        self.state.latest_recommendations=result['recommendations']
        self.state.recommendation_references=result['recommendations']
        self.state.pending_confirmation=False
        self.state.next_action="select_room" if result['recommendations'] else "adjust_requirements"
        return result

    def check_hard_constraints(self,room,quote=None):
        req=self.state.booking_requirements
        nights(req)
        prop=self.db.get(m.Property,room.property_id)
        if req.destination and req.destination.casefold() not in prop.location.casefold():raise BusinessError("This property does not match your current destination. Please search again.")
        if room.capacity<req.adults+req.children:raise BusinessError("Guest count exceeds this room’s capacity.")
        if not set(req.required_amenities).issubset(room.amenities):raise BusinessError("This room does not meet your required amenities. Please choose another option.")
        if req.room_preferences and not all(p.lower() in (room.name+' '+' '.join(room.amenities)).lower() for p in req.room_preferences):raise BusinessError("This room does not match your room requirements.")
        if quote and req.budget_amount:
            total=quote['total_minor']
            amount=total if req.budget_basis=='stay' else (total+quote['nights']-1)//quote['nights']
            if amount>req.budget_amount:raise BusinessError("This quote exceeds your current all-in budget. Please clarify whether you want to change that budget.")

    def select(self,reference,reprice=False):
        target=self.resolve(reference);req=self.state.booking_requirements;room=self.tools.room(target['room_type_id'])
        self.check_hard_constraints(room)
        available=self.tools.run('check_availability',s.AvailabilityInput(room_type_id=room.id,requirements=req))
        if not available['available']:raise BusinessError("This room is no longer available. Please search for another option.")
        q=self.db.get(m.Quote,target['quote']['id']) if target.get('quote') else None
        # Repricing is explicit when requirements changed or calculate_price was proposed.
        if reprice or not q or q.fingerprint!=fingerprint(req) or q.invalidated:
            quote=self.tools.run('calculate_price',s.PriceInput(room_type_id=room.id,requirements=req,session_id=self.state.session_id))
            self.quote_changed=True
        else:
            self.tools.fresh_quote(q.id)
            quote=q.breakdown|{'id':q.id,'expires_at':q.expires_at.isoformat()}
        self.check_hard_constraints(room,quote)
        if self.state.latest_quote_id!=quote['id']:self.state.negotiation_state={}
        self.state.selected_room_type_id=room.id;self.state.selected_property_id=room.property_id
        self.state.latest_quote_id=quote['id'];self.state.quote=quote
        self.state.pending_confirmation=True;self.state.next_action='confirm_hold'
        self.tools.run('get_room_details',s.RoomInput(room_type_id=room.id))
        return {'selected_room':room.name,'quote':quote}

    def do_select_room(self,args):return self.select(args.reference)
    def do_calculate_price(self,args):return self.select(args.reference,reprice=True)
    def do_check_availability(self,args):
        target=self.resolve(args.reference)
        return self.tools.run('check_availability',s.AvailabilityInput(room_type_id=target['room_type_id'],requirements=self.state.booking_requirements))
    def do_get_room_details(self,args):
        target=self.resolve(args.reference)
        return self.tools.run('get_room_details',s.RoomInput(room_type_id=target['room_type_id']))
    def do_get_policy(self,args):
        target=self.resolve(args.reference)
        return self.tools.run('get_policy',s.PolicyInput(property_id=target['property_id'],topic=args.topic))

    def proposal(self):
        if not self.state.latest_quote_id:raise BusinessError("Please select a room first so I can negotiate a verified quote.")
        q,_=self.tools.fresh_quote(self.state.latest_quote_id)
        p=self.interpretation.negotiation
        if p is None:raise BusinessError("Please clarify the concession you would like me to evaluate.")
        if p.kind=='complimentary_add_on':
            self.flag('unsupported_request','unsupported_concession')
            raise BusinessError("I can’t approve a free add-on. I can price a paid option or record your request for review.")
        if p.kind=='amount' and p.basis is None:raise BusinessError("Is that price per night, including tax, or for the entire stay? Please repeat the amount with its basis.")
        amount=p.amount_minor
        if p.kind=='percentage':amount=max(1,money(Decimal(q.total_minor)*(10000-p.percentage_bps)/10000))
        if not self.tools.run('check_availability',s.AvailabilityInput(room_type_id=q.room_type_id,requirements=self.state.booking_requirements))['available']:
            raise BusinessError("The room became unavailable. Please search again before negotiating.")
        return s.DiscountInput(quote_id=q.id,proposed_amount=amount,basis=p.basis or 'stay')

    def do_evaluate_discount(self,args):return self.tools.run('evaluate_discount',self.proposal())
    def do_create_negotiation_offer(self,args):
        p=self.proposal()
        result=self.tools.run('create_negotiation_offer',s.OfferInput(**p.model_dump(),session_id=self.state.session_id,idempotency_key=self.key+':offer'))
        self.state.negotiation_state=result
        self.state.pending_confirmation=result['status'] in ('accepted','countered')
        self.state.next_action='await_manager' if result['status']=='pending_approval' else 'confirm_offer'
        self.quote_changed=True  # An offer changes what the guest is asked to confirm.
        if result['status']=='pending_approval':self.flag('pricing_approval_required','discount_requires_review')
        if result.get('attempts',0)>=3:self.flag('repeated_negotiation','three_price_requests',severity='info')
        return result

    def flag(self,category,reason,severity='warning'):
        if category in self.reviewed:return self.reviewed[category]
        result=self.tools.run('create_escalation_flag',s.FlagInput(session_id=self.state.session_id,category=category,severity=severity,reason_code=reason,context={'quote_id':self.state.latest_quote_id},idempotency_key=self.key+':'+category))
        self.reviewed[category]=result
        self.state.escalation_status='pending_review'
        if category!='possible_prompt_injection':self.tools.run('request_human_handoff',s.HandoffInput(session_id=self.state.session_id,flag_id=result['id']))
        return result

    def classified_flag(self,index):
        if index>len(self.interpretation.escalations):raise BusinessError("The requested review classification is missing.")
        signal=self.interpretation.escalations[index-1]
        category='guest_complaint' if signal.category=='repeated_unresolved_issue' else signal.category
        return self.flag(category,'semantic_'+signal.category,signal.severity)
    def do_create_escalation_flag(self,args):return self.classified_flag(args.classification_index)
    def do_request_human_handoff(self,args):return self.classified_flag(args.classification_index)

    def enforce_escalations(self):
        for i in range(len(self.interpretation.escalations)):self.classified_flag(i+1)
        mapping={'human':'requested_human','complaint':'guest_complaint','exception':'policy_exception','injection':'possible_prompt_injection'}
        for intent in [self.interpretation.primary_intent,*self.interpretation.secondary_intents]:
            if intent in mapping:self.flag(mapping[intent],'semantic_'+intent)

    def do_create_booking_hold(self,args):
        # A proposal cannot manufacture confirmation, select and book new terms at once,
        # or reuse an affirmation to a different pending clarification.
        previous=self.previous
        if not self.interpretation.explicit_confirmation or self.interpretation.ambiguities or self.quote_changed or not previous.pending_confirmation or previous.latest_quote_id!=self.state.latest_quote_id or not self.state.latest_quote_id:
            raise BusinessError("Please select and review a current room quote before confirming its temporary hold." if not previous.latest_quote_id else "A temporary hold requires separate confirmation of the latest displayed terms. No new hold was created.")
        hold=self.tools.run('create_booking_hold',s.HoldInput(session_id=self.state.session_id,quote_id=self.state.latest_quote_id,requirements=self.state.booking_requirements,confirmed=True,idempotency_key=self.key))
        self.state.active_booking_hold_id=hold['id'];self.state.hold=hold
        self.state.pending_confirmation=False;self.state.next_action='hold_active'
        return hold

    def do_cancel_booking_hold(self,args):
        if not self.interpretation.explicit_cancellation or self.interpretation.ambiguities:
            raise BusinessError("Please explicitly confirm which temporary hold you want to cancel.")
        hold_id=self.previous.active_booking_hold_id or (self.previous.hold or {}).get('id')
        if not hold_id:raise BusinessError("There is no temporary hold in this session to cancel. For an external reservation, staff must assist you.")
        result=self.tools.run('cancel_booking_hold',s.CancelHoldInput(hold_id=hold_id,confirmed=True))
        self.state.hold=result
        self.state.active_booking_hold_id=None
        self.state.pending_confirmation=False
        self.state.negotiation_state={}
        self.state.quote=None;self.state.latest_quote_id=None
        self.state.latest_recommendations=[]
        self.state.next_action='hold_cancelled'
        return result

    def do_plan_itinerary(self,args):
        current=self.state.itinerary_preferences.model_dump()
        current.update(args.model_dump(exclude_none=True))
        req=self.state.booking_requirements
        destination=(req.destination or 'Goa').casefold()
        if not any(area in destination for area in ('goa','candolim','anjuna','palolem')):
            raise BusinessError('The fictional itinerary catalog covers Goa only. Please choose Goa for this demo.')
        if current['days'] is None and req.check_in and req.check_out:
            current['days']=(req.check_out-req.check_in).days
        if current['days'] is None:raise BusinessError('How many days would you like your Goa itinerary to cover?')
        if not 1<=current['days']<=7:raise BusinessError('The demo planner supports one to seven days. Please choose a duration within that range.')
        if req.check_in and req.check_out and current['days']>(req.check_out-req.check_in).days:
            raise BusinessError('The itinerary is longer than your current stay. Please shorten the plan or explicitly extend the stay.')
        if current['region'] is None:
            prop=self.db.get(m.Property,self.state.selected_property_id) if self.state.selected_property_id else None
            current['region']='south_goa' if prop and 'south goa' in prop.location.casefold() else 'north_goa'
        if req.children:current['family_friendly']=True
        preferences=ItineraryPreferences.model_validate(current)
        result=self.tools.run('plan_itinerary',BuildInput(preferences=preferences,start_date=req.check_in))
        self.state.itinerary_preferences=preferences
        self.state.itinerary=ItineraryResult.model_validate(result)
        self.state.next_action='review_itinerary'
        return result
