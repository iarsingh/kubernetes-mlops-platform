# Terraform — supporting infrastructure

Provisions the GCP infra the platform depends on. It assumes you already have a
GKE cluster (with Workload Identity enabled) and layers app-specific resources
on top rather than owning the whole cluster lifecycle.

## What it creates

| Resource | Module / resource | Purpose |
|----------|-------------------|---------|
| Artifact Registry (Docker) | `modules/artifact-registry` | Stores the `ml-api` / training images with cleanup policies + immutable tags |
| GCS bucket | `modules/gcs-bucket` | MLflow artifact store (`--default-artifact-root`), versioned, lifecycle-managed |
| GKE training node pool | `google_container_node_pool.training` | Autoscaled **Spot** pool, tainted `workload=training` for batch training Jobs |
| GKE node service account | `google_service_account.gke_nodes` | Least-privilege node identity |
| Workload Identity SA | `google_service_account.ml_api` + IAM bindings | Lets `ml-api` pods reach GCS **without static keys** |

## Usage

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # edit values
terraform init          # add -backend=false to validate without remote state
terraform plan
terraform apply
```

After apply, annotate the Kubernetes ServiceAccount with the output
`ml_api_gcp_service_account` so Workload Identity binds:

```bash
kubectl annotate sa ml-api -n mlops \
  iam.gke.io/gcp-service-account=$(terraform output -raw ml_api_gcp_service_account)
```

## Remote state

State backend is **commented out** in `versions.tf` because no state bucket
exists yet. To enable durable, locked remote state:

```bash
gcloud storage buckets create gs://<PROJECT>-tfstate --location=<REGION> --uniform-bucket-level-access
# uncomment the backend "gcs" block in versions.tf, then:
terraform init -migrate-state
```

## MLflow metadata backend (PostgreSQL)

MLflow needs a database for run/metadata storage. Two options:

1. **Cloud SQL for PostgreSQL** (managed, recommended for prod) — add a
   `google_sql_database_instance` + `google_sql_database` + `google_sql_user`,
   and connect MLflow via the Cloud SQL Auth Proxy sidecar. Not provisioned here
   to avoid a standing cost in a portfolio/demo project.
2. **Self-hosted Postgres** — the `docker-compose.yml` in the repo root runs
   Postgres + MinIO + MLflow locally so the whole stack works with zero cloud
   spend.

## Security notes

- No secrets are hardcoded. Credentials for the artifact store come from
  Workload Identity (cloud) or Kubernetes Secrets (see `SECURITY.md`).
- `public_access_prevention = "enforced"` and uniform bucket-level access on the
  GCS bucket.
- Shielded VMs + secure boot on the node pool.
