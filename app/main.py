"""
AUTOMATED HUMAN-IN-LOOP SYSTEM v3.0
Fully automated workflows from CSV with timed approval intervals
"""

from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from contextlib import asynccontextmanager
import asyncio
import uuid
import json
import sqlite3
import pandas as pd
import os
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel
import random
import time

# ===== DATA MODELS =====
class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"

class TaskType(str, Enum):
    DATA_PROCESSING = "data_processing"
    PAYMENT_PROCESSING = "payment_processing"
    USER_ONBOARDING = "user_onboarding"
    SYSTEM_DEPLOYMENT = "system_deployment"
    SECURITY_REVIEW = "security_review"

class ApprovalAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"

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

# ===== DATABASE MANAGER =====
class DatabaseManager:
    def __init__(self, db_path: str = "workflows.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                task_type TEXT NOT NULL,
                status TEXT NOT NULL,
                current_step INTEGER DEFAULT 0,
                priority INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                steps TEXT NOT NULL,
                metadata TEXT NOT NULL,
                execution_log TEXT NOT NULL,
                rollback_data TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS approval_requests (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                requested_by TEXT NOT NULL,
                approval_level INTEGER DEFAULT 1,
                metadata TEXT NOT NULL,
                timeout_at TIMESTAMP,
                status TEXT DEFAULT 'pending'
            )
        ''')
        conn.commit()
        conn.close()

    def save_workflow(self, workflow: Dict[str, Any]) -> str:
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            INSERT INTO workflows 
            (id, name, description, task_type, status, current_step, priority, 
             created_at, steps, metadata, execution_log, rollback_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            workflow['id'],
            workflow['name'],
            workflow['description'],
            workflow['task_type'],
            workflow['status'],
            workflow['current_step'],
            workflow['priority'],
            workflow['created_at'].isoformat(),
            json.dumps([step.dict() for step in workflow['steps']]),
            json.dumps(workflow['metadata']),
            json.dumps(workflow['execution_log']),
            json.dumps(workflow.get('rollback_data'))
        ))
        conn.commit()
        conn.close()
        return workflow['id']

    def update_workflow_status(self, workflow_id: str, status: str, current_step: int = None):
        conn = sqlite3.connect(self.db_path)
        if current_step is not None:
            conn.execute('UPDATE workflows SET status = ?, current_step = ? WHERE id = ?',
                        (status, current_step, workflow_id))
        else:
            conn.execute('UPDATE workflows SET status = ? WHERE id = ?', (status, workflow_id))
        conn.commit()
        conn.close()

    def get_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute('SELECT * FROM workflows WHERE id = ?', (workflow_id,)).fetchone()
        conn.close()

        if row:
            data = dict(row)
            data['steps'] = json.loads(data['steps'])
            data['metadata'] = json.loads(data['metadata'])
            data['execution_log'] = json.loads(data['execution_log'])
            if data.get('rollback_data'):
                data['rollback_data'] = json.loads(data['rollback_data'])
            return data
        return None

    def get_all_workflows(self) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute('SELECT * FROM workflows ORDER BY created_at DESC').fetchall()
        conn.close()

        workflows = []
        for row in rows:
            data = dict(row)
            data['steps'] = json.loads(data['steps'])
            data['metadata'] = json.loads(data['metadata'])
            data['execution_log'] = json.loads(data['execution_log'])
            if data.get('rollback_data'):
                data['rollback_data'] = json.loads(data['rollback_data'])
            workflows.append(data)

        return workflows

    def save_approval_request(self, approval: ApprovalRequest):
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            INSERT INTO approval_requests 
            (id, workflow_id, step_id, requested_at, requested_by, approval_level, metadata, timeout_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            approval.id,
            approval.workflow_id,
            approval.step_id,
            approval.requested_at.isoformat(),
            approval.requested_by,
            approval.approval_level,
            json.dumps(approval.metadata),
            approval.timeout_at.isoformat()
        ))
        conn.commit()
        conn.close()

    def get_pending_approvals(self) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute('''
            SELECT ar.*, w.name as workflow_name, w.task_type 
            FROM approval_requests ar
            JOIN workflows w ON ar.workflow_id = w.id
            WHERE ar.status = 'pending'
            ORDER BY ar.requested_at DESC
        ''').fetchall()
        conn.close()

        approvals = []
        for row in rows:
            approval = dict(row)
            approval['metadata'] = json.loads(approval['metadata'])
            approvals.append(approval)

        return approvals

    def update_approval_status(self, approval_id: str, status: str):
        conn = sqlite3.connect(self.db_path)
        conn.execute('UPDATE approval_requests SET status = ? WHERE id = ?', (status, approval_id))
        conn.commit()
        conn.close()

# ===== AUTOMATED WORKFLOW ENGINE =====
class AutomatedWorkflowEngine:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.active_workflows: Dict[str, asyncio.Task] = {}
        self.approval_events: Dict[str, asyncio.Event] = {}

    async def start_workflow_automation(self):
        """Start automated workflow processing"""
        while True:
            try:
                # Process pending workflows
                await self._process_pending_workflows()

                # Check for approval timeouts
                await self._check_approval_timeouts()

                # Wait before next cycle
                await asyncio.sleep(10)  # Check every 10 seconds

            except Exception as e:
                print(f"Error in workflow automation: {e}")
                await asyncio.sleep(30)

    async def _process_pending_workflows(self):
        """Process workflows that are ready to run"""
        workflows = self.db.get_all_workflows()

        for workflow_data in workflows:
            if workflow_data['status'] == WorkflowStatus.PENDING:
                await self._start_workflow_execution(workflow_data)
            elif workflow_data['status'] == WorkflowStatus.AWAITING_APPROVAL:
                await self._check_workflow_approval(workflow_data)

    async def _start_workflow_execution(self, workflow_data: Dict[str, Any]):
        """Start executing a workflow"""
        workflow_id = workflow_data['id']

        if workflow_id in self.active_workflows:
            return  # Already running

        print(f"🚀 Starting automated workflow: {workflow_data['name']}")

        workflow = WorkflowInstance(**workflow_data)
        workflow.status = WorkflowStatus.RUNNING
        workflow.started_at = datetime.now()

        self.db.update_workflow_status(workflow_id, workflow.status)

        # Start execution in background
        task = asyncio.create_task(self._execute_workflow_steps(workflow))
        self.active_workflows[workflow_id] = task

    async def _execute_workflow_steps(self, workflow: WorkflowInstance):
        """Execute workflow steps with automated intervals"""
        try:
            for step_index, step in enumerate(workflow.steps[workflow.current_step:], workflow.current_step):
                workflow.current_step = step_index
                self.db.update_workflow_status(workflow.id, workflow.status, step_index)

                print(f"🔧 Executing step {step_index + 1}/{len(workflow.steps)}: {step.name}")

                # Add random delay between steps (1-5 seconds) to simulate real processing
                processing_time = random.uniform(1.0, 5.0)
                await asyncio.sleep(processing_time)

                if step.requires_approval:
                    # Move to approval state
                    workflow.status = WorkflowStatus.AWAITING_APPROVAL
                    self.db.update_workflow_status(workflow.id, workflow.status, step_index)

                    # Create approval request
                    approval_request = ApprovalRequest(
                        id=str(uuid.uuid4()),
                        workflow_id=workflow.id,
                        step_id=step.step_id,
                        requested_at=datetime.now(),
                        requested_by="system",
                        approval_level=step.approval_level,
                        metadata={
                            "workflow_name": workflow.name,
                            "step_name": step.name,
                            "task_type": workflow.task_type,
                            "priority": workflow.priority,
                            "step_index": step_index
                        },
                        timeout_at=datetime.now() + timedelta(minutes=step.timeout_minutes)
                    )

                    self.db.save_approval_request(approval_request)
                    self.approval_events[approval_request.id] = asyncio.Event()

                    print(f"⏳ Waiting for approval: {step.name}")
                    print(f"   Approval ID: {approval_request.id}")
                    print(f"   Timeout: {step.timeout_minutes} minutes")

                    # Wait for approval with timeout
                    try:
                        await asyncio.wait_for(
                            self.approval_events[approval_request.id].wait(),
                            timeout=step.timeout_minutes * 60
                        )
                        print(f"✅ Approval received for: {step.name}")
                    except asyncio.TimeoutError:
                        print(f"❌ Approval timeout for: {step.name}")
                        workflow.status = WorkflowStatus.FAILED
                        self.db.update_workflow_status(workflow.id, workflow.status)
                        break

                else:
                    # Execute automated task
                    success = await self._execute_automated_task(step, workflow.metadata)
                    if not success:
                        workflow.status = WorkflowStatus.FAILED
                        self.db.update_workflow_status(workflow.id, workflow.status)
                        break

                # Log step completion
                await self._log_event(workflow.id, "step_completed", {
                    "step_id": step.step_id,
                    "step_name": step.name,
                    "step_index": step_index
                })

            # If all steps completed successfully
            if workflow.status == WorkflowStatus.RUNNING:
                workflow.status = WorkflowStatus.COMPLETED
                workflow.completed_at = datetime.now()
                self.db.update_workflow_status(workflow.id, workflow.status)
                print(f"🎉 Workflow completed: {workflow.name}")

                await self._log_event(workflow.id, "workflow_completed", {
                    "message": "Workflow completed successfully",
                    "total_steps": len(workflow.steps)
                })

        except Exception as e:
            print(f"❌ Workflow execution failed: {e}")
            workflow.status = WorkflowStatus.FAILED
            self.db.update_workflow_status(workflow.id, workflow.status)

            await self._log_event(workflow.id, "workflow_failed", {
                "error": str(e),
                "failed_step": workflow.current_step
            })

        finally:
            # Clean up
            if workflow.id in self.active_workflows:
                del self.active_workflows[workflow.id]

    async def _execute_automated_task(self, step: WorkflowStep, metadata: Dict[str, Any]) -> bool:
        """Execute automated task with realistic processing"""
        try:
            # Simulate different task types
            if "validate" in step.action_type:
                print(f"   ✅ Validating data...")
                await asyncio.sleep(2)
                return True

            elif "process" in step.action_type:
                print(f"   🔄 Processing data...")
                await asyncio.sleep(3)
                return True

            elif "fraud" in step.action_type:
                print(f"   🔍 Running fraud detection...")
                await asyncio.sleep(4)
                # Simulate random fraud detection results
                is_suspicious = random.random() < 0.3  # 30% chance of suspicion
                if is_suspicious:
                    print(f"   ⚠️  Suspicious activity detected!")
                return True

            elif "deploy" in step.action_type:
                print(f"   🚀 Deploying system...")
                await asyncio.sleep(5)
                return True

            else:
                print(f"   ⚙️  Executing {step.action_type}...")
                await asyncio.sleep(2)
                return True

        except Exception as e:
            print(f"   ❌ Task execution failed: {e}")
            return False

    async def _check_workflow_approval(self, workflow_data: Dict[str, Any]):
        """Check if workflow has pending approvals that need attention"""
        # This method can be extended for approval reminder logic
        pass

    async def _check_approval_timeouts(self):
        """Check and handle approval timeouts"""
        approvals = self.db.get_pending_approvals()
        now = datetime.now()

        for approval in approvals:
            timeout_at = datetime.fromisoformat(approval['timeout_at'])
            if now > timeout_at:
                print(f"⏰ Approval timeout: {approval['id']}")
                self.db.update_approval_status(approval['id'], 'timeout')

                # If the approval event exists, set it to break the wait
                if approval['id'] in self.approval_events:
                    self.approval_events[approval['id']].set()

    async def submit_approval_decision(self, approval_request_id: str, decision: ApprovalAction, approved_by: str, comments: str = None):
        """Submit approval decision"""
        if approval_request_id in self.approval_events:
            self.approval_events[approval_request_id].set()
            self.db.update_approval_status(approval_request_id, decision.value)

            print(f"✅ Approval decision submitted: {decision.value} by {approved_by}")
            return True
        return False

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
            self.db.save_workflow(workflow)

# ===== CSV AUTOMATION ENGINE =====
class CSVAutomation:
    def __init__(self, db_manager: DatabaseManager, workflow_engine: AutomatedWorkflowEngine):
        self.db = db_manager
        self.workflow_engine = workflow_engine
        self.data_dir = "data"
        self.processed_dir = os.path.join(self.data_dir, "processed")

        # Create directories
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.processed_dir, exist_ok=True)

    async def start_csv_monitoring(self):
        """Start monitoring CSV files for automated workflow creation"""
        print("📁 Starting CSV file monitoring...")

        while True:
            try:
                await self._process_csv_files()
                await asyncio.sleep(15)  # Check every 15 seconds
            except Exception as e:
                print(f"❌ CSV monitoring error: {e}")
                await asyncio.sleep(30)

    async def _process_csv_files(self):
        """Process all CSV files in data directory"""
        for filename in os.listdir(self.data_dir):
            if filename.endswith('.csv') and not filename.startswith('processed_'):
                filepath = os.path.join(self.data_dir, filename)
                await self._import_workflows_from_csv(filepath)

                # Move to processed folder
                processed_file = os.path.join(
                    self.processed_dir,
                    f"processed_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
                )
                os.rename(filepath, processed_file)
                print(f"📦 Processed and archived: {filename}")

    async def _import_workflows_from_csv(self, filepath: str):
        """Import workflows from CSV file"""
        try:
            df = pd.read_csv(filepath)
            print(f"📥 Importing {len(df)} workflows from {os.path.basename(filepath)}")

            for index, row in df.iterrows():
                await self._create_workflow_from_csv_row(row, index)

        except Exception as e:
            print(f"❌ Error importing CSV {filepath}: {e}")

    async def _create_workflow_from_csv_row(self, row: pd.Series, index: int):
        """Create workflow from CSV row"""
        try:
            workflow_id = f"csv_{datetime.now().strftime('%Y%m%d')}_{index:03d}"

            # Determine task type with fallback
            task_type_str = row.get('task_type', 'data_processing')
            try:
                task_type = TaskType(task_type_str)
            except ValueError:
                task_type = TaskType.DATA_PROCESSING

            # Create workflow steps based on task type
            workflow_steps = self._generate_workflow_steps(task_type)

            workflow = WorkflowInstance(
                id=workflow_id,
                name=row.get('name', f'CSV Task {index}'),
                description=row.get('description', 'Automated task from CSV'),
                task_type=task_type,
                status=WorkflowStatus.PENDING,
                priority=int(row.get('priority', 1)),
                created_at=datetime.now(),
                steps=workflow_steps,
                metadata={
                    "source": "csv_import",
                    "csv_data": row.to_dict(),
                    "import_timestamp": datetime.now().isoformat(),
                    "original_file": os.path.basename(row.get('source_file', 'unknown'))
                },
                execution_log=[]
            )

            self.db.save_workflow(workflow.dict())
            print(f"✅ Created workflow: {workflow.name} (Priority: {workflow.priority})")

        except Exception as e:
            print(f"❌ Error creating workflow from CSV row: {e}")

    def _generate_workflow_steps(self, task_type: TaskType) -> List[WorkflowStep]:
        """Generate appropriate workflow steps based on task type"""
        base_steps = [
            WorkflowStep(
                step_id="init",
                name="Initialization",
                description="Initialize and validate task parameters",
                action_type="initialize_task",
                requires_approval=False,
                timeout_minutes=10
            ),
            WorkflowStep(
                step_id="process",
                name="Data Processing",
                description="Process the main task data",
                action_type="process_data",
                requires_approval=False,
                timeout_minutes=30
            )
        ]

        if task_type == TaskType.PAYMENT_PROCESSING:
            base_steps.extend([
                WorkflowStep(
                    step_id="fraud_check",
                    name="Fraud Detection",
                    description="Automated fraud detection analysis",
                    action_type="fraud_detection",
                    requires_approval=True,  # Requires approval
                    approval_level=1,
                    timeout_minutes=45
                ),
                WorkflowStep(
                    step_id="final_approval",
                    name="Final Approval",
                    description="Manager approval for payment processing",
                    action_type="final_approval",
                    requires_approval=True,  # Requires approval
                    approval_level=2,
                    timeout_minutes=60
                )
            ])
        elif task_type == TaskType.SYSTEM_DEPLOYMENT:
            base_steps.extend([
                WorkflowStep(
                    step_id="security_review",
                    name="Security Review",
                    description="Security team approval for deployment",
                    action_type="security_review",
                    requires_approval=True,  # Requires approval
                    approval_level=2,
                    timeout_minutes=90
                )
            ])
        elif task_type == TaskType.SECURITY_REVIEW:
            base_steps.extend([
                WorkflowStep(
                    step_id="security_scan",
                    name="Security Scan",
                    description="Automated security vulnerability scan",
                    action_type="security_scan",
                    requires_approval=False,
                    timeout_minutes=25
                ),
                WorkflowStep(
                    step_id="compliance_check",
                    name="Compliance Check",
                    description="Verify regulatory compliance",
                    action_type="compliance_check",
                    requires_approval=True,  # Requires approval
                    approval_level=3,
                    timeout_minutes=75
                )
            ])

        # Final completion step
        base_steps.append(
            WorkflowStep(
                step_id="completion",
                name="Task Completion",
                description="Finalize and complete the workflow",
                action_type="complete_task",
                requires_approval=False,
                timeout_minutes=15
            )
        )

        return base_steps

    def create_sample_csv(self):
        """Create sample CSV file with various task types"""
        sample_data = [
            {
                'name': 'Client Payment Processing',
                'description': 'Process monthly client payment',
                'task_type': 'payment_processing',
                'priority': 1,
                'amount': '15000.00',
                'currency': 'USD',
                'client': 'ABC Corp'
            },
            {
                'name': 'User Data Migration',
                'description': 'Migrate user data to new system',
                'task_type': 'data_processing',
                'priority': 2,
                'records_count': '5000',
                'source_system': 'Legacy DB'
            },
            {
                'name': 'API Service Deployment',
                'description': 'Deploy new API service to production',
                'task_type': 'system_deployment',
                'priority': 1,
                'environment': 'production',
                'version': '2.1.0'
            },
            {
                'name': 'Security Audit',
                'description': 'Quarterly security compliance audit',
                'task_type': 'security_review',
                'priority': 1,
                'scope': 'full_system',
                'regulations': 'GDPR, HIPAA'
            },
            {
                'name': 'Vendor Payment',
                'description': 'Process vendor invoice payment',
                'task_type': 'payment_processing',
                'priority': 2,
                'amount': '7500.00',
                'currency': 'EUR',
                'vendor': 'Tech Supplies Inc'
            }
        ]

        df = pd.DataFrame(sample_data)
        csv_path = os.path.join(self.data_dir, "sample_tasks.csv")
        df.to_csv(csv_path, index=False)
        print(f"✅ Created sample CSV: {csv_path}")
        return csv_path

# ===== FASTAPI APP =====
db_manager = DatabaseManager()
workflow_engine = AutomatedWorkflowEngine(db_manager)
csv_automation = CSVAutomation(db_manager, workflow_engine)

background_tasks = set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Starting Automated Human-in-Loop System v3.0...")
    print("=" * 50)

    # Create sample CSV data
    csv_automation.create_sample_csv()

    # Start background services
    automation_task = asyncio.create_task(workflow_engine.start_workflow_automation())
    csv_task = asyncio.create_task(csv_automation.start_csv_monitoring())

    background_tasks.add(automation_task)
    background_tasks.add(csv_task)

    automation_task.add_done_callback(background_tasks.discard)
    csv_task.add_done_callback(background_tasks.discard)

    print("✅ Workflow automation started")
    print("✅ CSV monitoring started")
    print("📊 Dashboard: http://localhost:8000")
    print("⏹️  Press Ctrl+C to stop")
    print("=" * 50)

    yield

    # Shutdown
    print("🛑 Shutting down automated system...")
    for task in background_tasks:
        task.cancel()
    await asyncio.gather(*background_tasks, return_exceptions=True)

app = FastAPI(
    title="Automated Human-in-Loop System v3.0",
    description="Fully automated workflows from CSV with approval intervals",
    version="3.0.0",
    lifespan=lifespan
)

# Create templates directory
os.makedirs("templates", exist_ok=True)
templates = Jinja2Templates(directory="templates")

# ===== HTML TEMPLATES =====

# workflows.html
workflows_html = """
<!DOCTYPE html>
<html>
<head>
    <title>Workflows - Automated System</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        .workflow-card {
            border-left: 4px solid #007bff;
            transition: transform 0.2s;
        }
        .workflow-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }
        .progress-sm {
            height: 6px;
        }
        .step-badge {
            font-size: 0.7rem;
        }
    </style>
</head>
<body>
    <nav class="navbar navbar-dark bg-dark">
        <div class="container">
            <a class="navbar-brand" href="/">
                <i class="fas fa-robot"></i> Automated Workflow System
            </a>
            <div>
                <a href="/" class="btn btn-light btn-sm me-2">
                    <i class="fas fa-tachometer-alt"></i> Dashboard
                </a>
                <a href="/approvals" class="btn btn-warning btn-sm">
                    <i class="fas fa-user-check"></i> Approvals
                    {% if pending_approvals_count > 0 %}
                    <span class="badge bg-danger">{{ pending_approvals_count }}</span>
                    {% endif %}
                </a>
            </div>
        </div>
    </nav>

    <div class="container mt-4">
        <div class="d-flex justify-content-between align-items-center mb-4">
            <div>
                <h1><i class="fas fa-tasks"></i> All Workflows</h1>
                <p class="text-muted">Automated workflows from CSV import and manual creation</p>
            </div>
            <div class="text-end">
                <button class="btn btn-primary" onclick="createSampleWorkflow()">
                    <i class="fas fa-plus"></i> Create Sample
                </button>
                <button class="btn btn-success" onclick="uploadCSV()">
                    <i class="fas fa-file-csv"></i> Upload CSV
                </button>
            </div>
        </div>

        <!-- Statistics -->
        <div class="row mb-4">
            <div class="col-md-2">
                <div class="card bg-primary text-white text-center">
                    <div class="card-body py-3">
                        <h4>{{ total_workflows }}</h4>
                        <small>Total</small>
                    </div>
                </div>
            </div>
            <div class="col-md-2">
                <div class="card bg-success text-white text-center">
                    <div class="card-body py-3">
                        <h4>{{ completed_workflows }}</h4>
                        <small>Completed</small>
                    </div>
                </div>
            </div>
            <div class="col-md-2">
                <div class="card bg-warning text-white text-center">
                    <div class="card-body py-3">
                        <h4>{{ running_workflows }}</h4>
                        <small>Running</small>
                    </div>
                </div>
            </div>
            <div class="col-md-2">
                <div class="card bg-info text-white text-center">
                    <div class="card-body py-3">
                        <h4>{{ approval_workflows }}</h4>
                        <small>Awaiting Approval</small>
                    </div>
                </div>
            </div>
            <div class="col-md-2">
                <div class="card bg-secondary text-white text-center">
                    <div class="card-body py-3">
                        <h4>{{ pending_workflows }}</h4>
                        <small>Pending</small>
                    </div>
                </div>
            </div>
            <div class="col-md-2">
                <div class="card bg-danger text-white text-center">
                    <div class="card-body py-3">
                        <h4>{{ failed_workflows }}</h4>
                        <small>Failed</small>
                    </div>
                </div>
            </div>
        </div>

        <!-- Workflows List -->
        <div class="row">
            {% for workflow in workflows %}
            <div class="col-md-6 mb-4">
                <div class="card workflow-card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <h5 class="mb-0">{{ workflow.name }}</h5>
                        <div>
                            <span class="badge bg-secondary step-badge">{{ workflow.task_type }}</span>
                            <span class="badge 
                                {% if workflow.status == 'completed' %}bg-success
                                {% elif workflow.status == 'running' %}bg-primary
                                {% elif workflow.status == 'awaiting_approval' %}bg-warning
                                {% elif workflow.status == 'failed' or workflow.status == 'rolled_back' %}bg-danger
                                {% else %}bg-secondary{% endif %}">
                                {{ workflow.status }}
                            </span>
                        </div>
                    </div>
                    <div class="card-body">
                        <p class="card-text text-muted">{{ workflow.description }}</p>
                        
                        <!-- Progress -->
                        <div class="mb-3">
                            <div class="d-flex justify-content-between small text-muted mb-1">
                                <span>Progress</span>
                                <span>{{ workflow.current_step + 1 }}/{{ workflow.steps|length }} steps</span>
                            </div>
                            <div class="progress progress-sm">
                                <div class="progress-bar" style="width: {{ ((workflow.current_step + 1) / workflow.steps|length * 100) }}%"></div>
                            </div>
                        </div>

                        <!-- Step Information -->
                        {% if workflow.current_step < workflow.steps|length %}
                        <div class="alert alert-info py-2">
                            <small>
                                <i class="fas fa-info-circle"></i>
                                <strong>Current Step:</strong> 
                                {{ workflow.steps[workflow.current_step].name }}
                                {% if workflow.steps[workflow.current_step].requires_approval %}
                                <span class="badge bg-warning ms-1 step-badge">Approval Required</span>
                                {% endif %}
                            </small>
                        </div>
                        {% endif %}

                        <!-- Metadata -->
                        <div class="small text-muted mb-3">
                            <div><strong>Priority:</strong> 
                                {% for i in range(workflow.priority) %}
                                <i class="fas fa-star text-warning"></i>
                                {% endfor %}
                            </div>
                            <div><strong>Created:</strong> {{ workflow.created_at[:16] }}</div>
                            {% if workflow.metadata.source %}
                            <div><strong>Source:</strong> {{ workflow.metadata.source }}</div>
                            {% endif %}
                        </div>

                        <div class="d-flex justify-content-between">
                            <button class="btn btn-outline-primary btn-sm" onclick="viewWorkflowDetails('{{ workflow.id }}')">
                                <i class="fas fa-eye"></i> Details
                            </button>
                            {% if workflow.status == 'running' or workflow.status == 'awaiting_approval' %}
                            <button class="btn btn-outline-danger btn-sm" onclick="triggerRollback('{{ workflow.id }}')">
                                <i class="fas fa-undo"></i> Rollback
                            </button>
                            {% endif %}
                        </div>
                    </div>
                </div>
            </div>
            {% else %}
            <div class="col-12">
                <div class="text-center py-5">
                    <i class="fas fa-tasks fa-3x text-muted mb-3"></i>
                    <h4 class="text-muted">No Workflows Found</h4>
                    <p class="text-muted">Create a sample workflow or add CSV files to the data/ folder.</p>
                    <button class="btn btn-primary" onclick="createSampleWorkflow()">
                        <i class="fas fa-plus"></i> Create Sample Workflow
                    </button>
                </div>
            </div>
            {% endfor %}
        </div>
    </div>

    <script>
        async function createSampleWorkflow() {
            const response = await fetch('/api/workflows/sample', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            const result = await response.json();
            alert('Sample workflow created! ID: ' + result.workflow_id);
            location.reload();
        }

        function uploadCSV() {
            alert('CSV upload functionality - add CSV files to the data/ folder for automatic processing');
        }

        function viewWorkflowDetails(workflowId) {
            window.open(`/workflows/${workflowId}`, '_blank');
        }

        async function triggerRollback(workflowId) {
            if (confirm('Are you sure you want to trigger rollback? This will undo all completed steps.')) {
                const response = await fetch(`/api/workflows/${workflowId}/rollback`, {
                    method: 'POST'
                });
                const result = await response.json();
                alert(result.message);
                location.reload();
            }
        }

        // Auto-refresh every 15 seconds
        setInterval(() => {
            location.reload();
        }, 15000);
    </script>
</body>
</html>
"""

# Write template files
with open("templates/workflows.html", "w") as f:
    f.write(workflows_html)

# ===== FASTAPI ROUTES =====
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    workflows = db_manager.get_all_workflows()
    pending_approvals = db_manager.get_pending_approvals()

    # Calculate metrics
    total = len(workflows)
    completed = len([w for w in workflows if w['status'] == 'completed'])
    running = len([w for w in workflows if w['status'] == 'running'])
    pending_workflows = len([w for w in workflows if w['status'] == 'pending'])
    approval_workflows = len([w for w in workflows if w['status'] == 'awaiting_approval'])
    failed = len([w for w in workflows if w['status'] in ['failed', 'rolled_back']])

    return templates.TemplateResponse("workflows.html", {
        "request": request,
        "workflows": workflows,
        "pending_approvals_count": len(pending_approvals),
        "total_workflows": total,
        "completed_workflows": completed,
        "running_workflows": running,
        "pending_workflows": pending_workflows,
        "approval_workflows": approval_workflows,
        "failed_workflows": failed
    })

@app.get("/workflows", response_class=HTMLResponse)
async def workflows_page(request: Request):
    return await dashboard(request)  # Reuse dashboard for now

@app.get("/approvals", response_class=HTMLResponse)
async def approvals_page(request: Request):
    pending_approvals = db_manager.get_pending_approvals()

    approvals_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Approvals</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body>
        <nav class="navbar navbar-dark bg-dark">
            <div class="container">
                <a class="navbar-brand" href="/">Approval Panel</a>
                <a href="/" class="btn btn-light">Back to Dashboard</a>
            </div>
        </nav>
        <div class="container mt-4">
            <h1>Pending Approvals</h1>
            {% if approvals %}
                {% for approval in approvals %}
                <div class="card mb-3">
                    <div class="card-body">
                        <h5>{{ approval.workflow_name }}</h5>
                        <p><strong>Step:</strong> {{ approval.metadata.step_name }}</p>
                        <form action="/api/approvals/{{ approval.id }}/respond" method="post">
                            <textarea name="comments" class="form-control mb-2" placeholder="Comments..."></textarea>
                            <input type="hidden" name="approved_by" value="user">
                            <button type="submit" name="action" value="approve" class="btn btn-success">Approve</button>
                            <button type="submit" name="action" value="reject" class="btn btn-danger">Reject</button>
                        </form>
                    </div>
                </div>
                {% endfor %}
            {% else %}
                <p class="text-muted">No pending approvals</p>
            {% endif %}
        </div>
    </body>
    </html>
    """

    with open("templates/approvals.html", "w") as f:
        f.write(approvals_html)

    return templates.TemplateResponse("approvals.html", {
        "request": request,
        "approvals": pending_approvals
    })

@app.post("/api/approvals/{approval_id}/respond")
async def respond_to_approval(
    approval_id: str,
    action: str = Form(...),
    comments: str = Form(None),
    approved_by: str = Form("user")
):
    success = await workflow_engine.submit_approval_decision(
        approval_id,
        ApprovalAction(action),
        approved_by,
        comments
    )

    if success:
        return RedirectResponse(url="/approvals?message=Decision+submitted", status_code=303)
    else:
        raise HTTPException(status_code=400, detail="Failed to submit approval")

@app.post("/api/workflows/sample")
async def create_sample_workflow():
    """Create a sample workflow manually"""
    workflow_id = f"manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    workflow = WorkflowInstance(
        id=workflow_id,
        name="Manual Sample Workflow",
        description="Sample workflow created manually for testing",
        task_type=TaskType.DATA_PROCESSING,
        status=WorkflowStatus.PENDING,
        priority=1,
        created_at=datetime.now(),
        steps=[
            WorkflowStep(
                step_id="init",
                name="Initial Setup",
                description="Initialize workflow parameters",
                action_type="initialize_task",
                requires_approval=False,
                timeout_minutes=10
            ),
            WorkflowStep(
                step_id="process",
                name="Data Processing",
                description="Process the main data",
                action_type="process_data",
                requires_approval=False,
                timeout_minutes=30
            ),
            WorkflowStep(
                step_id="approval",
                name="Manager Approval",
                description="Get manager approval for completion",
                action_type="manager_approval",
                requires_approval=True,
                approval_level=1,
                timeout_minutes=60
            )
        ],
        metadata={"source": "manual_creation"},
        execution_log=[]
    )

    db_manager.save_workflow(workflow.dict())

    return JSONResponse({
        "workflow_id": workflow_id,
        "status": "created",
        "message": "Sample workflow created successfully"
    })

@app.post("/api/workflows/{workflow_id}/rollback")
async def trigger_rollback(workflow_id: str):
    workflow = db_manager.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    workflow['status'] = WorkflowStatus.ROLLED_BACK
    workflow['metadata']['rollback_reason'] = "Manual rollback"
    workflow['metadata']['rollback_timestamp'] = datetime.now().isoformat()

    db_manager.save_workflow(workflow)

    return JSONResponse({
        "status": "rollback_initiated",
        "message": "Rollback completed successfully"
    })

@app.get("/api/workflows")
async def get_workflows_api():
    workflows = db_manager.get_all_workflows()
    return JSONResponse(workflows)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# ===== RUN THE APP =====
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
