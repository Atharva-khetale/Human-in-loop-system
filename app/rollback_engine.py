import asyncio
from datetime import datetime
from typing import Dict, Any
from models import WorkflowInstance, WorkflowStatus
from database import DatabaseManager
from notification_service import NotificationService

class RollbackEngine:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.notification_service = NotificationService()

    async def execute_rollback(self, workflow_id: str, workflow: WorkflowInstance, reason: str):
        """Execute rollback for a failed workflow"""
        try:
            await self._log_rollback_start(workflow_id, reason)
            
            # Create rollback snapshot
            rollback_data = await self._create_rollback_snapshot(workflow)
            
            # Execute compensation actions for completed steps
            for step_index in range(workflow.current_step, -1, -1):
                step = workflow.steps[step_index]
                await self._execute_compensation_action(workflow, step, step_index)
            
            # Update workflow status
            workflow.status = WorkflowStatus.ROLLED_BACK
            workflow.rollback_data = rollback_data
            
            self.db.update_workflow_status(workflow_id, workflow.status)
            
            await self._log_rollback_completion(workflow_id, rollback_data)
            
            # Send rollback notification
            await self.notification_service.send_rollback_notification(workflow, reason)
            
        except Exception as e:
            await self._log_rollback_failure(workflow_id, str(e))

    async def _create_rollback_snapshot(self, workflow: WorkflowInstance) -> Dict[str, Any]:
        """Create snapshot of current state for rollback"""
        return {
            "snapshot_timestamp": datetime.now().isoformat(),
            "workflow_state": workflow.dict(),
            "completed_steps": workflow.current_step,
            "execution_log": workflow.execution_log[-10:],  # Last 10 events
            "metadata_snapshot": workflow.metadata.copy()
        }

    async def _execute_compensation_action(self, workflow: WorkflowInstance, step: Any, step_index: int):
        """Execute compensation action for a specific step"""
        compensation_actions = {
            "process_data": self._compensate_data_processing,
            "fraud_detection": self._compensate_fraud_check,
            "deploy_system": self._compensate_deployment,
            "validate_data": self._compensate_validation
        }
        
        action_func = compensation_actions.get(step.action_type, self._generic_compensation)
        await action_func(workflow, step, step_index)
        
        await asyncio.sleep(1)  # Simulate compensation time

    async def _compensate_data_processing(self, workflow: WorkflowInstance, step: Any, step_index: int):
        """Compensate for data processing step"""
        await self._log_compensation_action(
            workflow.id, step.step_id, "data_processing_rollback",
            {"message": "Reverted data processing changes", "step_index": step_index}
        )

    async def _compensate_fraud_check(self, workflow: WorkflowInstance, step: Any, step_index: int):
        """Compensate for fraud detection step"""
        await self._log_compensation_action(
            workflow.id, step.step_id, "fraud_check_rollback",
            {"message": "Reset fraud detection flags", "step_index": step_index}
        )

    async def _compensate_deployment(self, workflow: WorkflowInstance, step: Any, step_index: int):
        """Compensate for system deployment"""
        await self._log_compensation_action(
            workflow.id, step.step_id, "deployment_rollback",
            {"message": "Rolled back deployment to previous version", "step_index": step_index}
        )

    async def _compensate_validation(self, workflow: WorkflowInstance, step: Any, step_index: int):
        """Compensate for validation step"""
        await self._log_compensation_action(
            workflow.id, step.step_id, "validation_rollback", 
            {"message": "Reset validation status", "step_index": step_index}
        )

    async def _generic_compensation(self, workflow: WorkflowInstance, step: Any, step_index: int):
        """Generic compensation action"""
        await self._log_compensation_action(
            workflow.id, step.step_id, "generic_rollback",
            {"message": "Executed generic rollback action", "step_index": step_index}
        )

    async def _log_rollback_start(self, workflow_id: str, reason: str):
        """Log rollback initiation"""
        await self._log_compensation_action(
            workflow_id, "system", "rollback_started",
            {"reason": reason, "timestamp": datetime.now().isoformat()}
        )

    async def _log_rollback_completion(self, workflow_id: str, rollback_data: Dict[str, Any]):
        """Log rollback completion"""
        await self._log_compensation_action(
            workflow_id, "system", "rollback_completed",
            {"snapshot_timestamp": rollback_data["snapshot_timestamp"]}
        )

    async def _log_rollback_failure(self, workflow_id: str, error: str):
        """Log rollback failure"""
        await self._log_compensation_action(
            workflow_id, "system", "rollback_failed",
            {"error": error, "timestamp": datetime.now().isoformat()}
        )

    async def _log_compensation_action(self, workflow_id: str, step_id: str, action_type: str, data: Dict[str, Any]):
        """Log compensation action"""
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": action_type,
            "step_id": step_id,
            "data": data
        }
        
        workflow = self.db.get_workflow(workflow_id)
        if workflow:
            workflow['execution_log'].append(event)
            self.db.save_workflow(workflow)