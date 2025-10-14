import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from models import ApprovalRequest, ApprovalResponse, ApprovalAction
from database import DatabaseManager
from notification_service import NotificationService

class ApprovalManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.notification_service = NotificationService()
        self.pending_approvals: Dict[str, asyncio.Event] = {}

    async def create_approval_request(self, workflow_id: str, step_id: str, 
                                   approval_level: int, metadata: Dict[str, Any]) -> ApprovalRequest:
        """Create a new approval request"""
        approval_request = ApprovalRequest(
            id=str(uuid.uuid4()),
            workflow_id=workflow_id,
            step_id=step_id,
            requested_at=datetime.now(),
            requested_by="system",
            approval_level=approval_level,
            metadata=metadata,
            timeout_at=datetime.now() + timedelta(hours=24)
        )
        
        # Save to database
        with self.db._get_connection() as conn:
            conn.execute('''
                INSERT INTO approval_requests 
                (id, workflow_id, step_id, requested_at, requested_by, approval_level, metadata, timeout_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                approval_request.id,
                approval_request.workflow_id,
                approval_request.step_id,
                approval_request.requested_at.isoformat(),
                approval_request.requested_by,
                approval_request.approval_level,
                str(approval_request.metadata),
                approval_request.timeout_at.isoformat()
            ))
            conn.commit()
        
        # Create event for waiting
        self.pending_approvals[approval_request.id] = asyncio.Event()
        
        # Send notifications
        await self.notification_service.send_approval_notification(approval_request)
        
        return approval_request

    async def wait_for_approval(self, approval_request_id: str, timeout: timedelta) -> bool:
        """Wait for approval decision with timeout"""
        if approval_request_id not in self.pending_approvals:
            return False
        
        try:
            await asyncio.wait_for(
                self.pending_approvals[approval_request_id].wait(),
                timeout=timeout.total_seconds()
            )
            return True
        except asyncio.TimeoutError:
            return False

    async def submit_approval_response(self, approval_request_id: str, response: ApprovalResponse) -> bool:
        """Submit approval decision"""
        # Save response to database
        with self.db._get_connection() as conn:
            conn.execute('''
                INSERT INTO approval_responses 
                (id, approval_request_id, action, approved_by, comments, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                str(uuid.uuid4()),
                approval_request_id,
                response.action.value,
                response.approved_by,
                response.comments,
                response.timestamp.isoformat()
            ))
            
            # Update approval request status
            conn.execute('''
                UPDATE approval_requests 
                SET status = ?
                WHERE id = ?
            ''', (response.action.value, approval_request_id))
            
            conn.commit()
        
        # Notify waiting workflow
        if approval_request_id in self.pending_approvals:
            self.pending_approvals[approval_request_id].set()
            del self.pending_approvals[approval_request_id]
        
        # Send response notification
        await self.notification_service.send_approval_response_notification(
            approval_request_id, response
        )
        
        return True

    async def get_pending_approvals(self) -> list[Dict[str, Any]]:
        """Get all pending approval requests"""
        with self.db._get_connection() as conn:
            rows = conn.execute('''
                SELECT ar.*, w.name as workflow_name, w.task_type 
                FROM approval_requests ar
                JOIN workflows w ON ar.workflow_id = w.id
                WHERE ar.status = 'pending'
                ORDER BY ar.requested_at DESC
            ''').fetchall()
            
            approvals = []
            for row in rows:
                approval = dict(row)
                approval['metadata'] = eval(approval['metadata']) if approval['metadata'] else {}
                approvals.append(approval)
            
            return approvals