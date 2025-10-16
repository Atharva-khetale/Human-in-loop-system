import asyncio
from typing import Dict, Any
from .models import WorkflowInstance, WorkflowStep


class NotificationService:
    async def send_approval_request(self, workflow_id: str, workflow: WorkflowInstance, step: WorkflowStep):
        """Send approval request (mock implementation)"""
        approval_url = f"http://localhost:8000/approve/{workflow_id}"

        print(f"\n=== APPROVAL REQUIRED ===")
        print(f"Workflow: {workflow.name}")
        print(f"Step: {step.name}")
        print(f"Description: {step.approval_prompt or 'Approval required to continue'}")
        print(f"Approval URL: {approval_url}")
        print(f"==========================\n")

        # In real implementation, this would send:
        # - Slack message
        # - Email
        # - MS Teams notification
        # etc.

    async def send_approval_notification(self, workflow_id: str, decision: str, reason: str = None):
        """Send approval decision notification"""
        print(f"\n=== APPROVAL DECISION ===")
        print(f"Workflow: {workflow_id}")
        print(f"Decision: {decision.upper()}")
        print(f"Reason: {reason or 'No reason provided'}")
        print(f"==========================\n")

    async def send_notification(self, workflow: WorkflowInstance, step: WorkflowStep):
        """Send general notification"""
        print(f"Notification: {step.name} - {workflow.name}")

        await asyncio.sleep(0.2)  # Simulate notification delay
