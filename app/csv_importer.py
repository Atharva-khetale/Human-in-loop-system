import pandas as pd
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any
import uuid
import os
from models import CSVTasks, TaskType, WorkflowCreate, WorkflowStep
from database import DatabaseManager

class CSVImporter:
    def __init__(self, db_manager: DatabaseManager, import_path: str = "data/"):
        self.db = db_manager
        self.import_path = import_path
        self.processed_path = os.path.join(import_path, "processed")
        os.makedirs(self.processed_path, exist_ok=True)

    async def monitor_and_import(self):
        """Monitor CSV files and import tasks automatically"""
        while True:
            try:
                await self._process_csv_files()
                await asyncio.sleep(30)  # Check every 30 seconds
            except Exception as e:
                print(f"Error in CSV monitoring: {e}")
                await asyncio.sleep(60)

    async def _process_csv_files(self):
        """Process all CSV files in the import directory"""
        for filename in os.listdir(self.import_path):
            if filename.endswith('.csv') and not filename.startswith('processed_'):
                filepath = os.path.join(self.import_path, filename)
                await self._import_from_csv(filepath)
                
                # Move processed file
                processed_file = os.path.join(
                    self.processed_path, 
                    f"processed_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
                )
                os.rename(filepath, processed_file)
                print(f"Processed and moved: {filename}")

    async def _import_from_csv(self, filepath: str):
        """Import tasks from a CSV file"""
        try:
            df = pd.read_csv(filepath)
            tasks = []
            
            for _, row in df.iterrows():
                task = CSVTasks(
                    task_id=str(uuid.uuid4()),
                    task_type=TaskType(row.get('task_type', 'data_processing')),
                    name=row.get('name', 'Unnamed Task'),
                    description=row.get('description', ''),
                    priority=int(row.get('priority', 1)),
                    data=row.to_dict(),
                    scheduled_time=datetime.now() if pd.isna(row.get('scheduled_time')) else 
                                 pd.to_datetime(row.get('scheduled_time'))
                )
                tasks.append(task)
            
            # Create workflows from tasks
            for task in tasks:
                await self._create_workflow_from_task(task)
                
            print(f"Imported {len(tasks)} tasks from {filepath}")
            
        except Exception as e:
            print(f"Error importing from {filepath}: {e}")

    async def _create_workflow_from_task(self, task: CSVTasks):
        """Create a workflow instance from a CSV task"""
        workflow_steps = self._get_workflow_steps_for_task_type(task.task_type)
        
        workflow = WorkflowCreate(
            name=task.name,
            description=task.description,
            task_type=task.task_type,
            priority=task.priority,
            steps=workflow_steps,
            metadata={
                "source": "csv_import",
                "original_data": task.data,
                "scheduled_time": task.scheduled_time.isoformat() if task.scheduled_time else None,
                "import_timestamp": datetime.now().isoformat()
            }
        )
        
        # Save to database and trigger processing
        workflow_instance = WorkflowInstance(
            id=task.task_id,
            name=workflow.name,
            description=workflow.description,
            task_type=workflow.task_type,
            status="pending",
            priority=workflow.priority,
            created_at=datetime.now(),
            steps=workflow.steps,
            metadata=workflow.metadata,
            execution_log=[]
        )
        
        self.db.save_workflow(workflow_instance.dict())

    def _get_workflow_steps_for_task_type(self, task_type: TaskType) -> List[WorkflowStep]:
        """Define workflow steps based on task type"""
        base_steps = [
            WorkflowStep(
                step_id="validation",
                name="Data Validation",
                description="Validate input data and requirements",
                action_type="validate_data",
                requires_approval=False,
                timeout_minutes=30
            ),
            WorkflowStep(
                step_id="processing",
                name="Data Processing",
                description="Process the main task data",
                action_type="process_data",
                requires_approval=False,
                timeout_minutes=60
            )
        ]
        
        if task_type == TaskType.PAYMENT_PROCESSING:
            base_steps.extend([
                WorkflowStep(
                    step_id="fraud_check",
                    name="Fraud Detection",
                    description="Automated fraud detection check",
                    action_type="fraud_detection",
                    requires_approval=True,
                    approval_level=1,
                    timeout_minutes=120
                ),
                WorkflowStep(
                    step_id="manager_approval",
                    name="Manager Approval",
                    description="Manager approval for large payments",
                    action_type="manager_approval",
                    requires_approval=True,
                    approval_level=2,
                    timeout_minutes=240
                )
            ])
        elif task_type == TaskType.SYSTEM_DEPLOYMENT:
            base_steps.extend([
                WorkflowStep(
                    step_id="security_review",
                    name="Security Review",
                    description="Security team approval for deployment",
                    action_type="security_review",
                    requires_approval=True,
                    approval_level=2,
                    timeout_minutes=180
                ),
                WorkflowStep(
                    step_id="production_deploy",
                    name="Production Deployment",
                    description="Deploy to production environment",
                    action_type="deploy_system",
                    requires_approval=True,
                    approval_level=3,
                    timeout_minutes=360
                )
            ])
        
        # Final completion step
        base_steps.append(
            WorkflowStep(
                step_id="completion",
                name="Task Completion",
                description="Finalize and complete the task",
                action_type="complete_task",
                requires_approval=False,
                timeout_minutes=30
            )
        )
        
        return base_steps