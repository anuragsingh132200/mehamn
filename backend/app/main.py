import hashlib
import hmac
import json
import logging
import secrets
import time
from contextlib import asynccontextmanager, ExitStack
from uuid import uuid4
from fastapi import FastAPI, Depends, Header, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy import select, func, text
from sqlalchemy.exc import SQLAlchemyError
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool
from .config import settings
from .db import SessionLocal, engine, get_db, now
from . import schemas as s, models as m
from .orchestrator import Receptionist
from .extraction import ModelUnavailable
from .tools import Tools, BusinessError

logger=logging.getLogger("mira")
logging.basicConfig(level=logging.INFO,format="%(message)s")

@asynccontextmanager
async def lifespan(app):
    with ExitStack() as stack:
        app.state.checkpointer=None
        if settings.database_url.startswith("postgresql"):
            uri=settings.database_url.replace("postgresql+psycopg://","postgresql://")
            pool=stack.enter_context(ConnectionPool(uri,min_size=1,max_size=10,kwargs={"autocommit":True,"prepare_threshold":0}))
            saver=PostgresSaver(pool)
            # Tables are initialized by the migration/start script, never by API workers.
            app.state.checkpointer=saver
        yield
        engine.dispose()

app=FastAPI(title="Mira · Fictional hotel receptionist",lifespan=lifespan,responses={code:{"model":s.ErrorOutput} for code in (403,404,409,422,429,500,503)})
app.add_middleware(CORSMiddleware,allow_origins=[settings.cors_origin],allow_methods=["GET","POST"],allow_headers=["Authorization","Content-Type","X-Admin-Token","X-Request-ID"])

@app.middleware("http")
async def request_context(request:Request,call_next):
    # Never trust or log user-supplied request IDs or message bodies.
    request.state.request_id=str(uuid4())
    tick=time.monotonic()
    response=await call_next(request)
    response.headers["X-Request-ID"]=request.state.request_id
    logger.info(json.dumps({"event":"request","request_id":request.state.request_id,"method":request.method,"route":request.scope.get("route").path if request.scope.get("route") else "unknown","status":response.status_code,"duration_ms":int((time.monotonic()-tick)*1000)}))
    return response

@app.exception_handler(RequestValidationError)
async def validation_error(request,exc):
    fields=sorted({".".join(str(v) for v in e["loc"]) for e in exc.errors()})
    return JSONResponse(status_code=422,content={"error":"Invalid request fields: "+", ".join(fields),"request_id":request.state.request_id})

@app.exception_handler(HTTPException)
async def http_error(request,exc):
    return JSONResponse(status_code=exc.status_code,content={"error":str(exc.detail),"request_id":getattr(request.state,"request_id","")},headers=exc.headers)

@app.exception_handler(SQLAlchemyError)
async def database_error(request,exc):
    logger.error(json.dumps({"event":"database_failure","request_id":request.state.request_id,"type":type(exc).__name__}))
    return JSONResponse(status_code=503,content={"error":"Database unavailable. No booking is confirmed; retry with the same idempotency key.","request_id":request.state.request_id})

@app.exception_handler(ModelUnavailable)
async def model_error(request,exc):
    return JSONResponse(status_code=503,content={"error":str(exc),"request_id":request.state.request_id})

@app.exception_handler(BusinessError)
async def business_error(request,exc):
    return JSONResponse(status_code=409,content={"error":str(exc),"request_id":request.state.request_id})

@app.exception_handler(Exception)
async def unexpected_error(request,exc):
    logger.error(json.dumps({"event":"unexpected_failure","request_id":request.state.request_id,"type":type(exc).__name__}))
    return JSONResponse(status_code=500,content={"error":"The request could not be completed. Retry with the same idempotency key.","request_id":request.state.request_id})

def authorize(db,sid,authorization,lock=False):
    query=select(m.Conversation).where(m.Conversation.id==sid)
    if lock: query=query.with_for_update()
    c=db.scalar(query)
    token=(authorization or "").removeprefix("Bearer ")
    if not c or not hmac.compare_digest(c.token_hash,hashlib.sha256(token.encode()).hexdigest()):
        raise HTTPException(404,"Session not found or access denied.")
    return c

def admin(x_admin_token:str=Header(default="")):
    if not settings.admin_token or not hmac.compare_digest(x_admin_token,settings.admin_token):
        raise HTTPException(403,"Separate demo admin authorization is required.")

def guest_state(db,c):
    state=s.AgentState.model_validate(c.state)
    if state.hold and state.hold.get("status")!="cancelled" and state.hold["expires_at"]<=now().isoformat():
        state.hold["status"]="expired"; state.active_booking_hold_id=None
    if state.latest_quote_id:
        q=db.get(m.Quote,state.latest_quote_id)
        if q and (q.expires_at<=now() or q.invalidated): state.pending_confirmation=False
        o=db.scalar(select(m.NegotiationOffer).where(m.NegotiationOffer.quote_id==state.latest_quote_id).order_by(m.NegotiationOffer.created_at.desc(),m.NegotiationOffer.id.desc()))
        if o:
            previous_status=state.negotiation_state.get("status")
            state.negotiation_state=Tools.offer_result(o)
            if previous_status=="pending_approval" and o.status=="accepted" and o.expires_at>now() and q and not q.invalidated and not state.active_booking_hold_id: state.pending_confirmation=True
    return state

@app.post("/api/sessions",response_model=s.SessionCreated,status_code=201)
def create_session(db=Depends(get_db)):
    token=secrets.token_urlsafe(32)
    c=m.Conversation(token_hash=hashlib.sha256(token.encode()).hexdigest())
    db.add(c); db.flush()
    c.state=s.AgentState(session_id=c.id).model_dump(mode="json")
    db.commit()
    return {"session_id":c.id,"token":token}

@app.get("/api/sessions/{session_id}",response_model=s.SessionOutput)
def get_session(session_id:str,authorization:str=Header(default=""),limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),db=Depends(get_db)):
    c=authorize(db,session_id,authorization)
    messages=list(db.scalars(select(m.Message).where(m.Message.session_id==session_id).order_by(m.Message.created_at.desc(),m.Message.id.desc()).offset(offset).limit(limit)))
    return {"state":guest_state(db,c),"messages":[{"id":x.id,"role":x.role,"content":x.content} for x in reversed(messages)],"llm_mode":settings.llm_mode}

@app.post("/api/chat",response_model=s.ChatOutput)
def chat(body:s.ChatInput,request:Request,authorization:str=Header(default=""),db=Depends(get_db)):
    # This row lock serializes messages and admin approvals across processes/workers.
    c=authorize(db,body.session_id,authorization,lock=True)
    old=db.scalar(select(m.ChatRequest).where(m.ChatRequest.session_id==c.id,m.ChatRequest.key==body.idempotency_key))
    digest=hashlib.sha256(body.message.encode()).hexdigest()
    if old:
        if old.payload_hash!=digest: raise HTTPException(409,"Idempotency key already used for a different message.")
        return old.response
    if body.expected_version is not None and body.expected_version!=c.version:
        raise HTTPException(409,"State changed. Refresh this session before sending again.")
    from datetime import timedelta
    recent=db.scalar(select(func.count()).select_from(m.ChatRequest).where(m.ChatRequest.session_id==c.id,m.ChatRequest.created_at>now()-timedelta(minutes=1)))
    if recent>=settings.rate_limit_per_minute: raise HTTPException(429,"Too many messages. Please wait a minute.",headers={"Retry-After":"60"})
    state=guest_state(db,c)
    receptionist=Receptionist(db,state,body.message,request.state.request_id,body.idempotency_key,getattr(request.app.state,"checkpointer",None))
    try:
        # A failed planning pass must not leave quotes/offers/holds partially committed.
        with db.begin_nested():
            response,state=receptionist.invoke()
    except ModelUnavailable:
        # Preserve a durable operational review event without advancing authoritative state.
        db.add(m.ToolLog(session_id=c.id,correlation_id=request.state.request_id,tool_name="llm_turn_failure",arguments={},duration_ms=0,success=False,summary=receptionist.gateway.usage()))
        tools=Tools(db,c.id,request.state.request_id)
        result=tools.run("create_escalation_flag",s.FlagInput(session_id=c.id,category="tool_failure",reason_code="language_service_unavailable",idempotency_key=body.idempotency_key+":llm"))
        tools.run("request_human_handoff",s.HandoffInput(session_id=c.id,flag_id=result["id"]))
        db.commit()
        raise
    c.state=state.model_dump(mode="json"); c.version=state.state_version
    # Explicit microsecond ordering prevents unstable replay ordering in fast requests.
    from datetime import timedelta
    stamp=now()
    db.add_all([m.Message(session_id=c.id,role="user",content=body.message,created_at=stamp),m.Message(session_id=c.id,role="assistant",content=response,created_at=stamp+timedelta(microseconds=1))])
    out=s.ChatOutput(response=response,state=state,request_id=request.state.request_id).model_dump(mode="json")
    db.add(m.ChatRequest(session_id=c.id,key=body.idempotency_key,payload_hash=digest,response=out))
    db.commit()
    return out

class PropertyView(s.BaseModel):
    id:str
    name:str
    location:str
    description:str
    amenities:list[str]
    fictional:bool=True

@app.get("/api/properties",response_model=list[PropertyView])
def properties(db=Depends(get_db)):
    return [PropertyView(**{k:getattr(p,k) for k in ("id","name","location","description","amenities")}) for p in db.scalars(select(m.Property).order_by(m.Property.name))]

@app.get("/api/properties/{property_id}",response_model=s.PropertyDetails)
def property_details(property_id:str,db=Depends(get_db)):
    p=db.get(m.Property,property_id)
    if not p: raise HTTPException(404,"Property not found.")
    return {"id":p.id,"name":p.name,"location":p.location,"policies":p.policies,"fictional":True,"rooms":[{k:getattr(r,k) for k in ("id","name","capacity","nightly_minor","amenities","description")} for r in db.scalars(select(m.RoomType).where(m.RoomType.property_id==p.id))],"add_ons":[{k:getattr(a,k) for k in ("id","name","price_minor","basis")} for a in db.scalars(select(m.AddOn).where(m.AddOn.property_id==p.id))]}

@app.get("/api/sessions/{session_id}/traces",response_model=list[s.TraceOutput])
def traces(session_id:str,authorization:str=Header(default=""),limit:int=Query(30,ge=1,le=100),offset:int=Query(0,ge=0),db=Depends(get_db)):
    authorize(db,session_id,authorization)
    # Sensitive flag reasons and mutation arguments are admin-only.
    logs=list(db.scalars(select(m.ToolLog).where(m.ToolLog.session_id==session_id).order_by(m.ToolLog.started_at.desc()).offset(offset).limit(limit)))
    return [{"id":x.id,"tool_name":x.tool_name,"arguments":{} if x.tool_name in ("create_escalation_flag","request_human_handoff") else x.arguments,"started_at":x.started_at.isoformat(),"duration_ms":x.duration_ms,"success":x.success,"summary":{} if x.tool_name in ("create_escalation_flag","request_human_handoff") else x.summary,"correlation_id":x.correlation_id} for x in logs]

@app.get("/api/sessions/{session_id}/offers",response_model=list[s.OfferOutput])
def offers(session_id:str,authorization:str=Header(default=""),limit:int=Query(30,ge=1,le=100),offset:int=Query(0,ge=0),db=Depends(get_db)):
    authorize(db,session_id,authorization)
    return [Tools.offer_result(o) for o in db.scalars(select(m.NegotiationOffer).where(m.NegotiationOffer.session_id==session_id).order_by(m.NegotiationOffer.created_at.desc()).offset(offset).limit(limit))]

@app.get("/api/sessions/{session_id}/flags",response_model=list[s.FlagOutput])
def flags(session_id:str,authorization:str=Header(default=""),limit:int=Query(30,ge=1,le=100),offset:int=Query(0,ge=0),db=Depends(get_db)):
    authorize(db,session_id,authorization)
    return [{"id":f.id,"status":f.status,"created_at":f.created_at.isoformat(),"message":"Recorded for review"} for f in db.scalars(select(m.EscalationFlag).where(m.EscalationFlag.session_id==session_id).order_by(m.EscalationFlag.created_at.desc()).offset(offset).limit(limit))]

@app.get("/api/admin/escalations",dependencies=[Depends(admin)],response_model=s.AdminQueue)
def admin_escalations(limit:int=Query(30,ge=1,le=100),offset:int=Query(0,ge=0),db=Depends(get_db)):
    flags=list(db.scalars(select(m.EscalationFlag).where(m.EscalationFlag.status=="open").order_by(m.EscalationFlag.created_at).offset(offset).limit(limit)))
    offers=list(db.scalars(select(m.NegotiationOffer).where(m.NegotiationOffer.status=="pending_approval",m.NegotiationOffer.expires_at>now()).order_by(m.NegotiationOffer.created_at).offset(offset).limit(limit)))
    return {"flags":[{k:getattr(f,k) for k in ("id","session_id","category","severity","status","reason_code","context")} for f in flags],"offers":[Tools.offer_result(o)|{"session_id":o.session_id} for o in offers]}

@app.post("/api/admin/escalations/{flag_id}/resolve",dependencies=[Depends(admin)],response_model=s.StatusOutput)
def resolve(flag_id:str,request:Request,db=Depends(get_db)):
    flag=db.get(m.EscalationFlag,flag_id)
    if not flag: raise HTTPException(404,"Flag not found.")
    db.scalar(select(m.Conversation).where(m.Conversation.id==flag.session_id).with_for_update())
    result=Tools(db,flag.session_id,request.state.request_id).run("resolve_escalation_flag",s.ResolveInput(flag_id=flag_id))
    db.commit(); return result

def decide_offer(offer_id,approved,db,request):
    # Read session ID, lock parent, then refresh offer to use the same order as chat.
    initial=db.get(m.NegotiationOffer,offer_id)
    if not initial: raise HTTPException(404,"Offer not found.")
    db.scalar(select(m.Conversation).where(m.Conversation.id==initial.session_id).with_for_update())
    db.refresh(initial)
    offer=initial
    target="accepted" if approved else "rejected"
    if offer.status==target: return Tools.offer_result(offer)
    if offer.status!="pending_approval": raise HTTPException(409,"Offer is no longer pending review.")
    tools=Tools(db,offer.session_id,request.state.request_id)
    q,policy=tools.fresh_quote(offer.quote_id)
    if offer.discount_bps>policy.manager_bps or offer.policy_version!=policy.version: raise HTTPException(409,"Offer exceeds current review policy. Reprice it.")
    offer.status=target
    offer.approved_amount=offer.proposed_amount if approved else None
    for f in db.scalars(select(m.EscalationFlag).where(m.EscalationFlag.session_id==offer.session_id,m.EscalationFlag.category=="pricing_approval_required",m.EscalationFlag.status=="open")):
        if f.context.get("quote_id")==q.id: tools.run("resolve_escalation_flag",s.ResolveInput(flag_id=f.id))
    db.add(m.ToolLog(session_id=offer.session_id,correlation_id=request.state.request_id,tool_name="manager_approve" if approved else "manager_reject",arguments={"offer_id":offer.id},duration_ms=0,success=True,summary={"status":target}))
    db.commit()
    return Tools.offer_result(offer)

@app.post("/api/admin/offers/{offer_id}/approve",dependencies=[Depends(admin)],response_model=s.OfferOutput)
def approve(offer_id:str,request:Request,db=Depends(get_db)): return decide_offer(offer_id,True,db,request)
@app.post("/api/admin/offers/{offer_id}/reject",dependencies=[Depends(admin)],response_model=s.OfferOutput)
def reject(offer_id:str,request:Request,db=Depends(get_db)): return decide_offer(offer_id,False,db,request)

@app.get("/health",response_model=s.HealthOutput)
def health(db=Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status":"ok","fictional":True,"llm_mode":settings.llm_mode,"model_configured":bool(settings.openai_api_key)}
