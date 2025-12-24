from celery import Celery
import os

# Default to a local Redis instance if the broker URL isn't specified.
broker_url = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
result_backend_url = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')

app = Celery(
    'task_manager',
    broker=broker_url,
    backend=result_backend_url,
    include=['task_manager.tasks']
)

if __name__ == '__main__':
    app.start()
