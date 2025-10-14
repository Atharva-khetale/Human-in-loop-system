import os
from datetime import timedelta

class Config:
    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./workflows.db")
    
    # CSV Processing
    CSV_UPLOAD_PATH = "data/"
    CSV_PROCESSING_INTERVAL = 30  # seconds
    
    # Workflow Settings
    MAX_RETRY_ATTEMPTS = 3
    APPROVAL_TIMEOUT = timedelta(hours=24)
    
    # Notifications
    SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
    EMAIL_SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
    EMAIL_PORT = 587
    
    # Automation
    AUTO_START_WORKFLOWS = True
    BATCH_PROCESSING_SIZE = 10