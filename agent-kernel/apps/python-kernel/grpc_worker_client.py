"""
gRPC Worker Client for Python Kernel.

Architecture:
- Request Manager pushes tasks via gRPC Server Stream (StreamTasks)
- Kernel processes tasks and sends HTTP callback to Gateway via skill
- Kernel notifies Request Manager via TaskComplete (for scheduling only)

This removes the need for Request Manager to forward responses to Gateway.
"""

import asyncio
import json
import os
import sys
import traceback
from datetime import datetime
from typing import Optional

import grpc
import structlog

# Add project root to path for skills import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from grpc_generated import request_manager_pb2
from grpc_generated import request_manager_pb2_grpc

logger = structlog.get_logger()

# Import Gateway callback skill
# skills目录在项目根目录 (/home/eziothean/ProClaw/skills)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(project_root, 'skills'))
sys.path.insert(0, os.path.join(project_root, 'skills', 'system-skills'))

try:
    from system_skills import get_callback_skill
except ImportError as e:
    logger.warning(f"Could not import system_skills: {e}, using fallback")
    # Fallback: import directly from file
    import importlib.util
    skill_path = os.path.join(project_root, 'skills', 'system-skills', 'gateway_callback_skill.py')
    spec = importlib.util.spec_from_file_location("gateway_callback_skill", skill_path)
    if spec and spec.loader:
        gateway_callback_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gateway_callback_module)
        get_callback_skill = gateway_callback_module.get_callback_skill
    else:
        raise ImportError(f"Could not load gateway_callback_skill from {skill_path}")


class GRPCWorkerClient:
    """
    gRPC Worker client that receives tasks and sends HTTP callbacks to Gateway.
    """
    
    def __init__(
        self,
        request_manager_address: str = "localhost:50052",
        worker_id: Optional[str] = None,
    ):
        self.address = request_manager_address
        self.worker_id = worker_id or f"kernel-{os.getpid()}"
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub: Optional[request_manager_pb2_grpc.KernelWorkerStub] = None
        self._running = False
        self._stream_task: Optional[asyncio.Task] = None
        self._process_request_func = None
        
        # Gateway callback skill
        self._callback_skill = None
        
    def set_process_request_func(self, func):
        """Set request processing function"""
        self._process_request_func = func
        
    async def start(self) -> None:
        """Start worker client"""
        if self._running:
            logger.warning("gRPC Worker already running")
            return
            
        self._running = True
        
        # Initialize callback skill
        self._callback_skill = get_callback_skill()
        
        # Create gRPC channel
        self.channel = grpc.aio.insecure_channel(self.address)
        self.stub = request_manager_pb2_grpc.KernelWorkerStub(self.channel)
        
        # Wait for connection
        try:
            await asyncio.wait_for(self.channel.channel_ready(), timeout=5.0)
            logger.info("Connected to Request Manager", address=self.address)
        except asyncio.TimeoutError:
            logger.error("Failed to connect to Request Manager", address=self.address)
            raise
            
        # Start task stream receiver
        self._stream_task = asyncio.create_task(self._receive_tasks())
        logger.info("gRPC Worker client started", worker_id=self.worker_id)
        
    async def stop(self) -> None:
        """Stop worker client"""
        if not self._running:
            return
            
        self._running = False
        logger.info("Stopping gRPC Worker client")
        
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
                
        if self.channel:
            await self.channel.close()
            
        # Close callback skill
        if self._callback_skill:
            await self._callback_skill.close()
            
        logger.info("gRPC Worker client stopped")
        
    async def _receive_tasks(self) -> None:
        """Main loop for receiving task stream"""
        while self._running:
            try:
                # Create connection request
                connect_request = request_manager_pb2.WorkerConnectRequest(
                    worker_id=self.worker_id,
                    capacity=1,  # Process one task at a time for now
                )
                
                # Subscribe to task stream
                async for task in self.stub.StreamTasks(connect_request):
                    if not self._running:
                        break
                        
                    logger.info(
                        "Received task from Request Manager",
                        request_id=task.request_id,
                        session_id=task.session_id
                    )
                    
                    # Process task asynchronously
                    asyncio.create_task(
                        self._handle_task_with_http_callback(task)
                    )
                    
            except grpc.aio.AioRpcError as e:
                logger.error(
                    "gRPC stream error",
                    error=str(e),
                    code=e.code() if hasattr(e, 'code') else 'unknown'
                )
                await asyncio.sleep(5.0)
            except Exception as e:
                logger.error(
                    "Task receiver error",
                    error=str(e),
                    traceback=traceback.format_exc()
                )
                await asyncio.sleep(5.0)
                
    async def _handle_task_with_http_callback(
        self,
        task: request_manager_pb2.KernelTask,
    ) -> None:
        """
        Process task and send HTTP callback to Gateway.
        Then notify Request Manager via TaskComplete.
        """
        request_id = task.request_id
        start_time = datetime.utcnow()
        success = False
        error_msg = ""
        
        try:
            # Process the task
            if self._process_request_func:
                result = await self._process_request_func(
                    request_id=request_id,
                    session_id=task.session_id,
                    user_id=task.user_id,
                    body=task.body,
                    metadata=dict(task.metadata),
                )
                
                processing_time_ms = int(
                    (datetime.utcnow() - start_time).total_seconds() * 1000
                )
                
                # Send HTTP callback to Gateway
                if result.get("status") == "completed":
                    callback_success = await self._callback_skill.send_completion(
                        request_id=request_id,
                        session_id=task.session_id,
                        output=result.get("output", ""),
                        actions=result.get("actions", []),
                        processing_time_ms=processing_time_ms,
                    )
                    success = callback_success
                else:
                    callback_success = await self._callback_skill.send_error(
                        request_id=request_id,
                        session_id=task.session_id,
                        error_message=result.get("error", "Unknown error"),
                        error_category=result.get("error_category", "system_error"),
                        error_code=result.get("error_code", "INTERNAL_ERROR"),
                        recoverable=result.get("recoverable", False),
                        processing_time_ms=processing_time_ms,
                    )
                    success = False
                    error_msg = result.get("error", "Unknown error")
                
                logger.info(
                    "Task processed and callback sent",
                    request_id=request_id,
                    status=result.get("status"),
                    callback_success=success
                )
            else:
                logger.error("No request processor configured")
                error_msg = "No request processor configured"
                
        except Exception as e:
            logger.error(
                "Task processing failed",
                request_id=request_id,
                error=str(e),
                traceback=traceback.format_exc()
            )
            
            # Send error callback
            processing_time_ms = int(
                (datetime.utcnow() - start_time).total_seconds() * 1000
            )
            await self._callback_skill.send_error(
                request_id=request_id,
                session_id=task.session_id,
                error_message=str(e),
                processing_time_ms=processing_time_ms,
            )
            success = False
            error_msg = str(e)
        
        finally:
            # Notify Request Manager that task is complete (for scheduling purposes)
            await self._notify_task_complete(request_id, success, error_msg)
    
    async def _notify_task_complete(self, request_id: str, success: bool, error_message: str = "") -> None:
        """
        Notify Request Manager that task is complete via TaskComplete RPC.
        This is only for scheduling decisions, not for forwarding response.
        """
        try:
            request = request_manager_pb2.TaskCompleteRequest(
                request_id=request_id,
                success=success,
                error_message=error_message,
            )
            response = await self.stub.TaskComplete(request)
            
            if response.acknowledged:
                logger.debug(
                    "Request Manager acknowledged task completion",
                    request_id=request_id,
                    success=success
                )
            else:
                logger.warning(
                    "Request Manager did not acknowledge task completion",
                    request_id=request_id
                )
                
        except Exception as e:
            logger.warning(
                "Failed to notify Request Manager of task completion",
                request_id=request_id,
                error=str(e)
            )
        
    async def send_heartbeat(self) -> bool:
        """Send heartbeat to Request Manager"""
        if not self.stub:
            return False
            
        try:
            request = request_manager_pb2.HeartbeatRequest(
                worker_id=self.worker_id,
                active_tasks=0,
                available_slots=1,
            )
            response = await self.stub.Heartbeat(request)
            return response.acknowledged
        except Exception as e:
            logger.warning("Heartbeat failed", error=str(e))
            return False


# Global worker client instance
_worker_client: Optional[GRPCWorkerClient] = None


def get_worker_client() -> GRPCWorkerClient:
    """Get global worker client instance"""
    global _worker_client
    if _worker_client is None:
        address = os.environ.get("REQUEST_MANAGER_GRPC_ADDRESS", "localhost:50052")
        _worker_client = GRPCWorkerClient(address)
    return _worker_client