from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from contextlib import asynccontextmanager
import asyncio
import uuid
from datetime import datetime
from typing import List, Dict, Any
from models import *
from database import DatabaseManager
from workflow_engine import WorkflowEngine
from csv_importer import CSVImporter
from approval_manager import ApprovalManager

# Background tasks
background_tasks = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Starting Automated Human-in-Loop System...")

    # Start CSV monitoring
    csv_task = asyncio.create_task(csv_importer.monitor_and_import())
    background_tasks.add(csv_task)
    csv_task.add_done_callback(background_tasks.discard)

    print("✅ CSV monitoring started")
    print("✅ System ready at http://localhost:8000")

    yield  # This is where the application runs

    # Shutdown
    print("🛑 Shutting down system...")
    for task in background_tasks:
        task.cancel()
    await asyncio.gather(*background_tasks, return_exceptions=True)
    print("✅ System shutdown complete")


app = FastAPI(
    title="Automated Human-in-Loop System",
    description="Event-driven workflow system with automated task processing and human approvals",
    version="2.0.0",
    lifespan=lifespan  # Use the modern lifespan approach
)

# Setup
templates = Jinja2Templates(directory="templates")
#app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Initialize components
db_manager = DatabaseManager()
workflow_engine = WorkflowEngine(db_manager)
approval_manager = ApprovalManager(db_manager)
csv_importer = CSVImporter(db_manager)


# Common context for templates
def get_common_context():
    """Get common context variables for all templates"""
    try:
        workflows = db_manager.get_all_workflows()
        pending_approvals = len([w for w in workflows if w.get('status') == 'awaiting_approval'])
    except:
        pending_approvals = 0

    return {
        "pending_approvals_count": pending_approvals,
        "system_status": "online"
    }


# Dashboard Routes
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard"""
    try:
        workflows = db_manager.get_all_workflows()
        pending_approvals = await approval_manager.get_pending_approvals()

        # Calculate metrics
        total_workflows = len(workflows)
        completed = len([w for w in workflows if w.get('status') == 'completed'])
        pending = len([w for w in workflows if w.get('status') in ['pending', 'running']])
        failed = len([w for w in workflows if w.get('status') in ['failed', 'rolled_back']])

        context = get_common_context()
        context.update({
            "request": request,
            "workflows": workflows[:10],
            "pending_approvals": pending_approvals,
            "metrics": {
                "total": total_workflows,
                "completed": completed,
                "pending": pending,
                "failed": failed,
                "completion_rate": (completed / total_workflows * 100) if total_workflows > 0 else 0
            }
        })

        return templates.TemplateResponse("dashboard.html", context)
    except Exception as e:
        return HTMLResponse(f"<h1>Error loading dashboard: {str(e)}</h1>")


@app.get("/workflows", response_class=HTMLResponse)
async def workflows_list(request: Request):
    """Workflows list page"""
    try:
        workflows = db_manager.get_all_workflows()

        context = get_common_context()
        context.update({
            "request": request,
            "workflows": workflows
        })

        return templates.TemplateResponse("workflows.html", context)
    except Exception as e:
        return HTMLResponse(f"<h1>Error loading workflows: {str(e)}</h1>")


@app.get("/workflows/{workflow_id}", response_class=HTMLResponse)
async def workflow_detail(request: Request, workflow_id: str):
    """Workflow detail page"""
    try:
        workflow = db_manager.get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        context = get_common_context()
        context.update({
            "request": request,
            "workflow": workflow
        })

        return templates.TemplateResponse("workflow_detail.html", context)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading workflow: {str(e)}")


@app.get("/approvals", response_class=HTMLResponse)
async def approvals_panel(request: Request):
    """Approvals management panel"""
    try:
        pending_approvals = await approval_manager.get_pending_approvals()

        context = get_common_context()
        context.update({
            "request": request,
            "approvals": pending_approvals
        })

        return templates.TemplateResponse("approval_panel.html", context)
    except Exception as e:
        return HTMLResponse(f"<h1>Error loading approvals: {str(e)}</h1>")


@app.get("/analytics", response_class=HTMLResponse)
async def analytics_dashboard(request: Request):
    """Analytics dashboard"""
    try:
        context = get_common_context()
        context.update({
            "request": request
        })

        return templates.TemplateResponse("analytics.html", context)
    except Exception as e:
        return HTMLResponse(f"<h1>Error loading analytics: {str(e)}</h1>")


# API Routes
@app.post("/api/workflows")
async def create_workflow(workflow: WorkflowCreate):
    """Create a new workflow"""
    try:
        workflow_id = str(uuid.uuid4())

        workflow_instance = WorkflowInstance(
            id=workflow_id,
            name=workflow.name,
            description=workflow.description,
            task_type=workflow.task_type,
            status=WorkflowStatus.PENDING,
            priority=workflow.priority,
            created_at=datetime.now(),
            steps=workflow.steps,
            metadata=workflow.metadata,
            execution_log=[]
        )

        db_manager.save_workflow(workflow_instance.dict())

        # Start workflow execution
        await workflow_engine.start_workflow(workflow_id)

        return JSONResponse({
            "workflow_id": workflow_id,
            "status": "created",
            "message": "Workflow created and started successfully"
        })
    except Exception as e:
        return JSONResponse(
            {"error": f"Failed to create workflow: {str(e)}"},
            status_code=500
        )


@app.post("/api/workflows/sample")
async def create_sample_workflow():
    """Create a sample workflow for testing"""
    try:
        from .models import TaskType, WorkflowStep

        workflow_id = str(uuid.uuid4())

        sample_steps = [
            WorkflowStep(
                step_id="validate",
                name="Data Validation",
                description="Validate input data",
                action_type="validate_data",
                requires_approval=False,
                timeout_minutes=30
            ),
            WorkflowStep(
                step_id="process",
                name="Data Processing",
                description="Process the data",
                action_type="process_data",
                requires_approval=False,
                timeout_minutes=60
            ),
            WorkflowStep(
                step_id="approve",
                name="Manager Approval",
                description="Get manager approval",
                action_type="approval_gate",
                requires_approval=True,
                approval_level=1,
                timeout_minutes=120
            )
        ]

        workflow_instance = WorkflowInstance(
            id=workflow_id,
            name="Sample Workflow",
            description="A sample workflow for testing",
            task_type=TaskType.DATA_PROCESSING,
            status=WorkflowStatus.PENDING,
            priority=1,
            created_at=datetime.now(),
            steps=sample_steps,
            metadata={"sample": True, "created_via": "sample_endpoint"},
            execution_log=[]
        )

        db_manager.save_workflow(workflow_instance.dict())
        await workflow_engine.start_workflow(workflow_id)

        return JSONResponse({
            "workflow_id": workflow_id,
            "status": "created",
            "message": "Sample workflow created successfully"
        })

    except Exception as e:
        return JSONResponse(
            {"error": f"Failed to create sample workflow: {str(e)}"},
            status_code=500
        )


@app.post("/api/approvals/{approval_request_id}/respond")
async def respond_to_approval(
        approval_request_id: str,
        action: str = Form(...),
        comments: str = Form(None),
        approved_by: str = Form("user")
):
    """Submit approval response"""
    try:
        response = ApprovalResponse(
            approval_request_id=approval_request_id,
            action=ApprovalAction(action),
            approved_by=approved_by,
            comments=comments,
            timestamp=datetime.now()
        )

        success = await approval_manager.submit_approval_response(approval_request_id, response)

        if success:
            return RedirectResponse(url="/approvals?message=Decision+submitted", status_code=303)
        else:
            raise HTTPException(status_code=400, detail="Failed to submit approval response")

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/workflows")
async def get_workflows_api():
    """Get all workflows (API)"""
    try:
        workflows = db_manager.get_all_workflows()
        return JSONResponse(workflows)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/metrics")
async def get_system_metrics():
    """Get system metrics"""
    try:
        workflows = db_manager.get_all_workflows()

        metrics = {
            "total_workflows": len(workflows),
            "workflows_by_status": {},
            "workflows_by_type": {},
            "avg_completion_time": 0,
            "approval_stats": {
                "pending": len([w for w in workflows if w.get('status') == 'awaiting_approval']),
                "approved_today": 0,
                "rejected_today": 0
            }
        }

        # Calculate status distribution
        for workflow in workflows:
            status = workflow.get('status', 'unknown')
            metrics["workflows_by_status"][status] = metrics["workflows_by_status"].get(status, 0) + 1

            task_type = workflow.get('task_type', 'unknown')
            metrics["workflows_by_type"][task_type] = metrics["workflows_by_type"].get(task_type, 0) + 1

        return JSONResponse(metrics)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/workflows/{workflow_id}/rollback")
async def trigger_rollback(workflow_id: str):
    """Manually trigger rollback"""
    try:
        workflow = db_manager.get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        workflow_instance = WorkflowInstance(**workflow)
        await workflow_engine.rollback_engine.execute_rollback(workflow_id, workflow_instance, "Manual rollback")

        return JSONResponse({
            "status": "rollback_initiated",
            "message": "Rollback process started successfully"
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


# Remove the old __main__ block and use this instead:
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=5000, reload=True)