from fastapi import Header,HTTPException
from pydantic import BaseModel,Field,ConfigDict
from platform_common import application,bounded,create,read,update,operator
from workflow import WORKFLOWS,definition,run_graph

app=application('Enterprise Agentic AI Platform','Ten checkpointed LangGraph workflows with controlled tools and human review.')


class Task(BaseModel):
    model_config=ConfigDict(extra='forbid')
    workflow:str
    task:str=Field(min_length=5,max_length=1000)
    live:bool=False


class Decision(BaseModel):
    choice:str=Field(pattern='^(approve|reject)$')
    reason:str=Field(min_length=3,max_length=500)
    version:int=Field(ge=0)


@app.get('/api/workflows')
def workflows():return WORKFLOWS


@app.post('/api/runs',status_code=201)
def start(body:Task,x_admin_token:str=Header(default='')):
    try:definition(body.workflow)
    except ValueError:raise HTTPException(422,'Unknown workflow') from None
    if body.live:operator(x_admin_token)
    with bounded():
        record=create({'status':'starting','workflow':body.workflow})
        try:result=run_graph(record['id'],{'workflow':body.workflow,'task':body.task,'live':body.live,'steps':0,'tokens':0,'evidence':{},'trace':[]})
        except Exception:
            update(record['id'],record['token'],{'status':'failed','error':'Workflow could not complete; check server credentials and model compatibility'},0)
            raise HTTPException(502,'Workflow could not complete; no deterministic fallback was substituted') from None
        saved=update(record['id'],record['token'],result,0)
    return {**saved,'token':record['token']}


@app.get('/api/runs/{run_id}')
def get_run(run_id:str,x_run_token:str=Header(default='')):return read(run_id,x_run_token)


@app.post('/api/runs/{run_id}/decision')
def decide(run_id:str,body:Decision,x_run_token:str=Header(default='')):
    with bounded():
        current=read(run_id,x_run_token)
        if current['status']!='pending_review':raise HTTPException(409,'Run is not pending review')
        # Reserve the decision with a CAS before resuming the graph. Concurrent reviewers cannot both resume.
        payload={k:v for k,v in current.items() if k not in {'id','version'}}
        reserved=update(run_id,x_run_token,{**payload,'status':'resuming','operator_decision':body.model_dump()},body.version)
        try:result=run_graph(run_id,decision={'choice':body.choice,'reason':body.reason})
        except Exception:
            update(run_id,x_run_token,{**payload,'status':'resume_failed','operator_decision':body.model_dump()},reserved['version'])
            raise HTTPException(502,'Checkpoint resume failed; the decision is preserved for inspection') from None
        return update(run_id,x_run_token,{**result,'operator_decision':body.model_dump()},reserved['version'])
