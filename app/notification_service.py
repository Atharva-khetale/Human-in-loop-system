import asyncio
from datetime import datetime
from typing import Dict, Any
from .models import ApprovalRequest, ApprovalResponse, WorkflowInstance

class NotificationService:
    """Simple notification service that works without external dependencies"""
    
    async def send_approval_notification(self, approval_request: ApprovalRequest):
        """Send approval notification (console-based for demo)"""
        print(f"\n🔔 APPROVAL REQUIRED 🔔")
        print(f"Workflow: {approval_request.metadata.get('workflow_name', 'Unknown')}")
        print(f"Step: {approval_request.metadata.get('step_name', 'Unknown')}")
        print(f"Approval Level: {approval_request.approval_level}")
        print(f"Request ID: {approval_request.id}")
        print(f"Go to: http://localhost:8000/approvals")
        print(f"Timeout: {approval_request.timeout_at}")
        print("=" * 50)
        
        # In production, this would send:
        # - Slack message via webhook
        # - Email via SMTP
        # - MS Teams notification
        # etc.

    async def send_approval_response_notification(self, approval_request_id: str, response: ApprovalResponse):
        """Send approval response notification"""
        print(f"\n✅ APPROVAL DECISION ✅")
        print(f"Request ID: {approval_request_id}")
        print(f"Decision: {response.action.value.upper()}")
        print(f"Approved by: {response.approved_by}")
        print(f"Comments: {response.comments or 'None'}")
        print(f"Time: {response.timestamp}")
        print("=" * 50)

    async def send_rollback_notification(self, workflow: WorkflowInstance, reason: str):
        """Send rollback notification"""
        print(f"\n🔄 ROLLBACK EXECUTED 🔄")
        print(f"Workflow: {workflow.name}")
        print(f"Reason: {reason}")
        print(f"Steps rolled back: {workflow.current_step}")
        print(f"Time: {datetime.now()}")
        print("=" * 50)

    async def send_workflow_completion_notification(self, workflow: WorkflowInstance):
        """Send workflow completion notification"""
        print(f"\n🎉 WORKFLOW COMPLETED 🎉")
        print(f"Workflow: {workflow.name}")
        print(f"Type: {workflow.task_type.value}")
        print(f"Completed at: {workflow.completed_at}")
        print(f"Total steps: {len(workflow.steps)}")

        print("=" * 50)
