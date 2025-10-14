import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, List
from models import WorkflowInstance, WorkflowStatus, WorkflowStep, ApprovalRequest
from database import DatabaseManager
from approval_manager import ApprovalManager
from rollback_engine import RollbackEngine
from task_processor import TaskProcessor

class WorkflowEngine:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.approval_manager = ApprovalManager(db_manager)
        self.rollback_engine = RollbackEngine(db_manager)
        self.task_processor = TaskProcessor()
        self.active_workflows: Dict[str, asyncio.Task] = {}

    async def start_workflow(self, workflow_id: str):
        """Start executing a workflow"""
        workflow_data = self.db.get_workflow(workflow_id)
        if not workflow_data:
            raise ValueError(f"Workflow {workflow_id} not found")
        
        workflow = WorkflowInstance(**workflow_data)
        workflow.status = WorkflowStatus.RUNNING
        workflow.started_at = datetime.now()
        
        self.db.update_workflow_status(workflow_id, workflow.status)
        
        # Start execution in background
        task = asyncio.create_task(self._execute_workflow(workflow))
        self.active_workflows[workflow_id] = task
        
        await self._log_event(workflow_id, "workflow_started", {
            "message": "Workflow execution started",
            "total_steps": len(workflow.steps)
        })

    async def _execute_workflow(self, workflow: WorkflowInstance):
        """Execute workflow steps sequentially"""
        try:
            for step_index, step in enumerate(workflow.steps):
                workflow.current_step = step_index
                self.db.update_workflow_status(workflow.id, workflow.status, step_index)
                
                await self._log_event(workflow.id, "step_started", {
                    "step_id": step.step_id,
                    "step_name": step.name,
                    "step_index": step_index
                })
                
                # Execute step action
                success = await self._execute_step(workflow, step)
                
                if not success:
                    await self._handle_step_failure(workflow, step)
                    break
                    
                await self._log_event(workflow.id, "step_completed", {
                    "step_id": step.step_id,
                    "step_name": step.name
                })
            
            if workflow.status == WorkflowStatus.RUNNING:
                workflow.status = WorkflowStatus.COMPLETED
                workflow.completed_at = datetime.now()
                self.db.update_workflow_status(workflow.id, workflow.status)
                
                await self._log_event(workflow.id, "workflow_completed", {
                    "message": "Workflow completed successfully",
                    "completion_time": workflow.completed_at.isoformat()
                })
                
        except Exception as e:
            await self._handle_workflow_failure(workflow, str(e))

    async def _execute_step(self, workflow: WorkflowInstance, step: WorkflowStep) -> bool:
        """Execute a single workflow step"""
        try:
            if step.requires_approval:
                # Create approval request
                approval_request = await self.approval_manager.create_approval_request(
                    workflow_id=workflow.id,
                    step_id=step.step_id,
                    approval_level=step.approval_level,
                    metadata={
                        "workflow_name": workflow.name,
                        "step_name": step.name,
                        "task_type": workflow.task_type,
                        "priority": workflow.priority
                    }
                )
                
                # Wait for approval
                approved = await self.approval_manager.wait_for_approval(
                    approval_request.id, 
                    timedelta(minutes=step.timeout_minutes)
                )
                
                if not approved:
                    await self._log_event(workflow.id, "approval_timeout", {
                        "step_id": step.step_id,
                        "approval_request_id": approval_request.id
                    })
                    return False
                    
            else:
                # Execute automated task
                result = await self.task_processor.execute_task(
                    step.action_type, 
                    workflow.metadata
                )
                
                if not result.get("success", False):
                    await self._log_event(workflow.id, "task_failed", {
                        "step_id": step.step_id,
                        "error": result.get("error", "Unknown error")
                    })
                    return False
            
            return True
            
        except Exception as e:
            await self._log_event(workflow.id, "step_execution_error", {
                "step_id": step.step_id,
                "error": str(e)
            })
            return False

    async def _handle_step_failure(self, workflow: WorkflowInstance, step: WorkflowStep):
        """Handle step failure with retry logic"""
        step.retry_count += 1
        
        if step.retry_count < 3:  # Max 3 retries
            await self._log_event(workflow.id, "step_retry", {
                "step_id": step.step_id,
                "retry_count": step.retry_count
            })
            # Retry the step
            await asyncio.sleep(5)  # Wait before retry
            await self._execute_step(workflow, step)
        else:
            await self._handle_workflow_failure(workflow, f"Step {step.name} failed after 3 retries")

    async def _handle_workflow_failure(self, workflow: WorkflowInstance, error: str):
        """Handle workflow failure and trigger rollback"""
        workflow.status = WorkflowStatus.FAILED
        self.db.update_workflow_status(workflow.id, workflow.status)
        
        await self._log_event(workflow.id, "workflow_failed", {
            "error": error,
            "failed_step": workflow.current_step
        })
        
        # Trigger rollback
        await self.rollback_engine.execute_rollback(workflow.id, workflow, error)

    async def _log_event(self, workflow_id: str, event_type: str, data: Dict[str, Any]):
        """Log workflow event"""
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "data": data
        }
        
        workflow = self.db.get_workflow(workflow_id)
        if workflow:
            workflow['execution_log'].append(event)
            # Update in database
            self.db.save_workflow(workflow)