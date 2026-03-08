"""
Agent Kernel Python Intelligence Layer.
"""
import asyncio
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import uuid4

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from context_compiler.master_compiler import get_master_compiler
from personality.prime_personality import get_prime_personality
from schemas.models import HealthCheck, Request, RequestStatus, Session
from session_host.session_host import get_session_host
from storage.runtime_store import get_memory_manager
from thread_runtime.scheduler import get_scheduler

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Python Kernel")
    memory_manager = get_memory_manager()
    await memory_manager.initialize()
    scheduler = get_scheduler()
    scheduler_task = asyncio.create_task(scheduler.start())
    logger.info("Python Kernel ready")
    yield
    logger.info("Shutting down Python Kernel")
    await scheduler.stop()
    scheduler_task.cancel()
    await memory_manager.close()
    logger.info("Python Kernel stopped")


app = FastAPI(
    title="Agent Kernel Python Intelligence Layer",
    description="Python-based agent intelligence and execution layer",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
FastAPIInstrumentor.instrument_app(app)


@app.get("/health", response_model=HealthCheck)
async def health_check():
    return HealthCheck(
        status="healthy",
        version="0.1.0",
        timestamp=datetime.utcnow(),
        components={
            "storage": "connected",
            "scheduler": "running",
            "run_mode": os.environ.get("KERNEL_RUN_MODE", "real"),
        },
    )


@app.post("/v1/execute")
async def execute_request(request_data: dict):
    request: Request | None = None
    started_at = time.perf_counter()
    memory_manager = get_memory_manager()

    try:
        request = Request(
            id=request_data.get("request_id", str(uuid4())),
            session_id=request_data.get("session_id", str(uuid4())),
            user_id=request_data["user_id"],
            message=request_data["message"],
            metadata=request_data.get("metadata", {}),
        )
        logger.info("Received execution request", request_id=request.id, session_id=request.session_id, user_id=request.user_id)

        session = await memory_manager.get_session(request.session_id)
        if not session:
            session = Session(id=request.session_id, user_id=request.user_id)
            await memory_manager.save_session(session)

        request.status = RequestStatus.PROCESSING
        request.processed_at = datetime.utcnow()
        await memory_manager.save_request(request)
        await memory_manager.save_event(
            request.session_id,
            {
                "timestamp": datetime.utcnow().isoformat(),
                "session_id": request.session_id,
                "request_id": request.id,
                "phase": "request_received",
                "actor": "python_kernel",
                "summary": request.message,
                "status": "processing",
            },
        )

        recent_events = await memory_manager.get_recent_events(request.session_id, limit=20)
        recent_snapshots = await memory_manager.get_recent_snapshots(request.session_id, limit=2)
        recent_tasks = [task.model_dump(mode='json') for task in await memory_manager.get_session_tasks(request.session_id)][:5]

        master_context = get_master_compiler().compile(
            request=request,
            session=session,
            additional_context={
                "recent_events": recent_events,
                "recent_snapshots": recent_snapshots,
                "recent_tasks": recent_tasks,
                "request_metadata": request.metadata,
            },
        )
        await memory_manager.save_event(
            request.session_id,
            {
                "timestamp": datetime.utcnow().isoformat(),
                "session_id": request.session_id,
                "request_id": request.id,
                "phase": "context_compiled",
                "actor": "master_compiler",
                "summary": "Master context compiled",
                "status": "completed",
            },
        )

        intermediate_repr = await get_prime_personality().process_request(request=request, session_context=master_context)
        await memory_manager.save_event(
            request.session_id,
            {
                "timestamp": datetime.utcnow().isoformat(),
                "session_id": request.session_id,
                "request_id": request.id,
                "phase": "ir_generated",
                "actor": "prime_personality",
                "summary": intermediate_repr.intent,
                "status": "completed",
            },
        )

        result = await get_session_host(session).handle_request(request, intermediate_repr)
        request.status = RequestStatus.COMPLETED if result["status"] == "completed" else RequestStatus.FAILED
        request.completed_at = datetime.utcnow()
        await memory_manager.save_request(request)
        await memory_manager.save_event(
            request.session_id,
            {
                "timestamp": datetime.utcnow().isoformat(),
                "session_id": request.session_id,
                "request_id": request.id,
                "phase": "request_completed" if result["status"] == "completed" else "request_failed",
                "actor": "python_kernel",
                "summary": request.message,
                "status": result["status"],
            },
        )

        return {
            "request_id": request.id,
            "session_id": request.session_id,
            "status": result["status"],
            "result": result,
            "task_ids": result["task_ids"],
            "processing_time_ms": int((time.perf_counter() - started_at) * 1000),
        }
    except Exception as e:
        logger.error("Request execution failed", error=str(e))
        if request is not None:
            request.status = RequestStatus.FAILED
            request.completed_at = datetime.utcnow()
            await memory_manager.save_request(request)
            await memory_manager.save_event(
                request.session_id,
                {
                    "timestamp": datetime.utcnow().isoformat(),
                    "session_id": request.session_id,
                    "request_id": request.id,
                    "phase": "request_failed",
                    "actor": "python_kernel",
                    "summary": str(e),
                    "status": "failed",
                },
            )
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/sessions/{session_id}/status")
async def get_session_status(session_id: str):
    memory_manager = get_memory_manager()
    session = await memory_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    tasks = await memory_manager.get_session_tasks(session_id)
    active_tasks = [
        {
            "id": task.id,
            "status": task.status,
            "goal": task.goal,
        }
        for task in tasks
        if task.status in ["running", "idle"]
    ]

    return {
        "session_id": session_id,
        "status": session.status,
        "task_count": session.task_count,
        "active_tasks": active_tasks,
        "active_task_count": len(active_tasks),
        "last_activity": session.last_activity.isoformat(),
    }


@app.get("/v1/tasks/{task_id}")
async def get_task_status(task_id: str):
    memory_manager = get_memory_manager()
    task = await memory_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return {
        "task_id": task.id,
        "session_id": task.session_id,
        "status": task.status,
        "goal": task.goal,
        "created_at": task.created_at.isoformat(),
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "output": task.output,
        "error": task.error,
    }


def main():
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    logger.info("Starting server", host=host, port=port)
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=os.environ.get("ENV", "production") == "development",
        log_level="info",
    )


if __name__ == "__main__":
    main()
