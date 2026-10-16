from langgraph.checkpoint.postgres import PostgresSaver
from .config import settings
if __name__=="__main__":
    with PostgresSaver.from_conn_string(settings.database_url.replace("postgresql+psycopg://","postgresql://")) as saver: saver.setup()
    print("PostgreSQL LangGraph checkpoint schema ready.")
