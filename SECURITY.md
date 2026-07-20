# Security

This document describes the security controls built into the platform and how
to report a vulnerability. The controls are defense-in-depth: image hardening,
runtime restrictions, network segmentation, least-privilege identity, and
supply-chain scanning.

## Container hardening

- **Non-root**: both images create an unprivileged user (`uid:gid 10001:10001`)
  and run as it. No process runs as root.
- **Multi-stage builds**: the build toolchain (gcc, build-essential) lives only
  in the builder stage and never ships in the final image, shrinking the attack
  surface.
- **Pinned base images**: `python:3.12-slim-bookworm` is pinned (pin to a digest
  for full immutability in a regulated environment).
- **No secrets baked in**: images contain code only; all credentials are
  injected at runtime.

## Runtime (Kubernetes) hardening

Set in `helm/ml-api/values.yaml` and applied by the Deployment:

- `runAsNonRoot: true`, explicit `runAsUser/runAsGroup/fsGroup: 10001`
- `allowPrivilegeEscalation: false`
- `readOnlyRootFilesystem: true` (a writable `emptyDir` is mounted at `/tmp`)
- `capabilities.drop: [ALL]`
- `seccompProfile: RuntimeDefault`
- `automountServiceAccountToken: false` — the app needs no Kubernetes API access
- The `mlops` namespace enforces the **restricted** Pod Security Standard
  (`kubernetes/namespace.yaml`)

## Secrets management

- **Nothing sensitive is committed.** `.env` and `*.tfvars` are gitignored;
  only `.example` templates are tracked.
- **In-cluster**: artifact-store credentials come from a Kubernetes `Secret`
  referenced via `existingSecret` in values, mounted as env vars — never placed
  in `values.yaml` or the ConfigMap. For production, use
  [External Secrets Operator](https://external-secrets.io/) or GCP Secret
  Manager rather than raw `Secret` objects.
- **Preferred (GKE)**: **Workload Identity** — the pod impersonates a Google
  service account (provisioned in `terraform/`) to reach GCS with **no static
  keys at all**. The Terraform `google_service_account_iam_member` binds the
  Kubernetes SA to the Google SA.

## Network policy

`kubernetes/networkpolicy.yaml` applies **default-deny** ingress and egress in
the `mlops` namespace, then explicitly allows only:

- ingress to port 8000 from the ingress controller and the monitoring namespace
  (Prometheus scraping),
- egress to cluster DNS, the MLflow tracking server, and HTTPS (443) to Google
  APIs — with the instance metadata endpoint (`169.254.169.254`) explicitly
  blocked to mitigate SSRF-to-metadata attacks.

Requires a NetworkPolicy-enforcing CNI (Calico, Cilium, or GKE Dataplane V2).

## Identity & least privilege

- The GKE node service account (`terraform/`) gets only logging, monitoring, and
  Artifact Registry **read** roles.
- The app's Google SA gets `roles/storage.objectAdmin` scoped to the single
  MLflow bucket — not project-wide storage admin.
- The deploy pipeline authenticates to GCP with **Workload Identity Federation**
  (OIDC), so there are no long-lived JSON key files in GitHub secrets.

## Supply-chain / CI security

- **Image scanning**: `docker-build.yml` scans every image with **Trivy**
  (`CRITICAL,HIGH`) *before* pushing, and fails the build on fixable findings.
  Results are uploaded as SARIF to GitHub code scanning.
- **Least-privilege tokens**: workflows declare minimal `permissions:` and only
  log in to the registry on non-fork `push` events.
- **Pinned actions & tool versions** in workflows.
- **Immutable image tags**: Artifact Registry is configured with
  `immutable_tags = true` so a tag cannot be silently overwritten.

## Reporting a vulnerability

Please **do not** open a public issue for security problems. Instead, use
GitHub's private **"Report a vulnerability"** flow
(Security ▸ Advisories ▸ Report a vulnerability) on this repository, or email the
maintainer listed in `Chart.yaml`. Include reproduction steps and impact. You
can expect an acknowledgement within a few business days.
