"""
Agent Kernel Python Intelligence Layer.
"""
import asyncio
import json
import os
import time
import traceback
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
from uuid import uuid4

import structlog
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from context_compiler.master_compiler import get_master_compiler
from executors_client.directory_lock_manager import get_directory_lock_manager
from grpc_worker_client import get_worker_client
from kernel_init import initialize_kernel, shutdown_kernel
from personality.prime_personality import get_prime_personality
from schemas.models import HealthCheck, Request, RequestStatus, Session
from scheduled_dispatcher import ScheduledRequestStorage, ScheduledRequestDispatcher
from session_host.session_host import get_session_host
from storage.runtime_store import get_memory_manager
from thread_runtime.scheduler import get_scheduler
from telemetry import get_telemetry_emitter

logger = structlog.get_logger()

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
    
    # Start gRPC Worker client (replaces inbox watcher polling)
    worker_client = get_worker_client()
    worker_client.set_process_request_func(process_request_grpc)
    await worker_client.start()
    
    # Start scheduled request dispatcher
    # Note: Scheduled tasks still write to inbox for now (separate concern from main request flow)
    global _scheduled_dispatcher
    scheduled_storage = ScheduledRequestStorage(base_path=os.environ.get("DATA_PATH", "./data"))
    _scheduled_dispatcher = ScheduledRequestDispatcher(
        storage=scheduled_storage,
        inbox_path=os.environ.get("GATEWAY_INBOX_PATH", "./data/gateway/inbox"),
        check_interval=float(os.environ.get("SCHEDULER_CHECK_INTERVAL", "60")),
    )
    await _scheduled_dispatcher.start()
    
    # Start telemetry emitter
    telemetry_emitter = get_telemetry_emitter()
    await telemetry_emitter.start()
    
    logger.info("Python Kernel ready")
    yield
    
    logger.info("Shutting down Python Kernel")
    worker_client = get_worker_client()
    await worker_client.stop()
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
    
    # Stop telemetry emitter
    telemetry_emitter = get_telemetry_emitter()
    await telemetry_emitter.stop()
    
    # Shutdown kernel gracefully
    await shutdown_kernel()
    
    await memory_manager.close()
    logger.info("Python Kernel stopped")


async def process_request_grpc(
    request_id: str,
    session_id: str,
    user_id: str,
    body: str,
    metadata: dict,
) -> dict:
    """
    gRPC专用的请求处理函数。
    
    替代原来的HTTP回调方式，直接返回结果给Request Manager。
    """
    started_at = time.perf_counter()
    memory_manager = get_memory_manager()
    request: Request | None = None
    
    try:
        # 创建临时Request对象用于处理
        request = Request(
            id=request_id,
            session_id=session_id,
            user_id=user_id,
            message=body,
            metadata=metadata,
        )
        
        # 保存请求到存储
        await memory_manager.save_request(request)
        
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
        
        master_context = await get_master_compiler().compile(
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
            session_context=master_context.model_dump() if hasattr(master_context, 'model_dump') else master_context
        )
        
        # FAST PATH: Simple conversation without capabilities - skip Session Host
        has_complex_tasks = any(
            len(p.get("capabilities", [])) > 0 or p.get("name") not in ["respond", "conversation"]
            for p in intermediate_repr.processes
        )
        
        if intermediate_repr.intent == "conversation" and not has_complex_tasks:
            logger.info(
                "Fast path for conversation - skipping Session Host",
                request_id=request_id,
                process_count=len(intermediate_repr.processes)
            )
            
            # Generate direct response using LLM
            from llm_client import get_llm_client
            client = get_llm_client()
            client.initialize(system_prompt="You are a helpful AI assistant.")
            
            response_text = await client.generate(request.message)
            
            result = {
                "status": "completed",
                "output": response_text,
                "actions": [],
            }
        else:
            # SLOW PATH: Complex tasks - use full Session Host execution
            result = await get_session_host(session).handle_request(request, intermediate_repr)
        
        # Update request status
        request.status = RequestStatus.COMPLETED if result["status"] == "completed" else RequestStatus.FAILED
        request.completed_at = datetime.utcnow()
        await memory_manager.save_request(request)
        
        # Build result for gRPC response
        processing_time_ms = int((time.perf_counter() - started_at) * 1000)
        
        return {
            "status": result["status"],
            "output": result.get("output", ""),
            "actions": result.get("actions", []),
            "processing_time_ms": processing_time_ms,
            "error": result.get("error") if result["status"] != "completed" else None,
            "error_category": result.get("error_category"),
            "error_code": result.get("error_code"),
            "recoverable": result.get("recoverable", False),
        }
        
    except Exception as e:
        logger.error("Request processing failed", 
                    request_id=request_id, 
                    error=str(e),
                    traceback=traceback.format_exc())
        
        if request:
            request.status = RequestStatus.FAILED
            request.completed_at = datetime.utcnow()
            await memory_manager.save_request(request)
        
        # Return error result for gRPC
        return {
            "status": "failed",
            "error": str(e),
            "error_category": "system_error",
            "error_code": "INTERNAL_ERROR",
            "recoverable": False,
            "output": "",
            "actions": [],
        }


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
        "mode": "grpc_worker",
        "scheduled_dispatcher": "running" if _scheduled_dispatcher and _scheduled_dispatcher._running else "stopped",
    }
    
    if _scheduled_dispatcher:
        stats = _scheduled_dispatcher.get_statistics()
        components["scheduled_request_stats"] = json.dumps(stats)
    
    return HealthCheck(
        status="healthy",
        version="0.1.0",
        timestamp=datetime.utcnow(),
        components=components,
    )


@app.post("/v1/shutdown")
async def shutdown_service(background_tasks: BackgroundTasks):
    """
    优雅关闭服务。
    
    给当前正在处理的请求10秒完成，然后退出。
    """
    timeout_seconds = 10
    logger.info(f"Shutdown requested, will wait {timeout_seconds}s for active requests")
    
    # 创建一个任务来执行延迟关闭
    async def delayed_shutdown():
        await asyncio.sleep(timeout_seconds)
        logger.info("Shutdown timeout reached, exiting")
        os._exit(0)
    
    background_tasks.add_task(delayed_shutdown)
    
    return {
        "status": "shutting_down",
        "timeout_seconds": timeout_seconds,
        "message": f"Service will shutdown in {timeout_seconds} seconds",
    }


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
