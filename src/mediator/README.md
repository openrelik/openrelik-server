## Mediator Server

This server acts as a mediator between The API server and Celery workers. It monitors Celery tasks and updates a database with their status, results, and errors.

**Key Features:**

* **Celery Task Monitoring:** Continuously monitors Celery tasks for progress updates, successes, and failures.
* **Database Integration:**  Updates the SQL database with detailed task information, including status, progress, results, and error details.
* **Result Handling:**  Processes successful task results, including creating new files in the database based on the output.
* **Error Handling:**  Captures and stores exception information and tracebacks for failed tasks.
* **Retry Logic:**  Implements retry logic for database lookups to handle potential transient errors.

**Running the Server:**

1.  Install the required dependencies.
2.  Set the `REDIS_URL` environment variable.
3.  Run the script: `python mediator_server.py`
