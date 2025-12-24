# Deployment Profiles

This document outlines the different deployment profiles for the ht-base microservices architecture.

## Local Development / Docker Compose

This profile is intended for local development and testing. It uses Docker Compose to stand up all the necessary services, including Redis and a local PostgreSQL instance.

### Prerequisites

- Docker
- Docker Compose

### Usage

1.  **Set up the environment:**
    -   Copy the `.env.example` files in each service directory to `.env`.
    -   Update the `.env` files with your local configuration.
2.  **Start the services:**
    ```
    docker-compose up -d
    ```
3.  **Stop the services:**
    ```
    docker-compose down
    ```

## Kubernetes / Google Cloud Run

This profile is intended for production deployments on Kubernetes or Google Cloud Run. It uses the same Docker images as the local development profile, but with environment-specific manifests (e.g., Helm charts, Terraform configurations).

### Prerequisites

- A Kubernetes cluster or Google Cloud Run project
- `kubectl` or `gcloud` CLI tools
- A managed Redis instance (e.g., Google Cloud Memorystore)
- A managed PostgreSQL instance (e.g., Google Cloud SQL)

### Configuration

-   **Environment Variables:**
    -   The required environment variables for each service are documented in their respective `.env.example` files.
    -   These environment variables should be configured in your Kubernetes or Cloud Run manifests.
-   **Secrets:**
    -   Sensitive information, such as database credentials and API keys, should be stored as secrets in your Kubernetes or Cloud Run environment.
-   **Scaling:**
    -   The API Gateway can be configured to scale based on CPU or memory usage.
    -   The archiver, summarization, and task manager services can be configured to scale independently based on the number of tasks in the queue.
-   **Storage:**
    -   The storage service can be configured to use a variety of storage providers, including Google Cloud Storage (GCS) and local storage.
    -   For production deployments, it is recommended to use a cloud-based storage provider like GCS.
-   **Data:**
    -   The data service can be configured to use both PostgreSQL and Firestore.
    -   For production deployments, it is recommended to use managed instances of these databases.
