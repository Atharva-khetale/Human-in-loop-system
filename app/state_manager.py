import json
from typing import Dict, Any, Optional
from datetime import datetime
from .models import StateSnapshot


class StateManager:
    def __init__(self):
        self.memory_store = {}
        print("Using in-memory state store")

    async def save_state(self, workflow_id: str, state: Dict[str, Any]) -> None:
        """Save workflow state"""
        snapshot = StateSnapshot(
            workflow_id=workflow_id,
            timestamp=datetime.utcnow(),
            state=state,
            step_index=state.get('current_step', 0)
        )

        self.memory_store[f"{workflow_id}:state"] = snapshot
        print(f"Saved state for workflow: {workflow_id}")

    async def get_state(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get workflow state"""
        return self.memory_store.get(f"{workflow_id}:state")

    async def save_snapshot(self, workflow_id: str, snapshot: StateSnapshot) -> None:
        """Save state snapshot for rollback"""
        key = f"{workflow_id}:snapshot:{snapshot.timestamp.isoformat()}"
        self.memory_store[key] = snapshot
        print(f"Saved snapshot for workflow: {workflow_id}")

    async def get_last_snapshot(self, workflow_id: str) -> Optional[StateSnapshot]:
        """Get last state snapshot for rollback"""
        snapshots = [k for k in self.memory_store.keys() if k.startswith(f"{workflow_id}:snapshot:")]
        if snapshots:
            latest_key = sorted(snapshots)[-1]
            return self.memory_store[latest_key]

        return None
