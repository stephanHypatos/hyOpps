from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .database import create_schema, seed_data
from .routes import auth, executions, organizations, users, partner


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_schema()
    seed_data()
    yield


app = FastAPI(
    title="HyOpps Workflow API",
    description="Workflow orchestration for access provisioning",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(executions.router, prefix="/api/executions", tags=["executions"])
app.include_router(organizations.router, prefix="/api/organizations", tags=["organizations"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(partner.router, prefix="/api/partner", tags=["partner"])


@app.get("/api/workflow-definitions")
def list_workflow_definitions():
    from .database import get_db
    conn = get_db()
    rows = conn.execute("SELECT * FROM workflow_definitions").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/health")
def health():
    return {"status": "ok"}
