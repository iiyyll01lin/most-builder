# ─── DDM-V2 Kubernetes Deployment — README ───────────────────────────────────
#
# This directory contains base Kubernetes manifests for the full DDM-V2 stack.
# They target AWS EKS and GCP GKE but work on any CNCF-conformant cluster.
#
# ── File map ──────────────────────────────────────────────────────────────────
#
#   namespace.yaml             Namespace: ddm-v2
#   configmap.yaml             Non-sensitive app config (env vars)
#   secrets.yaml               TEMPLATE — replace placeholders before applying
#   postgres-statefulset.yaml  PostgreSQL 15 StatefulSet + headless Service + PVC
#   redis-deployment.yaml      Redis 7 Deployment + Service + PVC
#   mosquitto-deployment.yaml  Mosquitto 2 Deployment + Service + ConfigMap + PVC
#   backend-deployment.yaml    FastAPI backend Deployment + Service (2 replicas)
#   celery-worker-deployment.yaml  Celery worker Deployment (2 replicas)
#   frontend-deployment.yaml   Nginx+React SPA Deployment + Service (2 replicas)
#   ingress.yaml               Nginx Ingress — routes /api/* → backend, /* → frontend
#
# ── Quick start ───────────────────────────────────────────────────────────────
#
# 1. Edit secrets.yaml with real base64-encoded values (or use External Secrets).
# 2. Edit configmap.yaml — set DDM_CORS_ALLOW_ORIGINS to your domain.
# 3. Edit ingress.yaml — replace `ddm.example.com` with your real domain.
# 4. Update image tags in *-deployment.yaml / postgres-statefulset.yaml to point
#    to your container registry.
# 5. Apply in order:
#
#   kubectl apply -f k8s/namespace.yaml
#   kubectl apply -f k8s/secrets.yaml
#   kubectl apply -f k8s/configmap.yaml
#   kubectl apply -f k8s/postgres-statefulset.yaml
#   kubectl apply -f k8s/redis-deployment.yaml
#   kubectl apply -f k8s/mosquitto-deployment.yaml
#   kubectl apply -f k8s/backend-deployment.yaml
#   kubectl apply -f k8s/celery-worker-deployment.yaml
#   kubectl apply -f k8s/frontend-deployment.yaml
#   kubectl apply -f k8s/ingress.yaml
#
#   — or apply the whole directory at once:
#   kubectl apply -f k8s/
#
# ── Storage classes ───────────────────────────────────────────────────────────
#
#   AWS EKS : storageClassName: gp2  (or gp3 — faster, lower cost)
#   GCP GKE : storageClassName: standard-rwo
#   On-prem : storageClassName: local-path  (k3s) or your provisioner
#
# ── Scaling ───────────────────────────────────────────────────────────────────
#
#   Backend and frontend are stateless — scale with:
#     kubectl scale deployment backend   -n ddm-v2 --replicas=N
#     kubectl scale deployment frontend  -n ddm-v2 --replicas=N
#     kubectl scale deployment celery-worker -n ddm-v2 --replicas=N
#
#   PostgreSQL is a StatefulSet — do NOT scale past 1 with this manifest.
#   Use the Bitnami HA chart or Crunchy PGO for multi-replica Postgres.
#
# ── Horizontal Pod Autoscaler (optional) ─────────────────────────────────────
#
#   kubectl autoscale deployment backend  -n ddm-v2 --min=2 --max=10 --cpu-percent=70
#   kubectl autoscale deployment frontend -n ddm-v2 --min=2 --max=6  --cpu-percent=80
