from celery import Celery

celery = Celery(
    "flask_app",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0"
)

import tasks  # 🔥 this registers tasks