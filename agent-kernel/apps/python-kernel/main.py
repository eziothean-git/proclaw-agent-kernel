"""
Agent Kernel Python Intelligence Layer.
"""
import asyncio
import os
import time
import traceback
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import uuid4

import httpx
import structlog
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from context_compiler.master_compiler import get_master_compiler
from executors_client.directory_lock_manager import get_directory_lock_manager
from inbox_watcher import get_inbox_watcher
from kernel_init import initialize_kernel, shutdown_kernel
from personality.prime_personality import get_prime_personality
from schemas.models import HealthCheck, Request, RequestStatus, Session
from scheduled_dispatcher import ScheduledRequestStorage, ScheduledRequestDispatcher
from session_host.session_host import get_session_host
from storage.runtime_store import get_memory_manager
from thread_runtime.scheduler import get_scheduler

logger = structlog.get_logger()

# HTTP client for callbacks
callback_client = httpx.AsyncClient(timeout=60.0)

# Global dispatcher instance for health checks
_scheduled_dispatcher: ScheduledRequestDispatcher | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Python Kernel")
    
    # Initialize kernel (registers skills, starts OS interface)
    await initialize_kernel()
    
    memory_manager = get_memory_manager()
    await memory_manager.initialize()
    
    # Start scheduler
    scheduler = get_scheduler()
    scheduler_task = asyncio.create_task(scheduler.start())
    
    # Start directory lock cleanup task
    lock_manager = get_directory_lock_manager()
    lock_cleanup_task = asyncio.create_task(lock_manager.start_cleanup_task())
    
    # Start inbox watcher (for Gateway mailbox integration)
    inbox_watcher = get_inbox_watcher()
    await inbox_watcher.start()
    
    # Start scheduled request dispatcher
    global _scheduled_dispatcher
    scheduled_storage = ScheduledRequestStorage(base_path=os.environ.get("DATA_PATH", "./data"))
    _scheduled_dispatcher = ScheduledRequestDispatcher(
        storage=scheduled_storage,
        inbox_path=os.environ.get("GATEWAY_INBOX_PATH", "./data/gateway/inbox"),
        check_interval=float(os.environ.get("SCHEDULER_CHECK_INTERVAL", "60")),
    )
    await _scheduled_dispatcher.start()
    
    logger.info("Python Kernel ready")
    yield
    
    logger.info("Shutting down Python Kernel")
    await inbox_watcher.stop()
    if _scheduled_dispatcher:
        await _scheduled_dispatcher.stop()
    await scheduler.stop()
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
    
    # Stop directory lock cleanup task
    await lock_manager.stop_cleanup_task()
    lock_cleanup_task.cancel()
    try:
        await lock_cleanup_task
    except asyncio.CancelledError:
        pass
    
    # Shutdown kernel gracefully
    await shutdown_kernel()
    
    await memory_manager.close()
    await callback_client.aclose()
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
    components = {
        "storage": "connected",
        "scheduler": "running",
        "run_mode": os.environ.get("KERNEL_RUN_MODE", "real"),
        "scheduled_dispatcher": "running" if _scheduled_dispatcher and _scheduled_dispatcher._running else "stopped",
    }
    
    if _scheduled_dispatcher:
        stats = _scheduled_dispatcher.get_statistics()
        components["scheduled_request_stats"] = stats
    
    return HealthCheck(
        status="healthy",
        version="0.1.0",
        timestamp=datetime.utcnow(),
        components=components,
    )


async def process_request_async(request_id: str, callback_url: str):
    """异步处理请求并在完成后回调 Gateway"""
    started_at = time.perf_counter()
    memory_manager = get_memory_manager()
    request: Request | None = None
    
    try:
        # Load request from storage
        request = await memory_manager.get_request(request_id)
        if not request:
            logger.error("Request not found", request_id=request_id)
            await send_callback(callback_url, {
                "request_id": request_id,
                "status": "failed",
                "error": {
                    "category": "system_error",
                    "message": "Request not found in storage",
                    "recoverable": False,
                }
            })
            return
        
        # Get or create session
        session = await memory_manager.get_session(request.session_id)
        if not session:
            session = Session(id=request.session_id, user_id=request.user_id)
            await memory_manager.save_session(session)
        
        # Update status to processing
        request.status = RequestStatus.PROCESSING
        request.processed_at = datetime.utcnow()
        await memory_manager.save_request(request)
        
        # Compile context
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
        
        # Prime Personality processing
        intermediate_repr = await get_prime_personality().process_request(
            request=request, 
            session_context=master_context
        )
        
        # Session Host execution
        result = await get_session_host(session).handle_request(request, intermediate_repr)
        
        # Update request status
        request.status = RequestStatus.COMPLETED if result["status"] == "completed" else RequestStatus.FAILED
        request.completed_at = datetime.utcnow()
        await memory_manager.save_request(request)
        
        # Build output IR (Gateway Webhook format)
        processing_time_ms = int((time.perf_counter() - started_at) * 1000)
        output_ir = {
            "request_id": request.id,
            "session_id": request.session_id,
            "status": result["status"],
            "header": {
                "timestamp": datetime.utcnow().isoformat(),
                "processing_time_ms": processing_time_ms,
            },
            "body": result.get("output", ""),
            "metadata": {
                "actions": result.get("actions", []),
            },
        }
        
        if result["status"] != "completed":
            output_ir["error"] = {
                "category": result.get("error_category", "unknown"),
                "code": result.get("error_code", "INTERNAL_ERROR"),
                "message": result.get("error", "Unknown error"),
                "stack_trace": result.get("stack_trace"),
                "recoverable": result.get("recoverable", False),
            }
        
        # Send callback
        await send_callback(callback_url, output_ir)
        logger.info("Request completed and callback sent", 
                   request_id=request_id, 
                   status=result["status"],
                   processing_time_ms=processing_time_ms)
        
    except Exception as e:
        logger.error("Request processing failed", 
                    request_id=request_id, 
                    error=str(e),
                    traceback=traceback.format_exc())
        
        if request:
            request.status = RequestStatus.FAILED
            request.completed_at = datetime.utcnow()
            await memory_manager.save_request(request)
        
        # Send error callback
        await send_callback(callback_url, {
            "request_id": request_id,
            "status": "failed",
            "error": {
                "category": "system_error",
                "code": "INTERNAL_ERROR",
                "message": str(e),
                "stack_trace": traceback.format_exc(),
                "recoverable": False,
            }
        })


async def send_callback(callback_url: str, payload: dict):
    """发送回调到 Gateway"""
    try:
        response = await callback_client.post(callback_url, json=payload)
        if response.status_code >= 400:
            logger.error("Callback failed", 
                        url=callback_url, 
                        status=response.status_code,
                        response=response.text)
        else:
            logger.debug("Callback sent successfully", url=callback_url)
    except Exception as e:
        logger.error("Failed to send callback", url=callback_url, error=str(e))


@app.post("/v1/execute")
async def execute_request(request_data: dict, background_tasks: BackgroundTasks):
    """
    接收请求并立即返回 request_id，后台异步处理完成后通过 callback 通知 Gateway
    
    Expected request_data:
    {
        "request_id": "uuid",
        "session_id": "uuid",
        "user_id": "user123",
        "message": "用户消息",
        "metadata": {...},
        "callback_url": "http://gateway:3000/gateway/webhook/kernel-response"
    }
    """
    memory_manager = get_memory_manager()
    
    try:
        request_id = request_data.get("request_id", str(uuid4()))
        session_id = request_data.get("session_id", str(uuid4()))
        callback_url = request_data.get("callback_url")
        
        if not callback_url:
            raise HTTPException(status_code=400, detail="callback_url is required")
        
        # Create request object
        request = Request(
            id=request_id,
            session_id=session_id,
            user_id=request_data["user_id"],
            message=request_data["message"],
            metadata=request_data.get("metadata", {}),
        )
        
        logger.info("Received execution request", 
                   request_id=request.id, 
                   session_id=request.session_id, 
                   user_id=request.user_id,
                   callback_url=callback_url)
        
        # Create session if not exists
        session = await memory_manager.get_session(request.session_id)
        if not session:
            session = Session(id=request.session_id, user_id=request.user_id)
            await memory_manager.save_session(session)
        
        # Save request as pending
        request.status = RequestStatus.PENDING
        await memory_manager.save_request(request)
        await memory_manager.save_event(
            request.session_id,
            {
                "timestamp": datetime.utcnow().isoformat(),
                "session_id": request.session_id,
                "request_id": request.id,
                "phase": "request_queued",
                "actor": "python_kernel",
                "summary": request.message,
                "status": "pending",
            },
        )
        
        # Start background processing
        background_tasks.add_task(process_request_async, request_id, callback_url)
        
        return {
            "request_id": request_id,
            "session_id": session_id,
            "status": "queued",
            "message": "Request queued for processing",
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to queue request", error=str(e))
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
