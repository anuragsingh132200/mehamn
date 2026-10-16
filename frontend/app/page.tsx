'use client';
import { useEffect, useRef, useState } from 'react';
import { ArrowUp, ArrowUpRight, Check, CheckCheck, ChevronDown, ChevronRight, CircleHelp, Clock3, Code2, Compass, Leaf, Loader2, MapPin, MessageSquare, Plus, ShieldCheck, Sparkles, Sun, Waves, X } from 'lucide-react';
import { Button } from '@/components/ui/button';

type Quote = { id:string; nights:number; nightly_minor:number; base_minor:number; tax_minor:number; total_minor:number; expires_at:string; add_ons:{name:string;amount_minor:number}[] };
type Card = { room_type_id:string; property_id:string; property_name:string; location:string; room_name:string; description:string; capacity:number; amenities:string[]; quote:Quote };
type Itinerary = {fictional:true;stale:boolean;region:string;pace:string;disclaimer:string;days:{day:number;date:string|null;note:string|null;stops:{slot:string;activity:{id:string;name:string;category:string;description:string}}[]}[]};
type State = { itinerary?:Itinerary|null; session_id:string; booking_requirements:Record<string,unknown>; active_intent:string; latest_recommendations:Card[]; latest_quote_id:string|null; quote:Quote|null; negotiation_state:{id?:string;status?:string;approved_amount?:number}; pending_confirmation:boolean; hold:{id:string;total_minor:number;expires_at:string;status:string}|null; next_action:string; state_version:number; escalation_status:string };
type Trace = { id:string; tool_name:string; duration_ms:number; success:boolean; started_at:string; arguments:unknown; summary:unknown; correlation_id:string };
type Message = { role:string;content:string;id?:string };
type Session = { session_id:string;token:string };
type AdminData = {flags:{id:string;category:string;severity:string;reason_code:string}[];offers:{id:string;status:string;proposed_amount:number}[]};
const API=process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const inr=(v:number)=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:2}).format(v/100);
const label=(v:string)=>v.replaceAll('_',' ');
const suggestions=['Plan a three-day Goa itinerary','A villa with a private pool','Something for the whole family'];

function Composer({busy,onSend}:{busy:boolean;onSend:(text:string)=>Promise<boolean>}){
 const [draft,setDraft]=useState('');
 async function submit(){
   const text=draft.trim();
   if(!text||busy)return;
   setDraft('');
   if(!await onSend(text))setDraft(current=>current||text);
 }
 return <form onSubmit={e=>{e.preventDefault();void submit()}} className="mx-auto flex max-w-[720px] items-end gap-3 rounded-2xl border border-[#d9ded0] bg-[#fdfdfa] p-3 shadow-[0_3px_12px_#29462c05]"><textarea aria-label="Message Mira" value={draft} onChange={e=>setDraft(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();void submit()}}} placeholder="Tell Mira your plans…" rows={1} className="max-h-32 min-h-11 min-w-0 flex-1 resize-none bg-transparent px-2 py-3 text-base sm:text-sm placeholder:text-[#a0a294]"/><Button type="submit" size="icon" disabled={busy||!draft.trim()} aria-label="Send message"><ArrowUp size={18}/></Button></form>;
}

export default function Home(){
 const [session,setSession]=useState<Session|null>(null),[state,setState]=useState<State|null>(null),[messages,setMessages]=useState<Message[]>([]),[busy,setBusy]=useState(false),[error,setError]=useState(''),[traces,setTraces]=useState<Trace[]>([]),[tab,setTab]=useState('overview'),[mode,setMode]=useState(''),[detailsOpen,setDetailsOpen]=useState(false),[manager,setManager]=useState(false),[adminToken,setAdminToken]=useState(''),[adminData,setAdminData]=useState<AdminData|null>(null),[flags,setFlags]=useState<{id:string;status:string}[]>([]),[adminError,setAdminError]=useState(''),[activityError,setActivityError]=useState(''),[activityRevision,setActivityRevision]=useState(0);
 const conversation=useRef<HTMLDivElement>(null),detailsTrigger=useRef<HTMLButtonElement>(null),detailsClose=useRef<HTMLButtonElement>(null);
 const activeSession=useRef<Session|null>(null),refreshRevision=useRef(0);
 const bottom=useRef<HTMLDivElement>(null),pending=useRef<{message:string;key:string}|null>(null),inFlight=useRef(false);
 async function api(path:string,opts:RequestInit={},s:Session|null=session){
   const res=await fetch(API+path,{...opts,headers:{'Content-Type':'application/json',...(s?{Authorization:`Bearer ${s.token}`} : {}),...opts.headers}});
   const data=await res.json(); if(!res.ok)throw new Error(typeof data.error==='string'?data.error:JSON.stringify(data.detail||'The request could not be completed.'));return data;
 }
 async function refresh(s:Session,signal?:AbortSignal){
   const revision=++refreshRevision.current;
   const data=await api(`/api/sessions/${s.session_id}`,{signal},s);
   if(signal?.aborted||revision!==refreshRevision.current||activeSession.current?.session_id!==s.session_id)return;
   setState(data.state);setMessages(data.messages);setMode(data.llm_mode);setActivityRevision(value=>value+1);
 }
 async function newSession(){
   if(inFlight.current)return;
   setError('');setBusy(true);inFlight.current=true;++refreshRevision.current;
   try{const s=await api('/api/sessions',{method:'POST'},null);localStorage.setItem('mira-session',JSON.stringify(s));activeSession.current=s;setSession(s);setState(null);setMessages([]);setTraces([]);setFlags([]);pending.current=null;await refresh(s);}catch(e){setError((e as Error).message)}finally{setBusy(false);inFlight.current=false}
 }
 useEffect(()=>{
   const controller=new AbortController();
   try{
     const saved=localStorage.getItem('mira-session');
     if(saved){
       const s=JSON.parse(saved) as Session;
       if(!s.session_id||!s.token)throw new Error('Invalid saved session');
       activeSession.current=s;setSession(s);setBusy(true);inFlight.current=true;
       refresh(s,controller.signal).catch(e=>{if(!controller.signal.aborted)setError(e.message)}).finally(()=>{if(!controller.signal.aborted){setBusy(false);inFlight.current=false}});
     }
   }catch{localStorage.removeItem('mira-session')}
   return()=>{controller.abort();++refreshRevision.current};
 },[]); // eslint-disable-line react-hooks/exhaustive-deps
 // Diagnostic reads never delay a reply or replace authoritative chat state.
 useEffect(()=>{
   setActivityError('');
   if(!session)return;
   const controller=new AbortController();
   const load=async()=>{
     const jobs=[api(`/api/sessions/${session.session_id}/flags`,{signal:controller.signal},session).then(data=>{if(!controller.signal.aborted)setFlags(data)})];
     if(tab==='activity')jobs.push(api(`/api/sessions/${session.session_id}/traces`,{signal:controller.signal},session).then(data=>{if(!controller.signal.aborted)setTraces(data)}));
     const results=await Promise.allSettled(jobs);
     if(!controller.signal.aborted&&results.some(result=>result.status==='rejected'))setActivityError('Stay activity could not be refreshed. Your conversation is saved.');
   };
   void load();
   return()=>controller.abort();
 },[session,state?.state_version,tab,activityRevision]); // eslint-disable-line react-hooks/exhaustive-deps
 useEffect(()=>{const element=conversation.current;if(element)element.scrollTo({top:element.scrollHeight,behavior:'smooth'});},[messages,busy]);
 useEffect(()=>{
   const viewport=window.visualViewport;
   const resize=()=>{document.documentElement.style.setProperty('--app-height',`${viewport?.height??window.innerHeight}px`);if(window.innerWidth>=1024)setDetailsOpen(false);};
   resize();viewport?.addEventListener('resize',resize);window.addEventListener('resize',resize);
   return()=>{viewport?.removeEventListener('resize',resize);window.removeEventListener('resize',resize);document.documentElement.style.removeProperty('--app-height');};
 },[]);
 useEffect(()=>{
   if(!detailsOpen)return;
   detailsClose.current?.focus();
   const escape=(event:KeyboardEvent)=>{
     if(event.key==='Escape'){setDetailsOpen(false);detailsTrigger.current?.focus();}
     if(event.key==='Tab'){
       const elements=Array.from(document.querySelectorAll<HTMLElement>('#stay-details button:not([disabled]),#stay-details summary,#stay-details [tabindex="0"]')).filter(element=>element.offsetParent!==null);
       const first=elements[0],last=elements[elements.length-1];
       if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
       else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
     }
   };
   document.addEventListener('keydown',escape);
   return()=>document.removeEventListener('keydown',escape);
 },[detailsOpen]);
 function closeDetails(){setDetailsOpen(false);detailsTrigger.current?.focus();}
 async function send(text:string):Promise<boolean>{
   text=text.trim();
   if(!text||inFlight.current)return false;
   inFlight.current=true;setBusy(true);setError('');++refreshRevision.current;
   const optimisticId=crypto.randomUUID();
   setMessages(old=>[...old,{id:optimisticId,role:'user',content:text}]);
   let s=session;
   try{
     if(!s){s=await api('/api/sessions',{method:'POST'},null);activeSession.current=s;setSession(s);localStorage.setItem('mira-session',JSON.stringify(s));}
     if(!s)throw new Error('Could not create a session.');
     const request=pending.current?.message===text?pending.current:{message:text,key:crypto.randomUUID()};pending.current=request;
     const result=await api('/api/chat',{method:'POST',body:JSON.stringify({session_id:s.session_id,message:text,idempotency_key:request.key})},s);
     setState(result.state);setMode('openai');setMessages(old=>[...old,{id:crypto.randomUUID(),role:'assistant',content:result.response}]);pending.current=null;
     return true;
   }catch(e){setMessages(old=>old.filter(message=>message.id!==optimisticId));setError((e as Error).message);return false;}finally{setBusy(false);inFlight.current=false;}
 }
 async function adminLoad(){setAdminError('');try{setAdminData(await api('/api/admin/escalations',{headers:{'X-Admin-Token':adminToken}},null));if(session&&!inFlight.current)await refresh(session);}catch(e){setAdminError((e as Error).message)}}
 async function adminAction(path:string){setAdminError('');try{await api(path,{method:'POST',headers:{'X-Admin-Token':adminToken}},null);await adminLoad();}catch(e){setAdminError((e as Error).message)}}
 const req=state?.booking_requirements||{};
 return <div className="flex h-[var(--app-height,100dvh)] flex-col overflow-hidden">
 <header className="flex h-16 shrink-0 items-center justify-between border-b border-[#e5e5dc] bg-[#fbfaf7] px-4 lg:h-20 lg:px-9">
   <a href="/" className="flex items-center gap-2.5" aria-label="Mehman home"><div className="flex h-9 w-9 items-center justify-center rounded-full bg-[#173f35] text-[#e4d7aa]"><Leaf size={21}/></div><span className="serif text-3xl tracking-[-1.5px]">mehman<span className="text-[#9b9c79]">.</span></span><span className="ml-3 hidden border-l border-stone-300 pl-5 text-xs text-stone-500 sm:inline">Consider your stay, considered.</span></a>
   <div className="flex items-center gap-5"><span className="hidden items-center gap-2 text-[11px] text-stone-500 md:flex"><span className="h-1.5 w-1.5 rounded-full bg-[#7b9567]"/> Fictional Goa collection</span><Button variant="ghost" size="sm" aria-label="Demo manager" onClick={()=>setManager(true)}><ShieldCheck size={15}/><span className="hidden sm:inline">Demo manager</span></Button></div>
 </header>
 <div className="mx-auto grid min-h-0 w-full max-w-[1600px] flex-1 lg:grid-cols-[minmax(0,1fr)_370px] xl:grid-cols-[minmax(0,1fr)_405px]">
 <main className="relative flex min-h-0 min-w-0 flex-col">
   <div className="flex shrink-0 items-center justify-between gap-2 border-b border-[#e5e5dc] px-4 py-3 lg:px-10 lg:py-5"><div className="flex items-center gap-3"><div className="relative hidden h-10 w-10 items-center min-[375px]:flex justify-center rounded-full bg-[#e7eadb]"><Sparkles size={19} className="text-[#61714d]"/><span className="absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full border-2 border-[#f7f6f2] bg-[#749061]"/></div><div><h1 className="text-sm font-semibold">Mira <span className="ml-1 rounded bg-[#e8ebdf] px-1.5 py-0.5 text-[9px] font-normal text-[#6f795c]">AI HOST</span></h1><p className="mt-1 hidden text-[11px] text-stone-500 sm:block">A little local knowledge. A lot of care.</p></div></div><div className="flex shrink-0 items-center gap-1"><Button ref={detailsTrigger} variant="outline" size="sm" className="lg:hidden" aria-expanded={detailsOpen} aria-controls="stay-details" onClick={()=>setDetailsOpen(true)}><Leaf size={14}/><span>Stay details</span></Button><Button variant="ghost" size="sm" aria-label="New stay" onClick={newSession} disabled={busy}><Plus size={15}/><span className="hidden min-[430px]:inline">New stay</span></Button></div></div>
   <div ref={conversation} className="scrollbar min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-5 sm:px-5 sm:py-8 lg:px-10">
    {!messages.length&&<section className="fade-in mx-auto max-w-[720px] pb-5 pt-3 lg:pt-7">
     <div className="mb-6 flex items-center gap-2 text-[11px] uppercase tracking-[.18em] text-[#7f866c]"><Sun size={15}/> A warmer welcome awaits</div>
     <h2 className="serif max-w-lg text-[36px] leading-[1.12] tracking-[-1.5px] min-[375px]:text-[40px] sm:text-[54px]">Go somewhere.<br/><span className="italic text-[#849071]">Feel at home.</span></h2>
     <p className="mt-4 max-w-[445px] text-sm leading-6 sm:mt-5 sm:leading-7 text-[#7c8176]">I’m Mira, your personal receptionist. Tell me what your perfect Goa stay looks like — I’ll take care of the details.</p>
     <div className="mt-7 grid grid-cols-1 gap-2 sm:grid-cols-3">{suggestions.map((s,i)=><button key={s} onClick={()=>send(s)} disabled={busy} className="group flex min-h-14 items-center gap-3 sm:min-h-24 sm:flex-col sm:items-start sm:justify-between rounded-2xl border border-[#e3e4da] bg-[#fbfaf7] p-4 text-left text-xs transition hover:border-[#a4b092]">{i===0?<Compass size={18} className="shrink-0 text-[#8c967a] sm:mb-3"/>:i===1?<Waves size={18} className="shrink-0 text-[#8c967a] sm:mb-3"/>:<Sun size={18} className="shrink-0 text-[#8c967a] sm:mb-3"/>}<span className="flex w-full min-w-0 items-center justify-between gap-2">{s}<ArrowUpRight size={13} className="text-[#99a185]"/></span></button>)}</div>
     <div className="mt-5 flex items-start gap-2 text-[10px] leading-5 sm:mt-7 text-[#92968b]"><ShieldCheck size={13}/> Verified inventory · Transparent prices · No payment required</div>
    </section>}
    <div className="mx-auto max-w-[720px] space-y-6" aria-live="polite">{messages.map((msg,i)=><div key={msg.id||i} className={`fade-in flex ${msg.role==='user'?'justify-end':'gap-3'}`}>{msg.role==='assistant'&&<span className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#e5eadc]"><Sparkles size={13}/></span>}<div className={msg.role==='user'?'min-w-0 max-w-[90%] break-words rounded-2xl rounded-tr-sm bg-[#e9ecdf] px-5 py-3.5 text-sm leading-6':'min-w-0 flex-1 whitespace-pre-wrap break-words text-sm leading-7 text-[#626c60]'}>{msg.content}</div></div>)}
    {!!state?.latest_recommendations.length&&<div className="grid gap-3">{state.latest_recommendations.map((card,i)=><article key={card.quote.id} className="overflow-hidden rounded-2xl border border-[#dfe3d7] bg-[#fbfcf7]"><div className="flex flex-col gap-4 p-4 sm:flex-row sm:p-5"><div className={`hidden h-24 w-24 shrink-0 items-center justify-center rounded-xl ${i===0?'bg-[#e2e7d6]':i===1?'bg-[#eae3d3]':'bg-[#dce8e3]'} sm:flex`}><Waves size={32} strokeWidth={1} className="text-[#7d8e76]"/></div><div className="min-w-0 flex-1"><div className="eyebrow">OPTION {i+1} · {card.location}</div><h3 className="serif mt-1 text-xl">{card.room_name}</h3><p className="mt-1 text-[11px] text-stone-500">{card.property_name.replace(' · Fictional','')} · Up to {card.capacity} guests</p><div className="mt-2 flex flex-wrap gap-1.5">{card.amenities.slice(0,4).map(a=><span key={a} className="rounded bg-[#edf0e7] px-2 py-0.5 text-[9px] capitalize text-[#75836a]">{label(a)}</span>)}</div></div><div className="flex shrink-0 items-center justify-between gap-3 border-t border-[#e0e4d7] pt-3 sm:flex-col sm:items-end sm:border-0 sm:pt-0"><div className="sm:text-right"><div className="serif text-lg">{inr(card.quote.total_minor)}</div><div className="mt-1 text-[9px] text-stone-500">{card.quote.nights} nights · incl. tax</div></div><Button size="sm" variant={state.latest_quote_id===card.quote.id?'default':'outline'} disabled={busy} onClick={()=>send(`Select option ${i+1}`)}>{state.latest_quote_id===card.quote.id?<Check size={12}/>:null}Select<ArrowUpRight size={11}/></Button></div></div></article>)}</div>}
    {state?.itinerary&&<section aria-label="Your demo itinerary" className="rounded-2xl border border-[#dfe3d7] bg-[#fbfaf7] p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="eyebrow">FICTIONAL DEMO ITINERARY</div><h3 className="serif mt-2 text-xl capitalize">{label(state.itinerary.region)} · {state.itinerary.days.length} days</h3><p className="mt-1 text-xs capitalize text-stone-500">{state.itinerary.pace} pace</p></div><Button variant="outline" size="sm" disabled={busy} onClick={()=>send('Regenerate my saved itinerary for my current travel dates and preferences.')}>Refresh itinerary</Button></div>{state.itinerary.stale?<p role="status" className="mt-4 text-xs text-amber-800">Your travel requirements changed. Refresh this itinerary before using it.</p>:<div className="mt-4 space-y-4">{state.itinerary.days.map(day=><article key={day.day} className="rounded-xl bg-[#edf0e7] p-4"><h4 className="text-sm font-semibold">Day {day.day}{day.date?` · ${day.date}`:''}</h4><ul className="mt-3 space-y-3">{day.stops.map(stop=><li key={stop.activity.id} className="text-xs leading-5"><span className="capitalize text-[#75836a]">{label(stop.slot)}</span><p className="font-medium">{stop.activity.name}</p><p className="text-stone-500">{stop.activity.description}</p></li>)}</ul>{day.note&&<p className="mt-3 text-xs text-stone-500">{day.note}</p>}</article>)}</div>}<p className="mt-4 text-[10px] leading-5 text-stone-500">{state.itinerary.disclaimer}</p><p className="mt-2 text-[10px] text-stone-500">Ask Mira to change the area, pace, interests, or excluded activities.</p></section>}
    {state?.quote&&<div className="rounded-2xl border border-[#dfe3d7] bg-[#fbfaf7] p-5 text-xs"><div className="eyebrow mb-4">YOUR STAY, IN DETAIL</div><div className="flex justify-between"><span>{state.quote.nights} nights × {inr(state.quote.nightly_minor)}</span><span>{inr(state.quote.base_minor)}</span></div>{state.quote.add_ons.map(a=><div key={a.name} className="mt-2 flex justify-between"><span>{a.name}</span><span>{inr(a.amount_minor)}</span></div>)}<div className="mt-2 flex justify-between text-stone-500"><span>Fictional tax</span><span>{inr(state.quote.tax_minor)}</span></div><div className="mt-4 flex justify-between border-t border-stone-200 pt-3 font-semibold"><span>Original stay total</span><span>{inr(state.quote.total_minor)}</span></div>{state.negotiation_state.status&&<div className="mt-3 flex justify-between text-[#77894d]"><span className="capitalize">Offer · {label(state.negotiation_state.status)}</span><span>{state.negotiation_state.approved_amount?inr(state.negotiation_state.approved_amount):'Awaiting review'}</span></div>}{state.pending_confirmation&&<Button className="mt-5 w-full" disabled={busy} onClick={()=>send('Confirm hold')}>Confirm temporary hold<ArrowUpRight size={14}/></Button>}</div>}
    {state?.hold&&<div className="rounded-2xl bg-[#e6ecdf] p-5"><div className="flex items-center gap-2 text-sm font-semibold"><CheckCheck size={18}/> {state.hold.status==='cancelled'?'Hold cancelled':state.hold.status==='expired'?'Hold expired':'Your temporary hold'}</div><p className="mt-2 text-xs leading-6">{inr(state.hold.total_minor)} · Expires {new Date(state.hold.expires_at+'Z').toLocaleString()}<br/>Reference {state.hold.id.slice(0,8)} · Not a confirmed reservation.</p>{state.hold.status==='temporary_hold'&&<Button className="mt-3" variant="outline" size="sm" disabled={busy} onClick={()=>send('Please cancel my current temporary hold and release the room.')}>Cancel temporary hold</Button>}</div>}
    {busy&&<div className="flex items-center gap-3 text-xs text-[#818c76]"><Loader2 size={15} className="animate-spin"/> Mira is checking the details…</div>}
    <div ref={bottom}/></div>
   </div>
   <div className="composer shrink-0 border-t border-[#e5e5dc] bg-[#f7f6f2] px-3 pt-3 sm:px-5 lg:border-0 lg:px-10">{error&&<div role="alert" className="mx-auto mb-3 max-w-[720px] rounded-xl border border-red-200 bg-red-50 p-3 text-xs leading-5 text-red-800">{error} {pending.current&&<button className="ml-2 underline" disabled={busy} onClick={()=>send(pending.current!.message)}>Retry message</button>}</div>}<Composer busy={busy} onSend={send}/><p className="mt-2 text-center text-[10px] leading-4 sm:mt-3 sm:text-[9px] text-[#a2a596]">A fictional hotel collection for a real conversation. Prices in INR. {mode==='openai'?'AI conversations · Verified hotel records.':'Powered by verified hotel records.'}</p></div>
 </main>
 {detailsOpen&&<button tabIndex={-1} aria-label="Close stay details overlay" className="fixed inset-0 z-30 bg-[#15291e66] lg:hidden" onClick={closeDetails}/>}
 <aside id="stay-details" role={detailsOpen?'dialog':undefined} aria-modal={detailsOpen||undefined} aria-label="Stay details" className={`scrollbar min-h-0 min-w-0 overflow-y-auto overscroll-contain border-[#e2e5da] bg-[#eff1e9] px-5 py-5 lg:static lg:z-auto lg:block lg:rounded-none lg:border-l lg:px-6 lg:py-7 ${detailsOpen?'fixed inset-x-0 bottom-0 top-16 z-40 rounded-t-3xl':'hidden'}`}>
  <div className="mb-4 flex items-center justify-between lg:hidden"><span className="text-sm font-semibold">Your stay details</span><Button ref={detailsClose} variant="ghost" size="icon" aria-label="Close stay details" onClick={closeDetails}><X size={20}/></Button></div>
  <div className="flex items-center justify-between"><div><p className="eyebrow">BEHIND THE WELCOME</p><h2 className="serif mt-2 text-[25px] tracking-[-.5px]">Your stay, taking shape.</h2></div><Leaf size={21} strokeWidth={1} className="text-[#849271]"/></div>
  <p className="mt-3 text-[11px] leading-5 text-[#8b9181]">A clear view of what Mira knows, checks, and arranges for you.</p>
  <div className="mt-6 flex gap-5 border-b border-[#dce1d2]">{['overview','activity'].map(t=><button key={t} onClick={()=>setTab(t)} className={`border-b-2 pb-3 text-[11px] capitalize ${tab===t?'border-[#244b3d] font-semibold':'border-transparent text-[#929888]'}`}>{t==='activity'?'Tool activity':t}</button>)}</div>
  {tab==='overview'?<>
   <section className="mt-6"><div className="flex items-center justify-between"><h3 className="eyebrow">THE ESSENTIALS</h3><span className="rounded-full border border-[#d8dfce] px-2 py-0.5 text-[8px] text-[#8a967c]">{state?`STATE v${state.state_version}`:'WAITING FOR YOU'}</span></div>
    <dl className="mt-4 space-y-0">{[['Destination',String(req.destination||'Where shall we go?')],['Dates',req.check_in?`${req.check_in} → ${req.check_out||'Departure?'}`:'A little flexibility is welcome'],['Guests',req.adults?`${req.adults} adults · ${req.children||0} children`:'Your favourite people'],['Budget',req.budget_amount?`${inr(Number(req.budget_amount))} / ${req.budget_basis}`:'Let’s find the right fit'],['Must-haves',Array.isArray(req.required_amenities)&&req.required_amenities.length?req.required_amenities.map(String).map(label).join(', '):'The details that matter']].map(([k,v])=><div key={k} className="flex justify-between gap-5 border-b border-[#e0e4d7] py-3.5 text-[11px]"><dt className="text-[#8a927e]">{k}</dt><dd className={`max-w-[185px] text-right ${v.includes('?')||['A little flexibility is welcome','Your favourite people','Let’s find the right fit','The details that matter'].includes(v)?'italic text-[#a1a792]':'text-[#4e6347]'}`}>{v}</dd></div>)}</dl>
   </section>
   <section className="mt-7 rounded-xl border border-[#dbe1d2] bg-[#f7f8f2] p-4"><div className="flex items-center gap-2 text-[11px] font-semibold"><Compass size={14} className="text-[#819071]"/> The next little step</div><p className="mt-2 text-xs leading-5 text-[#849078]">{state?label(state.next_action):'Tell Mira what you have in mind. A destination, a date, a daydream.'}</p></section>
   <section className="mt-7"><h3 className="eyebrow mb-3">RECEPTION DESK</h3>{[['Intent',label(state?.active_intent||'Getting acquainted')],['Room options',String(state?.latest_recommendations.length||'—')],['Negotiation',label(state?.negotiation_state.status||'No active offer')],['Staff review',flags.length?`${flags.filter(f=>f.status==='open').length} open requests`:'None needed']].map(([k,v])=><div key={k} className="mb-3 flex justify-between text-[10px]"><span className="text-[#8b947e]">{k}</span><span className="capitalize text-[#657959]">{v}</span></div>)}</section>
   {state&&<details className="mt-5 text-[10px] text-[#89957c]"><summary className="flex items-center gap-1"><Code2 size={12}/> Structured state <ChevronDown size={11}/></summary><pre className="text-wrap mt-3 max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-[#e7ecdf] p-3 text-[9px]">{JSON.stringify(state,null,2)}</pre></details>}
  </>:<section className="mt-5"><div className="mb-4 flex items-center justify-between"><span className="eyebrow">VERIFIED EXECUTION</span><button aria-label="Refresh activity" className="text-[10px] underline" disabled={!session||busy} onClick={()=>setActivityRevision(value=>value+1)}>Refresh</button></div>{!traces.length?<p className="text-xs leading-6 text-[#89947c]">When Mira checks inventory, calculates prices, or arranges a hold, you’ll see the real tool calls here.</p>:traces.map(t=><details key={t.id} className="mb-2 rounded-xl border border-[#dce2d2] bg-[#f8f9f3] p-3"><summary className="flex items-center justify-between gap-2 text-[10px]"><span className="flex items-center gap-2">{t.success?<Check size={12} className="text-[#749557]"/>:<X size={12} className="text-red-600"/>}{t.tool_name}</span><span className="text-[#98a18d]">{t.duration_ms} ms</span></summary><pre className="text-wrap mt-3 overflow-auto whitespace-pre-wrap text-[9px] leading-5 text-[#849078]">{JSON.stringify({arguments:t.arguments,result:t.summary,request_id:t.correlation_id},null,2)}</pre></details>)}{traces.length>=30&&<p className="text-[10px] text-stone-500">Showing latest 30 tool calls.</p>}</section>}
  {activityError&&<p role="status" className="mt-4 text-xs text-amber-800">{activityError}</p>}
  {error&&<section aria-label="Latest error" className="mt-5 rounded-xl border border-red-200 bg-red-50 p-3 text-xs leading-5 text-red-800"><h3 className="mb-1 font-semibold">Latest error</h3>{error}</section>}
  <div className="mt-10 border-t border-[#dbe1d2] pt-5"><div className="flex gap-2 text-[10px] text-[#819171]"><ShieldCheck size={14}/> Grounded in hotel records</div><p className="mt-2 text-[10px] leading-5 text-[#9aa28d]">Mira checks before making a promise. Unknown details stay unknown. Human decisions stay human.</p>{session&&<div className="mt-3 text-[8px] text-[#a5ad98]">SESSION {session.session_id.slice(0,8)} · PERSISTED</div>}</div>
 </aside>
 </div>
 {manager&&<div className="fixed inset-0 z-50 flex items-center justify-center bg-[#15291e66] p-4"><section role="dialog" aria-modal="true" aria-label="Demo manager review" className="max-h-[85dvh] w-full max-w-lg overflow-y-auto overscroll-contain rounded-2xl bg-[#fbfaf7] p-4 sm:p-7"><div className="flex items-center justify-between"><h2 className="serif text-2xl">Manager review</h2><Button variant="ghost" size="icon" aria-label="Close manager review" onClick={()=>{setManager(false);setAdminToken('');setAdminData(null)}}><X size={17}/></Button></div><p className="mt-2 text-xs leading-6 text-stone-500">Demo-only staff access. Enter the separate admin token configured on the backend. Decisions are recorded in the database.</p><form className="mt-4 flex flex-col gap-2 sm:flex-row" onSubmit={e=>{e.preventDefault();adminLoad()}}><input type="password" aria-label="Admin token" placeholder="Admin token" className="min-h-11 min-w-0 flex-1 rounded-xl border border-stone-300 px-3 text-base sm:text-xs" value={adminToken} onChange={e=>setAdminToken(e.target.value)}/><Button type="submit" size="sm">Load requests</Button></form>{adminError&&<p role="alert" className="mt-3 text-xs text-red-700">{adminError}</p>}{adminData&&<div className="mt-5 space-y-3">{!adminData.offers.length&&!adminData.flags.length&&<p className="text-xs text-stone-500">No pending requests.</p>}{adminData.offers.map(o=><div key={o.id} className="rounded-xl border p-4 text-xs"><p>Requested stay total: {inr(o.proposed_amount)}</p><p className="my-2 text-[10px] text-stone-500">Offer {o.id.slice(0,8)} · {label(o.status)}</p><div className="flex gap-2"><Button size="sm" onClick={()=>adminAction(`/api/admin/offers/${o.id}/approve`)}>Approve</Button><Button variant="outline" size="sm" onClick={()=>adminAction(`/api/admin/offers/${o.id}/reject`)}>Reject</Button></div></div>)}{adminData.flags.map(f=><div key={f.id} className="rounded-xl border p-4 text-xs"><p className="capitalize">{label(f.category)} · {f.severity}</p><p className="my-2 text-stone-500">{label(f.reason_code)}</p><Button size="sm" variant="outline" onClick={()=>adminAction(`/api/admin/escalations/${f.id}/resolve`)}>Mark reviewed</Button></div>)}</div>}</section></div>}
 </div>
}
