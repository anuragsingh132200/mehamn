"""Run mocked structured-LLM and database evaluations; emit machine-readable diagnostics from actual pytest results."""
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
root=Path(__file__).resolve().parents[1]
report=root/'reports';report.mkdir(exist_ok=True)
result=subprocess.run([sys.executable,'-m','pytest','-q','--junitxml='+str(report/'pytest.xml')],cwd=root/'backend')
xml=ET.parse(report/'pytest.xml')
cases=[]
for case in xml.findall('.//testcase'):
    failure=case.find('failure');error=case.find('error');skip=case.find('skipped')
    issue=failure if failure is not None else error
    cases.append({'scenario':case.attrib['name'],'suite':case.attrib.get('classname'),'seconds':float(case.attrib.get('time',0)),'status':'failed' if issue is not None else 'skipped' if skip is not None else 'passed','diagnostic':issue.text if issue is not None else skip.attrib.get('message') if skip is not None else None})
metrics={}
map_metrics={
'interpretation_fixture_regression':['relative_dates','ambiguous_yes','second_option','too_expensive','manager_request'],
'state_updates':['date_change','guest_count','budget_change','patch_semantics','persistent_state'],
'pricing':['price_uses','discount_auto','counteroffer'],
'negotiation_compliance':['manager_approval','stale_manager','ambiguous_offer','free_breakfast','counteroffer'],
'escalation':['rule_escalation','manager_request','repeated_negotiation','timeout_preserves'],
'grounding':['unknown_pool','private_pool','capacity_conflict','prompt_injection'],
'booking_concurrency':['cannot_hold_last_unit','messages_are_serialized','duplicate_confirmation'],
'next_action':['missing_checkout','second_option','too_expensive'],
'recommendations':['private_pool','budget_change','capacity_conflict'],
'protocol_and_tools':['trace_redacts','checkout_exclusive','unavailable_seed','version_conflict','idempotency_key']}
for metric,tokens in map_metrics.items():
    selected=[c for c in cases if any(t in c['scenario'] for t in tokens)]
    ran=[c for c in selected if c['status']!='skipped']
    metrics[metric]={'passed':sum(c['status']=='passed' for c in ran),'executed':len(ran),'skipped':len(selected)-len(ran),'pass_rate':sum(c['status']=='passed' for c in ran)/len(ran) if ran else None}
output={'mode':'mocked_structured_llm','database':'postgresql' if os.environ.get('TEST_DATABASE_URL','').startswith('postgresql') else 'sqlite','live_model_evaluated':False,'counts':{v:sum(c['status']==v for c in cases) for v in ['passed','failed','skipped']},'metrics':metrics,'scenarios':cases}
(report/'evaluation.json').write_text(json.dumps(output,indent=2))
print(json.dumps(output['counts']))
sys.exit(result.returncode)
