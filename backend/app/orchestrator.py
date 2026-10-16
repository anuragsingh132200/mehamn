"""Single bounded LangGraph: model proposals, guarded tools, grounded response."""
from typing import TypedDict
from pydantic import ValidationError
from sqlalchemy import select
from langgraph.graph import StateGraph,START,END
from . import schemas as s,models as m
from .agent_schemas import AgentDecision
from .extraction import extract
from .model_gateway import ModelGateway,ModelUnavailable,ModelOutputInvalid
from .tools import Tools,BusinessError,ToolUnavailable,nights
from .tool_results import public_results,validate_result
from .dispatch import Dispatcher
from .state_updates import merge_requirements,invalidate_quotes
from .response import generate_response,safe_receipt,ResponseGroundingError
from .config import settings
from .db import now

class GraphSnapshot(TypedDict,total=False):
    state:dict
    node:str
    response:str
    planning_round:int

class Receptionist:
    NODES=['receive_message','extract_intent','merge_state','validate_state','route_intent','execute_tools','validate_tool_results','evaluate_escalation','generate_response','persist_trace']
    def __init__(self,db,state,message,request_id,key,checkpointer=None):
        self.db,self.state,self.message=db,state,message
        self.tools=Tools(db,state.session_id,request_id)
        self.gateway=ModelGateway(db,state.session_id,request_id)
        self.dispatch=Dispatcher(db,state,self.tools,key)
        self.decision=AgentDecision()
        self.response='';self.error=None;self.round=0;self.calls=0;self.history=[]
        self.executed_calls=set()
        builder=StateGraph(GraphSnapshot)
        for name in self.NODES:builder.add_node(name,self.wrap(name))
        builder.add_edge(START,'receive_message');builder.add_edge('receive_message','extract_intent')
        builder.add_edge('extract_intent','merge_state');builder.add_edge('merge_state','validate_state')
        builder.add_edge('validate_state','route_intent')
        builder.add_conditional_edges('route_intent',self.choose_route,{'tools':'execute_tools','respond':'evaluate_escalation'})
        builder.add_edge('execute_tools','validate_tool_results');builder.add_edge('validate_tool_results','evaluate_escalation')
        builder.add_conditional_edges('evaluate_escalation',self.after_tools,{'replan':'extract_intent','respond':'generate_response'})
        builder.add_edge('generate_response','persist_trace');builder.add_edge('persist_trace',END)
        self.graph=builder.compile(checkpointer=checkpointer)

    def wrap(self,name):
        def node(snapshot):
            try:
                if not self.error or name in {'evaluate_escalation','generate_response','persist_trace'}:getattr(self,name)()
            except BusinessError as exc:
                self.error=str(exc)
            except ToolUnavailable as exc:
                self.error=str(exc)
                self.dispatch.flag('tool_failure','repeated_tool_timeout')
            except ValidationError as exc:
                # Tool-result validation failures cannot become guest facts.
                raise ModelOutputInvalid('A tool returned invalid data. Your booking state is preserved; please retry.') from exc
            return {'state':self.state.model_dump(mode='json'),'node':name,'response':self.response,'planning_round':self.round}
        return node

    def invoke(self):
        self.graph.invoke({'state':self.state.model_dump(mode='json')},{'configurable':{'thread_id':self.state.session_id},'recursion_limit':30})
        return self.response,self.state

    def receive_message(self):
        rows=list(self.db.scalars(select(m.Message).where(m.Message.session_id==self.state.session_id).order_by(m.Message.created_at.desc(),m.Message.id.desc()).limit(settings.recent_message_window)))
        self.history=[{'role':row.role,'content':row.content} for row in reversed(rows)]
        self.state.messages=[];self.state.last_tool_results=[];self.state.response_degraded=False

    def extract_intent(self):
        result=extract(self.message,self.state,self.history,self.gateway,public_results(self.tools.results),self.round)
        try:self.decision=AgentDecision.model_validate(result.model_dump() if hasattr(result,'model_dump') else result)
        except ValidationError as exc:raise ModelOutputInvalid('The proposed actions were invalid. Please clarify your request.') from exc
        interpretation=self.decision.interpretation
        if self.round and (interpretation.patches or interpretation.date_operations or interpretation.add_on_changes):
            raise ModelOutputInvalid('A follow-up plan tried to change the same turn’s requirements again. Please retry.')
        self.dispatch.interpretation=interpretation
        if self.decision.referenced_quote_id and self.decision.referenced_quote_id!=self.state.latest_quote_id:
            raise BusinessError('That quote is not the active quote for this conversation. Please select a current option.')
        self.dispatch.interpretation=interpretation
        if not self.round:
            self.state.active_intent=interpretation.primary_intent
            self.state.secondary_intents=interpretation.secondary_intents
        self.dispatch.round=self.round

    def is_injection(self):
        i=self.decision.interpretation
        return 'injection' in [i.primary_intent,*i.secondary_intents] or any(x.category=='possible_prompt_injection' for x in i.escalations)

    def merge_state(self):
        if self.round or self.is_injection():return
        i=self.decision.interpretation
        # Ambiguous interpretations must not mutate booking requirements or quote state.
        if i.ambiguities:
            self.state.pending_clarification=i.clarification_question
            return
        old=self.state.booking_requirements
        new=merge_requirements(old,i.patches,i.date_operations)
        new=self.dispatch.apply_addons(i,new)
        if new!=old:
            self.state.booking_requirements=new
            invalidate_quotes(self.db,self.state)
            self.dispatch.quote_changed=True
        if i.declines_pending_action:
            self.state.pending_confirmation=False;self.state.pending_clarification=None
        self.state.pending_clarification=i.clarification_question
        if self.state.hold and self.state.hold['expires_at']<=now().isoformat():
            self.state.hold['status']='expired';self.state.active_booking_hold_id=None

    def validate_state(self):
        req=self.state.booking_requirements
        if req.check_in and req.check_out and req.adults:nights(req)
        if self.calls+len(self.decision.requested_tool_calls)>settings.max_agent_tools:
            raise BusinessError('The requested actions exceed the execution limit. Please narrow this request.')
        # Validate the entire batch's reference shapes before any requested mutation.
        for call in self.decision.requested_tool_calls:
            if hasattr(call.arguments,'reference'):
                if call.arguments.reference.source=='recommendation' or not any(c.tool=='select_room' for c in self.decision.requested_tool_calls):
                    self.dispatch.resolve(call.arguments.reference)

    def route_intent(self):
        self.state.next_action=self.decision.proposed_next_action

    def choose_route(self,snapshot):
        i=self.decision.interpretation
        if self.error or self.is_injection() or i.ambiguities or self.decision.proposed_next_action!='execute_tools':return 'respond'
        return 'tools'

    def execute_tools(self):
        for call in self.decision.requested_tool_calls:
            # Avoid repeated identical calls/mutations across adaptive planning passes.
            signature=call.model_dump_json()
            if signature in self.executed_calls:continue
            self.calls+=1
            if self.calls>settings.max_agent_tools:raise BusinessError('Tool execution limit reached. Please narrow the request.')
            self.dispatch.execute(call)
            self.executed_calls.add(signature)

    def validate_tool_results(self):
        for result in self.tools.results:validate_result(result['tool_name'],result['data'])

    def evaluate_escalation(self):
        self.dispatch.enforce_escalations()
        if self.is_injection():
            self.error='I can help with verified hotel information and your travel requests. I cannot follow instructions to bypass booking controls or disclose internal information.'

    def after_tools(self,snapshot):
        if not self.error and not self.is_injection() and not self.decision.interpretation.ambiguities and self.decision.request_followup and self.round+1<settings.max_planning_rounds and not self.state.active_booking_hold_id:
            self.round+=1
            return 'replan'
        return 'respond'

    def generate_response(self):
        if self.error:
            self.response=self.error;self.state.next_action='correct_or_refresh'
            return
        try:
            self.response,question=generate_response(self.gateway,self.message,self.state,self.history,public_results(self.tools.results),self.dispatch.reviewed)
            self.state.pending_clarification=question or self.decision.interpretation.clarification_question
        except (ModelUnavailable,ResponseGroundingError):
            # Successful tools (especially holds) must not be repeated after a prose outage.
            self.dispatch.flag('tool_failure','response_generation_failed')
            self.state.response_degraded=True
            self.response=safe_receipt(self.state,public_results(self.tools.results),self.dispatch.reviewed)

    def persist_trace(self):
        self.state.last_tool_results=[{'tool_name':x['tool_name'],'success':True} for x in self.tools.results]
        self.state.model_usage=self.gateway.usage()
        self.state.state_version+=1
