
# 🧠 Human-in-the-Loop Automation System
*A scalable event-driven workflow engine with human approval checkpoints, rollback recovery, and full state management.*

---

## 🌍 Overview

The **Human-in-the-Loop (HITL) System** is an intelligent orchestration layer that combines automated workflows with real-time human intervention.

Designed for the **Lyzr Elite Hiring Challenge**, this project demonstrates an **event-driven**, **state-aware**, and **resilient** backend architecture where machine workflows pause for human approvals, capture feedback asynchronously, and resume execution automatically.

---

## ⚙️ Core Features

- 🚦 **Event-driven Orchestration** — asynchronous task management with background monitoring.  
- 👩‍💻 **Human Approval System** — configurable approval checkpoints using the `ApprovalManager`.  
- 🔄 **Rollback & Recovery** — safe rollback mechanism for failed or rejected tasks.  
- 🧩 **Workflow State Persistence** — robust tracking via `state_manager.py` and SQLite databases.  
- 📁 **CSV Data Ingestion** — bulk data input via `csv_importer.py`.  
- 🔔 **Notification Engine** — notifies on approval or state transitions.  
- 🧠 **Extensible Design** — easy to integrate with Slack, Gmail, or REST APIs.

---

## 🧰 Tech Stack

| Component | Technology |
|------------|-------------|
| Backend Framework | FastAPI |
| Database | SQLite |
| Task Handling | AsyncIO |
| Templates | Jinja2 |
| Language | Python 3.10+ |
| Web Server | Uvicorn |

---

## 📂 Project Structure

```

Human-in-loop-system-main/
│
├── app/
│   ├── main.py                # FastAPI entrypoint
│   ├── workflow_engine.py     # Core orchestration logic
│   ├── approval_manager.py    # Human approval and feedback handler
│   ├── rollback_engine.py     # Rollback and recovery
│   ├── state_manager.py       # Tracks and persists workflow states
│   ├── csv_importer.py        # Data ingestion service
│   ├── notification_service.py# Alerts and updates
│   ├── database.py            # Database manager
│   ├── models.py              # Pydantic/ORM models
│   ├── templates/             # Jinja2 HTML templates
│   ├── hitl.db, workflows.db  # SQLite databases
│
├── config.py                  # App configuration
├── run.py                     # Server entry script
└── requirements.txt            # Dependencies

````

---

## 🧩 How It Works

1. **CSV Importer** loads initial tasks or workflow data.
2. **Workflow Engine** executes tasks asynchronously.
3. When a decision point is reached, **Approval Manager** pauses execution.
4. Human reviewers interact via approval UI or API.
5. Once approved, **Workflow Engine** resumes automatically.
6. On failure, **Rollback Engine** restores safe state.
7. **State Manager** logs all transitions in database.

---

## 🧪 Running the Project

### 1. Setup Environment
```bash
git clone https://github.com/yourusername/Human-in-loop-system-main.git
cd Human-in-loop-system-main
python -m venv venv
source venv/bin/activate
````

### 2. Install Requirements

```bash
pip install -r requirements.txt
```

### 3. Launch Server

```bash
python run.py
# or
uvicorn app.main:app --reload
```

### 4. Access App

Open: **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

## 🔧 Future Improvements

* Add **multi-channel human input** (Slack, Email, WhatsApp API).
* Implement **async retry queues** with timeout and resubmission.
* Design a **frontend dashboard** to visualize approval pipelines.
* Introduce **LLM-assisted context validation** for approvals.

---

## 🧾 License

MIT License © 2025 Atharva Khetale
