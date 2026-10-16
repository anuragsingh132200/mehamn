"""Bounded OpenAI access with structured validation and metadata-only observability."""
import json
import logging
import time
from openai import OpenAI, pydantic_function_tool, AuthenticationError, PermissionDeniedError
from pydantic import ValidationError
from .config import settings
from .db import now
from .models import ToolLog
from .prompts import PROMPT_VERSION
from .agent_schemas import AgentDecision

log = logging.getLogger("mira.model")
class ModelUnavailable(RuntimeError): pass
class ModelOutputInvalid(ModelUnavailable): pass

class ModelGateway:
    def __init__(self, db=None, session_id=None, correlation_id=None):
        self.db, self.session_id, self.correlation_id = db, session_id, correlation_id
        self.calls=0
        self.input_tokens=0
        self.output_tokens=0
        self.deadline=time.monotonic()+settings.agent_timeout_seconds

    def _request(self, schema, context, system, purpose):
        timeout=max(1,min(settings.model_timeout_seconds,self.deadline-time.monotonic()))
        with OpenAI(api_key=settings.openai_api_key,timeout=timeout,max_retries=0) as client:
            kwargs={"model":settings.openai_model,"input":[{"role":"system","content":system},{"role":"user","content":json.dumps(context,ensure_ascii=False,default=str)}],"max_output_tokens":settings.model_max_output_tokens,"store":False}
            if schema is AgentDecision:
                # The native function submits a typed, ordered batch. Only the server
                # executes its allowlisted constituent tools after validation.
                tool=pydantic_function_tool(AgentDecision,name="propose_receptionist_turn",description="Submit interpreted guest intents, explicit state patches, and an ordered batch of permitted receptionist tool requests. This proposes actions; the application authorizes them.")
                # pydantic_function_tool uses the chat format; Responses accepts flat functions.
                f=tool["function"]
                kwargs.update(tools=[{"type":"function",**f}],tool_choice={"type":"function","name":f["name"]},parallel_tool_calls=False)
                # Retain the SDK's Pydantic tool marker for parsed_arguments support.
                from openai.lib._tools import ResponsesPydanticFunctionTool
                kwargs["tools"]=[ResponsesPydanticFunctionTool(kwargs["tools"][0],model=AgentDecision)]
                response=client.responses.parse(**kwargs)
                calls=[item for item in response.output if item.type=="function_call"]
                if len(calls)!=1 or calls[0].name!="propose_receptionist_turn": raise ModelOutputInvalid("Invalid planner tool envelope")
                parsed=calls[0].parsed_arguments
            else:
                response=client.responses.parse(**kwargs,text_format=schema)
                parsed=response.output_parsed
            if parsed is None: raise ModelOutputInvalid("Model did not supply a validated structured output")
            usage={"input_tokens":getattr(response.usage,"input_tokens",0),"output_tokens":getattr(response.usage,"output_tokens",0)}
            return parsed,usage

    def parse(self,schema,context,system,purpose):
        if not settings.openai_api_key:
            raise ModelUnavailable("OPENAI_API_KEY is not configured. Mira requires the language service; please configure the server and retry.")
        for attempt in range(2):
            if self.calls>=settings.max_model_calls or time.monotonic()>=self.deadline:
                raise ModelUnavailable("The assistant reached its execution limit. Please retry your request.")
            self.calls+=1
            tick=time.monotonic();started=now();success=False;usage={}
            try:
                parsed,usage=self._request(schema,context,system,purpose)
                self.input_tokens+=usage.get("input_tokens",0)
                self.output_tokens+=usage.get("output_tokens",0)
                output=schema.model_validate(parsed.model_dump() if hasattr(parsed,"model_dump") else parsed)
                success=True
                return output
            except (ValidationError,ModelOutputInvalid) as exc:
                log.warning(json.dumps({"event":"model_validation_failure","purpose":purpose,"request_id":self.correlation_id,"attempt":attempt+1,"type":type(exc).__name__}))
                if attempt: raise ModelOutputInvalid("I couldn’t safely interpret the model’s response. Please clarify your request and try again.") from exc
                context={**context,"validation_feedback":"Your previous structured output was invalid. Respect all field types, tool schemas, and cross-field requirements. No previous proposal was executed."}
            except (AuthenticationError,PermissionDeniedError) as exc:
                log.warning(json.dumps({"event":"model_authentication_failure","purpose":purpose,"request_id":self.correlation_id,"type":type(exc).__name__,"status":exc.status_code}))
                raise ModelUnavailable("The language service credentials were rejected. Please ask the administrator to update the server configuration.") from exc
            except ModelUnavailable: raise
            except Exception as exc:
                log.warning(json.dumps({"event":"model_call_failure","purpose":purpose,"request_id":self.correlation_id,"attempt":attempt+1,"type":type(exc).__name__}))
                if attempt: raise ModelUnavailable("The language service is unavailable. Your previous booking state is preserved; please retry.") from exc
            finally:
                if self.db is not None:
                    self.db.add(ToolLog(session_id=self.session_id,correlation_id=self.correlation_id,tool_name="llm_"+purpose,arguments={"model":settings.openai_model,"prompt_version":PROMPT_VERSION,"attempt":attempt+1},started_at=started,duration_ms=int((time.monotonic()-tick)*1000),success=success,summary=usage|{"status":"ok" if success else "unavailable"}))

    def usage(self):
        return {"calls":self.calls,"input_tokens":self.input_tokens,"output_tokens":self.output_tokens,"model":settings.openai_model,"prompt_version":PROMPT_VERSION}
