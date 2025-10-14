from enum import Enum
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime
from decimal import Decimal

class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskType(str, Enum):
    DATA_PROCESSING = "data_processing"
    PAYMENT_PROCESSING = "payment_processing"
    USER_ONBOARDING = "user_onboarding"
    SYSTEM_DEPLOYMENT = "system_deployment"
    SECURITY_REVIEW = "security_review"

class ApprovalAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request_changes"

class WorkflowStep(BaseModel):
    step_id: str
    name: str
    description: str
    action_type: str
    requires_approval: bool = False
    approval_level: int = 1
    timeout_minutes: int = 60
    retry_count: int = 0
    metadata: Dict[str, Any] = {}

class WorkflowCreate(BaseModel):
    name: str
    description: str
    task_type: TaskType
    priority: int = 1
    steps: List[WorkflowStep]
    metadata: Dict[str, Any] = {}

class WorkflowInstance(BaseModel):
    id: str
    name: str
    description: str
    task_type: TaskType
    status: WorkflowStatus
    current_step: int = 0
    priority: int = 1
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    steps: List[WorkflowStep]
    metadata: Dict[str, Any] = {}
    execution_log: List[Dict[str, Any]] = []
    rollback_data: Optional[Dict[str, Any]] = None

class ApprovalRequest(BaseModel):
    id: str
    workflow_id: str
    step_id: str
    requested_at: datetime
    requested_by: str
    approval_level: int
    metadata: Dict[str, Any] = {}
    timeout_at: datetime

class ApprovalResponse(BaseModel):
    approval_request_id: str
    action: ApprovalAction
    approved_by: str
    comments: Optional[str] = None
    timestamp: datetime

class CSVTasks(BaseModel):
    task_id: str
    task_type: TaskType
    name: str
    description: str
    priority: int
    data: Dict[str, Any]
    scheduled_time: Optional[datetime] = None