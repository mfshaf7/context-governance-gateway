#!/usr/bin/env bash
set -euo pipefail

readonly PROFILE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly OWNER_REPO_ROOT="$(cd "${PROFILE_ROOT}/../../.." && pwd)"
readonly PROFILE_ID="${DEVINT_PROFILE_ID:-context-governance-gateway}"
readonly OPERATOR="${DEVINT_OPERATOR:-${USER:-operator}}"
readonly NAMESPACE="${DEVINT_NAMESPACE:-devint-${PROFILE_ID}-${OPERATOR}}"
readonly STATE_ROOT="${DEVINT_STATE_ROOT:-${OWNER_REPO_ROOT}/.dev-integration/${PROFILE_ID}/${OPERATOR}}"
readonly SESSION_FILE="${DEVINT_SESSION_FILE:-${STATE_ROOT}/session.yaml}"
readonly PROMOTION_REPORT="${DEVINT_PROMOTION_REPORT:-${STATE_ROOT}/promotion-report.yaml}"
readonly DEVINT_KUBECONFIG_PATH="${DEVINT_KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"

export KUBECONFIG="${DEVINT_KUBECONFIG_PATH}"

read -r -a KUBECTL_CMD <<<"${DEVINT_KUBECTL:-k3s kubectl}"

profile_lifecycle() {
  if [[ -n "${DEVINT_PROFILE_LIFECYCLE:-}" ]]; then
    printf '%s' "${DEVINT_PROFILE_LIFECYCLE}"
    return
  fi

  if [[ -f "${SESSION_FILE}" ]]; then
    python3 - "${SESSION_FILE}" <<'PY'
import pathlib
import re
import sys

text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
match = re.search(r"(?m)^profile_lifecycle:\s*['\"]?([^'\"\n]+)['\"]?\s*$", text)
print(match.group(1).strip() if match else "build-admitted")
PY
    return
  fi

  printf 'build-admitted'
}

readonly PROFILE_LIFECYCLE="$(profile_lifecycle)"
readonly STATUS_FILE="${STATE_ROOT}/profile-status.txt"
readonly SMOKE_SUMMARY="${STATE_ROOT}/smoke-summary.txt"
readonly PROFILE_PROMOTION_NOTES="${STATE_ROOT}/profile-promotion-notes.md"
readonly RENDERED_DIR="${STATE_ROOT}/rendered"
readonly LOGS_DIR="${STATE_ROOT}/logs"
readonly LOCAL_SECRETS_ENV="${STATE_ROOT}/local-secrets.env"
readonly ACCESS_LOCAL_PORT="${DEVINT_CGG_API_LOCAL_PORT:-18280}"
readonly MINIO_LOCAL_PORT="${DEVINT_CGG_MINIO_LOCAL_PORT:-18281}"
readonly API_DEPLOYMENT="context-governance-gateway-api"
readonly WORKER_DEPLOYMENT="context-governance-gateway-worker"
readonly API_SERVICE="context-governance-gateway-api"
readonly POSTGRES_DEPLOYMENT="context-governance-gateway-postgresql"
readonly POSTGRES_SERVICE="context-governance-gateway-postgresql"
readonly MINIO_DEPLOYMENT="context-governance-gateway-minio"
readonly MINIO_SERVICE="context-governance-gateway-minio"
readonly CGG_STATE_PVC="context-governance-gateway-state"
readonly POSTGRES_PVC="context-governance-gateway-postgresql"
readonly MINIO_PVC="context-governance-gateway-minio"
readonly SECRET_NAME="context-governance-gateway-local-secrets"
readonly SEED_ARTIFACT_FILE="${STATE_ROOT}/seed-artifact-id.txt"

kubectl_cmd() {
  "${KUBECTL_CMD[@]}" "$@"
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

ensure_state_dirs() {
  mkdir -p "${STATE_ROOT}" "${RENDERED_DIR}" "${LOGS_DIR}"
}

generate_random_hex() {
  python3 - <<'PY'
import secrets
print(secrets.token_hex(24))
PY
}

ensure_local_secrets() {
  ensure_state_dirs
  if [[ -f "${LOCAL_SECRETS_ENV}" ]]; then
    return
  fi

  cat >"${LOCAL_SECRETS_ENV}" <<EOF
POSTGRES_USER=cgg
POSTGRES_PASSWORD=$(generate_random_hex)
POSTGRES_DB=cgg
MINIO_ROOT_USER=cgg-local
MINIO_ROOT_PASSWORD=$(generate_random_hex)
EOF
}

load_local_secrets() {
  # shellcheck disable=SC1090
  source "${LOCAL_SECRETS_ENV}"
}

is_active_profile() {
  [[ "${PROFILE_LIFECYCLE}" == "active" ]]
}

write_status_file() {
  ensure_state_dirs
  cat >"${STATUS_FILE}" <<EOF
profile: ${PROFILE_ID}
lifecycle: ${PROFILE_LIFECYCLE}
namespace: ${NAMESPACE}
operator: ${OPERATOR}
state root: ${STATE_ROOT}
runtime: $(is_active_profile && printf 'active-local-k3s' || printf 'build-admitted-not-active')
launchable: $(is_active_profile && printf 'true' || printf 'false')
api service: ${API_SERVICE}
api local port: ${ACCESS_LOCAL_PORT}
minio local port: ${MINIO_LOCAL_PORT}
EOF
}

stage_handoff_required_checks_markdown() {
  cat <<'EOF'
   - `active dev-integration profile admission`
   - `API readiness contract`
   - `artifact custody model`
   - `redaction policy gate`
   - `packet receipt compatibility`
   - `security custody review`
EOF
}

print_status() {
  write_status_file
  cat "${STATUS_FILE}"
}

fail_not_active() {
  print_status
  echo
  echo "refused: ${PROFILE_ID} is ${PROFILE_LIFECYCLE}, not active; service-mode runtime launch is intentionally blocked." >&2
  exit 2
}

require_active_profile() {
  if ! is_active_profile; then
    fail_not_active
  fi
}

wait_for_runtime_ready() {
  kubectl_cmd -n "${NAMESPACE}" rollout status "deployment/${POSTGRES_DEPLOYMENT}" --timeout=300s
  kubectl_cmd -n "${NAMESPACE}" rollout status "deployment/${MINIO_DEPLOYMENT}" --timeout=300s
  kubectl_cmd -n "${NAMESPACE}" rollout status "deployment/${API_DEPLOYMENT}" --timeout=600s
  kubectl_cmd -n "${NAMESPACE}" rollout status "deployment/${WORKER_DEPLOYMENT}" --timeout=600s
}

render_runtime_manifest() {
  ensure_state_dirs
  load_local_secrets
  cat >"${RENDERED_DIR}/cgg-runtime.yaml" <<EOF
apiVersion: v1
kind: Namespace
metadata:
  name: ${NAMESPACE}
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ${CGG_STATE_PVC}
  namespace: ${NAMESPACE}
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: ${DEVINT_CGG_STATE_VOLUME_SIZE:-2Gi}
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ${POSTGRES_PVC}
  namespace: ${NAMESPACE}
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: ${DEVINT_CGG_POSTGRES_VOLUME_SIZE:-2Gi}
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ${MINIO_PVC}
  namespace: ${NAMESPACE}
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: ${DEVINT_CGG_MINIO_VOLUME_SIZE:-2Gi}
---
apiVersion: v1
kind: Secret
metadata:
  name: ${SECRET_NAME}
  namespace: ${NAMESPACE}
type: Opaque
stringData:
  POSTGRES_USER: "${POSTGRES_USER}"
  POSTGRES_PASSWORD: "${POSTGRES_PASSWORD}"
  POSTGRES_DB: "${POSTGRES_DB}"
  MINIO_ROOT_USER: "${MINIO_ROOT_USER}"
  MINIO_ROOT_PASSWORD: "${MINIO_ROOT_PASSWORD}"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${POSTGRES_DEPLOYMENT}
  namespace: ${NAMESPACE}
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: ${POSTGRES_DEPLOYMENT}
  template:
    metadata:
      labels:
        app.kubernetes.io/name: ${POSTGRES_DEPLOYMENT}
    spec:
      containers:
        - name: postgres
          image: postgres:16-alpine
          envFrom:
            - secretRef:
                name: ${SECRET_NAME}
          ports:
            - containerPort: 5432
              name: postgres
          volumeMounts:
            - name: postgres-data
              mountPath: /var/lib/postgresql/data
      volumes:
        - name: postgres-data
          persistentVolumeClaim:
            claimName: ${POSTGRES_PVC}
---
apiVersion: v1
kind: Service
metadata:
  name: ${POSTGRES_SERVICE}
  namespace: ${NAMESPACE}
spec:
  selector:
    app.kubernetes.io/name: ${POSTGRES_DEPLOYMENT}
  ports:
    - name: postgres
      port: 5432
      targetPort: postgres
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${MINIO_DEPLOYMENT}
  namespace: ${NAMESPACE}
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: ${MINIO_DEPLOYMENT}
  template:
    metadata:
      labels:
        app.kubernetes.io/name: ${MINIO_DEPLOYMENT}
    spec:
      containers:
        - name: minio
          image: minio/minio:RELEASE.2025-04-22T22-12-26Z
          args:
            - server
            - /data
            - --console-address
            - :9001
          envFrom:
            - secretRef:
                name: ${SECRET_NAME}
          ports:
            - containerPort: 9000
              name: api
            - containerPort: 9001
              name: console
          volumeMounts:
            - name: minio-data
              mountPath: /data
      volumes:
        - name: minio-data
          persistentVolumeClaim:
            claimName: ${MINIO_PVC}
---
apiVersion: v1
kind: Service
metadata:
  name: ${MINIO_SERVICE}
  namespace: ${NAMESPACE}
spec:
  selector:
    app.kubernetes.io/name: ${MINIO_DEPLOYMENT}
  ports:
    - name: api
      port: 9000
      targetPort: api
    - name: console
      port: 9001
      targetPort: console
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${API_DEPLOYMENT}
  namespace: ${NAMESPACE}
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: ${API_DEPLOYMENT}
  template:
    metadata:
      labels:
        app.kubernetes.io/name: ${API_DEPLOYMENT}
    spec:
      containers:
        - name: api
          image: python:3.12-slim
          workingDir: /workspace/context-governance-gateway
          command:
            - sh
            - -c
            - python -m pip install --no-cache-dir 'fastapi>=0.115' 'pydantic>=2' 'uvicorn>=0.30' && PYTHONPATH=apps/api/src:apps/cli/src:apps/dashboard/src:packages/context_adapters/src:packages/context_core/src:packages/context_observability/src:packages/context_policy/src:packages/context_storage/src exec python -m uvicorn cgg_api.app:app --host 0.0.0.0 --port 8080
          env:
            - name: CGG_ROOT
              value: /var/lib/cgg
            - name: CGG_RUNTIME_PROFILE_STATE
              value: "${PROFILE_LIFECYCLE}"
            - name: CGG_METADATA_BACKEND
              value: local
            - name: CGG_ARTIFACT_BACKEND
              value: local
            - name: PYTHONPATH
              value: apps/api/src:apps/cli/src:apps/dashboard/src:packages/context_adapters/src:packages/context_core/src:packages/context_observability/src:packages/context_policy/src:packages/context_storage/src
          ports:
            - containerPort: 8080
              name: http
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            initialDelaySeconds: 10
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /healthz
              port: http
            initialDelaySeconds: 15
            periodSeconds: 20
          volumeMounts:
            - name: source
              mountPath: /workspace/context-governance-gateway
              readOnly: true
            - name: cgg-state
              mountPath: /var/lib/cgg
      volumes:
        - name: source
          hostPath:
            path: ${OWNER_REPO_ROOT}
            type: Directory
        - name: cgg-state
          persistentVolumeClaim:
            claimName: ${CGG_STATE_PVC}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${WORKER_DEPLOYMENT}
  namespace: ${NAMESPACE}
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: ${WORKER_DEPLOYMENT}
  template:
    metadata:
      labels:
        app.kubernetes.io/name: ${WORKER_DEPLOYMENT}
    spec:
      containers:
        - name: worker
          image: python:3.12-slim
          workingDir: /workspace/context-governance-gateway
          command:
            - sh
            - -c
            - PYTHONPATH=apps/api/src:apps/cli/src:apps/dashboard/src:packages/context_adapters/src:packages/context_core/src:packages/context_observability/src:packages/context_policy/src:packages/context_storage/src exec python -m cgg_api.worker
          env:
            - name: CGG_ROOT
              value: /var/lib/cgg
            - name: CGG_RUNTIME_PROFILE_STATE
              value: "${PROFILE_LIFECYCLE}"
            - name: PYTHONPATH
              value: apps/api/src:apps/cli/src:apps/dashboard/src:packages/context_adapters/src:packages/context_core/src:packages/context_observability/src:packages/context_policy/src:packages/context_storage/src
          volumeMounts:
            - name: source
              mountPath: /workspace/context-governance-gateway
              readOnly: true
            - name: cgg-state
              mountPath: /var/lib/cgg
      volumes:
        - name: source
          hostPath:
            path: ${OWNER_REPO_ROOT}
            type: Directory
        - name: cgg-state
          persistentVolumeClaim:
            claimName: ${CGG_STATE_PVC}
---
apiVersion: v1
kind: Service
metadata:
  name: ${API_SERVICE}
  namespace: ${NAMESPACE}
spec:
  selector:
    app.kubernetes.io/name: ${API_DEPLOYMENT}
  ports:
    - name: http
      port: 8080
      targetPort: http
EOF
}

seed_projection_if_needed() {
  local artifact_id=""
  if [[ -f "${SEED_ARTIFACT_FILE}" ]]; then
    artifact_id="$(cat "${SEED_ARTIFACT_FILE}")"
  fi
  if [[ -n "${artifact_id}" ]]; then
    if kubectl_cmd -n "${NAMESPACE}" exec -i "deployment/${API_DEPLOYMENT}" -- \
      python - "${artifact_id}" <<'PY' >/dev/null 2>&1
from pathlib import Path
import os
import sys

root = Path(os.environ["CGG_ROOT"])
artifact_id = sys.argv[1]
packet = root / ".cgg" / "packets" / f"{artifact_id}.packet.json"
raise SystemExit(0 if packet.is_file() else 1)
PY
    then
      return
    fi
  fi

  artifact_id="$(
    kubectl_cmd -n "${NAMESPACE}" exec -i "deployment/${API_DEPLOYMENT}" -- python - <<'PY'
import json
from pathlib import Path

from cgg_api import ContextGatewayService, RuntimeSettings

service = ContextGatewayService(RuntimeSettings.from_env())
result = service.project_text(
    "ERROR CGG_DEVINT_SEED failed with API_TOKEN=devint-seed-secret\n",
    source_label="devint-seed",
    profile_name="developer",
    budget_tokens=200,
)
print(result["artifact_id"])
PY
  )"
  printf '%s\n' "${artifact_id}" >"${SEED_ARTIFACT_FILE}"
}
