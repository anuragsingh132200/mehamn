"""Start the local API using the repository .env, overriding stale shell values.
Usage: backend/.venv/bin/python scripts/run_local.py [--setup] [--port 8000]
--setup applies migrations, seeds fictional records and initializes checkpoints.
"""
import argparse,os,subprocess,sys
from pathlib import Path
from dotenv import dotenv_values
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--setup',action='store_true');p.add_argument('--port',type=int,default=8000)
a=p.parse_args()
if not (root/'.env').exists():raise SystemExit('Create .env from .env.example and set your database URL and API key first.')
env=os.environ.copy();env.update({k:v for k,v in dotenv_values(root/'.env').items() if v is not None})
if a.setup:
 for command in [['alembic','upgrade','head'],['app.seed'],['app.checkpoints']]:
  argv=[sys.executable,'-m',*command]
  subprocess.run(argv,cwd=root/'backend',env=env,check=True)
os.chdir(root/'backend')
os.execve(sys.executable,[sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(a.port),'--workers','2'],env)
