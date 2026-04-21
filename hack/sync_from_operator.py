#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml


REPO_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_DIR = REPO_DIR.parent
DEFAULT_OPERATOR_REPO = WORKSPACE_DIR / "eloq-operator"
CHART_DIR = REPO_DIR / "charts" / "eloq-operator"
TEMPLATES_DIR = CHART_DIR / "templates"
RENDERED_CHART = Path("/tmp/eloq-operator-rendered.yaml")
OPERATOR_REPO = DEFAULT_OPERATOR_REPO
GENERATED_PATHS = [
    CHART_DIR / "templates" / "crds",
    CHART_DIR / "templates" / "controller-manager" / "manager-rbac.yaml",
    CHART_DIR / "templates" / "controller-manager" / "leader-election-rbac.yaml",
    CHART_DIR / "templates" / "controller-manager" / "proxy-rbac.yaml",
    CHART_DIR / "templates" / "controller-manager" / "deployment.yaml",
    CHART_DIR / "templates" / "gatewayclass.yaml",
    CHART_DIR / "templates" / "metrics" / "metrics-rbac.yaml",
    CHART_DIR / "templates" / "webhook",
]
ENV_VALUE_OVERRIDES = {
    "ENABLE_LEADER_ELECTION": "{{ .Values.controllerManager.enableLeaderElection | default true | quote }}",
    "ENABLE_WEBHOOKS": "{{ .Values.controllerManager.enableWebhooks | default true | quote }}",
    "ENABLE_RECONCILER": "{{ .Values.controllerManager.enableReconciler | default true | quote }}",
    "WATCH_NAMESPACE": "{{ .Values.controllerManager.watchNamespaces | quote }}",
    "DSYNC_IMAGE": "{{ .Values.controllerManager.dsyncImage | quote }}",
    "REDIS_SHAKE_IMAGE": "{{ .Values.controllerManager.redisShakeImage | quote }}",
    "CACHE_SYNC_PERIOD": "{{ .Values.controllerManager.cacheSyncPeriod | quote }}",
    "KUBE_API_QPS": "{{ .Values.controllerManager.kubeApiQps | quote }}",
    "KUBE_API_BURST": "{{ .Values.controllerManager.kubeApiBurst | quote }}",
    "GOOGLE_CLOUD_PROJECT": "{{ .Values.controllerManager.googleCloudProject | quote }}",
    "GCP_PSC_VPC": "{{ .Values.controllerManager.gcpPscVpc | quote }}",
    "GCP_DNS_PROJECT_ID": "{{ .Values.controllerManager.gcpDnsProjectId | quote }}",
    "GCP_DNS_MANAGED_ZONE": "{{ .Values.controllerManager.gcpDnsManagedZone | quote }}",
    "GATEWAY_NAMESPACE": "{{ .Values.controllerManager.gatewayNamespace | quote }}",
    "CLUSTER_ISSUER": "{{ .Values.controllerManager.clusterIssuer | quote }}",
    "GATEWAY_CLASS_NAME": "{{ .Values.controllerManager.gatewayClassName | quote }}",
    "GATEWAY_NAME": "{{ .Values.controllerManager.gatewayName | quote }}",
    "GATEWAY_CERTIFICATE_NAME": "{{ .Values.controllerManager.gatewayCertificateName | quote }}",
    "GATEWAY_CERTIFICATE_SECRET_NAME": "{{ .Values.controllerManager.gatewayCertificateSecretName | quote }}",
    "ENVOYPROXY_MIN_REPLICAS": "{{ .Values.controllerManager.envoyProxyMinReplicas | quote }}",
    "ENVOYPROXY_MAX_REPLICAS": "{{ .Values.controllerManager.envoyProxyMaxReplicas | quote }}",
}
TARGET_TO_PATHS = {
    "crds": [CHART_DIR / "templates" / "crds"],
    "rbac": [
        CHART_DIR / "templates" / "controller-manager" / "manager-rbac.yaml",
        CHART_DIR / "templates" / "controller-manager" / "leader-election-rbac.yaml",
        CHART_DIR / "templates" / "controller-manager" / "proxy-rbac.yaml",
        CHART_DIR / "templates" / "metrics" / "metrics-rbac.yaml",
    ],
    "gatewayclass": [CHART_DIR / "templates" / "gatewayclass.yaml"],
    "webhook": [CHART_DIR / "templates" / "webhook"],
    "deployment": [CHART_DIR / "templates" / "controller-manager" / "deployment.yaml"],
}


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"required tool not found in PATH: {name}")


def dump_yaml(value: object, indent: int = 0) -> str:
    text = yaml.safe_dump(value, sort_keys=False, width=4096).rstrip()
    if indent:
        text = text.replace("\n", "\n" + " " * indent)
    return text


def render_mapping_list_item(value: dict) -> list[str]:
    dumped = yaml.safe_dump(value, sort_keys=False).rstrip().splitlines()
    return [f"- {dumped[0]}"] + [f"  {line}" for line in dumped[1:]]


def render_env_list_item(env: dict) -> list[str]:
    name = env.get("name")
    if name in ENV_VALUE_OVERRIDES and "value" in env:
        return [f"- name: {name}", f"  value: {ENV_VALUE_OVERRIDES[name]}"]
    return render_mapping_list_item(env)


def run(
    cmd: list[str], cwd: Path | None = None, capture_output: bool = False
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        check=True,
        capture_output=capture_output,
    )


def resolve_targets(selected: list[str]) -> list[str]:
    return (
        ["crds", "rbac", "gatewayclass", "webhook", "deployment"]
        if not selected or "all" in selected
        else selected
    )


def generated_paths_for_targets(targets: list[str]) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for target in targets:
        for path in TARGET_TO_PATHS[target]:
            if path not in seen:
                paths.append(path)
                seen.add(path)
    return paths


def remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def copy_path(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)


def sync_crds() -> None:
    src_dir = OPERATOR_REPO / "config" / "crd" / "bases"
    dst_dir = TEMPLATES_DIR / "crds"
    if not src_dir.is_dir():
        raise SystemExit(f"operator CRD directory not found: {src_dir}")

    dst_dir.mkdir(parents=True, exist_ok=True)
    for file in dst_dir.glob("*.yaml"):
        file.unlink()

    for src_file in sorted(src_dir.glob("*.yaml")):
        lines = src_file.read_text().splitlines()
        output: list[str] = []
        in_metadata = False
        inserted = False

        for idx, line in enumerate(lines):
            output.append(line)
            if line == "metadata:":
                in_metadata = True
                continue
            if in_metadata and line == "  annotations:":
                output.extend(
                    [
                        "    {{- if .Values.keepCrds }}",
                        '    "helm.sh/resource-policy": keep',
                        "    {{- end }}",
                    ]
                )
                inserted = True
                continue
            if in_metadata and not inserted:
                next_line = lines[idx + 1] if idx + 1 < len(lines) else ""
                if next_line.startswith("  ") and not next_line.startswith("    "):
                    output.extend(
                        [
                            "  annotations:",
                            "    {{- if .Values.keepCrds }}",
                            '    "helm.sh/resource-policy": keep',
                            "    {{- end }}",
                        ]
                    )
                    inserted = True
                    in_metadata = False

        if not inserted:
            raise SystemExit(f"failed to inject keepCrds annotation into {src_file}")

        (dst_dir / src_file.name).write_text("\n".join(output) + "\n")

    print(f"synced CRDs from {src_dir} to {dst_dir}")


def extract_rules(src_file: Path) -> str:
    lines = src_file.read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line == "rules:")
    return "\n".join(lines[start:])


def sync_rbac() -> None:
    config_dir = OPERATOR_REPO / "config" / "rbac"
    controller_dir = TEMPLATES_DIR / "controller-manager"
    metrics_dir = TEMPLATES_DIR / "metrics"

    manager_rules = extract_rules(config_dir / "role.yaml")
    leader_rules = extract_rules(config_dir / "leader_election_role.yaml")
    proxy_rules = extract_rules(config_dir / "auth_proxy_role.yaml")
    metrics_rules = extract_rules(config_dir / "auth_proxy_client_clusterrole.yaml")

    (controller_dir / "manager-rbac.yaml").write_text(
        "{{- /*\n"
        "Generated from eloq-operator/config/rbac/role.yaml via hack/sync_from_operator.py\n"
        "*/ -}}\n"
        "apiVersion: rbac.authorization.k8s.io/v1\n"
        "kind: ClusterRole\n"
        "metadata:\n"
        '  name: {{ include "eloq-operator.fullname" . }}-manager-cluster-role\n'
        "  labels:\n"
        "    app.kubernetes.io/component: rbac\n"
        '    {{- include "eloq-operator.commonLabels" . | nindent 4 }}\n'
        f"{manager_rules}\n"
        "---\n"
        "apiVersion: rbac.authorization.k8s.io/v1\n"
        "kind: ClusterRoleBinding\n"
        "metadata:\n"
        '  name: {{ include "eloq-operator.fullname" . }}-manager-cluster-rolebinding\n'
        "  labels:\n"
        "    app.kubernetes.io/component: rbac\n"
        '    {{- include "eloq-operator.commonLabels" . | nindent 4 }}\n'
        "roleRef:\n"
        "  apiGroup: rbac.authorization.k8s.io\n"
        "  kind: ClusterRole\n"
        '  name: {{ include "eloq-operator.fullname" . }}-manager-cluster-role\n'
        "subjects:\n"
        "- kind: ServiceAccount\n"
        "  name: {{ .Values.controllerManager.serviceAccount.name }}\n"
        "  namespace: {{ .Release.Namespace }}\n"
    )

    (controller_dir / "leader-election-rbac.yaml").write_text(
        "{{- /*\n"
        "Generated from eloq-operator/config/rbac/leader_election_role.yaml via hack/sync_from_operator.py\n"
        "*/ -}}\n"
        "apiVersion: rbac.authorization.k8s.io/v1\n"
        "kind: Role\n"
        "metadata:\n"
        '  name: {{ include "eloq-operator.name" . }}-leader-election-role\n'
        "  namespace: {{ .Release.Namespace }}\n"
        "  labels:\n"
        "    app.kubernetes.io/component: rbac\n"
        '    {{- include "eloq-operator.commonLabels" . | nindent 4 }}\n'
        f"{leader_rules}\n"
        "---\n"
        "apiVersion: rbac.authorization.k8s.io/v1\n"
        "kind: RoleBinding\n"
        "metadata:\n"
        '  name: {{ include "eloq-operator.name" . }}-leader-election-rolebinding\n'
        "  namespace: {{ .Release.Namespace }}\n"
        "  labels:\n"
        "    app.kubernetes.io/component: rbac\n"
        '    {{- include "eloq-operator.commonLabels" . | nindent 4 }}\n'
        "roleRef:\n"
        "  apiGroup: rbac.authorization.k8s.io\n"
        "  kind: Role\n"
        '  name: {{ include "eloq-operator.name" . }}-leader-election-role\n'
        "subjects:\n"
        "- kind: ServiceAccount\n"
        "  name: {{ .Values.controllerManager.serviceAccount.name }}\n"
        "  namespace: {{ .Release.Namespace }}\n"
    )

    (controller_dir / "proxy-rbac.yaml").write_text(
        "{{- /*\n"
        "Generated from eloq-operator/config/rbac/auth_proxy_role.yaml via hack/sync_from_operator.py\n"
        "*/ -}}\n"
        "apiVersion: rbac.authorization.k8s.io/v1\n"
        "kind: ClusterRole\n"
        "metadata:\n"
        '  name: {{ include "eloq-operator.fullname" . }}-proxy-cluster-role\n'
        "  labels:\n"
        "    app.kubernetes.io/component: kube-rbac-proxy\n"
        '    {{- include "eloq-operator.commonLabels" . | nindent 4 }}\n'
        f"{proxy_rules}\n"
        "---\n"
        "apiVersion: rbac.authorization.k8s.io/v1\n"
        "kind: ClusterRoleBinding\n"
        "metadata:\n"
        '  name: {{ include "eloq-operator.fullname" . }}-proxy-cluster-rolebinding\n'
        "  labels:\n"
        "    app.kubernetes.io/component: kube-rbac-proxy\n"
        '    {{- include "eloq-operator.commonLabels" . | nindent 4 }}\n'
        "roleRef:\n"
        "  apiGroup: rbac.authorization.k8s.io\n"
        "  kind: ClusterRole\n"
        '  name: {{ include "eloq-operator.fullname" . }}-proxy-cluster-role\n'
        "subjects:\n"
        "- kind: ServiceAccount\n"
        "  name: {{ .Values.controllerManager.serviceAccount.name }}\n"
        "  namespace: {{ .Release.Namespace }}\n"
    )

    (metrics_dir / "metrics-rbac.yaml").write_text(
        "{{- /*\n"
        "Generated from eloq-operator/config/rbac/auth_proxy_client_clusterrole.yaml via hack/sync_from_operator.py\n"
        "*/ -}}\n"
        "{{- if .Values.controllerManager.enableMonitor }}\n"
        "apiVersion: rbac.authorization.k8s.io/v1\n"
        "kind: ClusterRole\n"
        "metadata:\n"
        '  name: {{ include "eloq-operator.fullname" . }}-metrics-reader-cluster-role\n'
        "  labels:\n"
        "    app.kubernetes.io/component: kube-rbac-proxy\n"
        '    {{- include "eloq-operator.commonLabels" . | nindent 4 }}\n'
        f"{metrics_rules}\n"
        "{{- end }}\n"
    )

    print(f"synced RBAC from {config_dir}")


def sync_webhook() -> None:
    service_src = OPERATOR_REPO / "config" / "webhook" / "service.yaml"
    manifest_src = OPERATOR_REPO / "config" / "webhook" / "manifests.yaml"
    webhook_dir = TEMPLATES_DIR / "webhook"

    service_text = service_src.read_text()
    service_text = service_text.replace(
        "name: webhook-service",
        'name: {{ include "eloq-operator.name" . }}-webhook-service',
    )
    service_text = service_text.replace(
        "namespace: system", "namespace: {{ .Release.Namespace }}"
    )
    service_text = service_text.replace(
        "    control-plane: controller-manager\n"
        "    app.kubernetes.io/name: eloq-operator\n"
        "    app.kubernetes.io/instance: eloq-operator",
        '    {{- include "eloq-operator.selectorLabels" . | nindent 4 }}\n'
        '    {{- include "eloq-operator.controlPlaneLabels" . | nindent 4 }}',
    )
    (webhook_dir / "webhook-service.yaml").write_text(
        "{{- /*\n"
        "Generated from eloq-operator/config/webhook/service.yaml via hack/sync_from_operator.py\n"
        "*/ -}}\n"
        "{{- if .Values.controllerManager.enableWebhooks }}\n"
        f"{service_text}\n"
        "{{- end }}\n"
    )

    for doc in yaml.safe_load_all(manifest_src.read_text()):
        if not doc:
            continue
        kind = doc["kind"]
        name = doc["metadata"]["name"]
        if kind == "MutatingWebhookConfiguration":
            out_name = "mutating-webhook-configuration.yaml"
            resource_name = '{{ include "eloq-operator.fullname" . }}-mutating-webhook-configuration'
        elif kind == "ValidatingWebhookConfiguration":
            out_name = "validating-webhook-configuration.yaml"
            resource_name = '{{ include "eloq-operator.fullname" . }}-validating-webhook-configuration'
        else:
            continue

        doc["metadata"] = {
            "name": resource_name,
            "annotations": {
                "cert-manager.io/inject-ca-from": '{{ .Release.Namespace }}/{{ include "eloq-operator.name" . }}-serving-cert',
            },
            "labels": {
                "app.kubernetes.io/component": "webhook",
                "__HELM_COMMON_LABELS__": True,
            },
        }
        for webhook in doc.get("webhooks", []):
            service = webhook.get("clientConfig", {}).get("service")
            if not service:
                continue
            service["name"] = '{{ include "eloq-operator.name" . }}-webhook-service'
            service["namespace"] = "{{ .Release.Namespace }}"

        text = dump_yaml(doc)
        text = text.replace("'{{ .Release.Namespace }}'", "{{ .Release.Namespace }}")
        text = text.replace(
            "'{{ include \"eloq-operator.name\" . }}-webhook-service'",
            '{{ include "eloq-operator.name" . }}-webhook-service',
        )
        text = text.replace(
            "'{{ include \"eloq-operator.fullname\" . }}-mutating-webhook-configuration'",
            '{{ include "eloq-operator.fullname" . }}-mutating-webhook-configuration',
        )
        text = text.replace(
            "'{{ include \"eloq-operator.fullname\" . }}-validating-webhook-configuration'",
            '{{ include "eloq-operator.fullname" . }}-validating-webhook-configuration',
        )
        text = text.replace(
            "    __HELM_COMMON_LABELS__: true",
            '    {{- include "eloq-operator.commonLabels" . | nindent 4 }}',
        )
        text = text.replace(
            "'{{ .Release.Namespace }}/{{ include \"eloq-operator.name\" . }}-serving-cert'",
            "'{{ .Release.Namespace }}/{{ include \"eloq-operator.name\" . }}-serving-cert'",
        )
        (webhook_dir / out_name).write_text(
            "{{- /*\n"
            f"Generated from eloq-operator/config/webhook/{'manifests.yaml'} via hack/sync_from_operator.py\n"
            "*/ -}}\n"
            "{{- if .Values.controllerManager.enableWebhooks }}\n"
            f"{text}\n"
            "{{- end }}\n"
        )
        _ = name

    print(f"synced webhook manifests from {OPERATOR_REPO / 'config' / 'webhook'}")


def sync_gatewayclass() -> None:
    src = OPERATOR_REPO / "config" / "gatewayclass" / "eloq-gateway-class.yaml"
    doc = yaml.safe_load(src.read_text())
    if not doc or doc.get("kind") != "GatewayClass":
        raise SystemExit(f"unexpected gatewayclass manifest: {src}")

    out = TEMPLATES_DIR / "gatewayclass.yaml"
    out.write_text(
        "{{- /*\n"
        "Generated from eloq-operator/config/gatewayclass/eloq-gateway-class.yaml via hack/sync_from_operator.py\n"
        "*/ -}}\n"
        "{{- if .Values.controllerManager.createGatewayClass }}\n"
        "apiVersion: gateway.networking.k8s.io/v1\n"
        "kind: GatewayClass\n"
        "metadata:\n"
        "  name: {{ .Values.controllerManager.gatewayClassName }}\n"
        "  labels:\n"
        '    {{- include "eloq-operator.commonLabels" . | nindent 4 }}\n'
        "spec:\n"
        "  controllerName: {{ .Values.controllerManager.gatewayClassControllerName }}\n"
        "{{- end }}\n"
    )
    print(f"synced gatewayclass manifest from {src}")


def sync_deployment() -> None:
    require_tool("kustomize")
    rendered = run(
        ["kustomize", "build", "config/default"],
        cwd=OPERATOR_REPO,
        capture_output=True,
    ).stdout
    docs = [doc for doc in yaml.safe_load_all(rendered) if doc]
    deployment = next(doc for doc in docs if doc.get("kind") == "Deployment")

    pod_spec = deployment["spec"]["template"]["spec"]
    manager = next(
        container
        for container in pod_spec["containers"]
        if container["name"] == "manager"
    )
    proxy = next(
        container
        for container in pod_spec["containers"]
        if container["name"] == "kube-rbac-proxy"
    )

    manager_args = [
        "- --health-probe-bind-address=:{{ .Values.controllerManager.healthPort }}",
        "- --metrics-bind-address=127.0.0.1:{{ .Values.controllerManager.metricPort }}",
        "{{- if .Values.controllerManager.watchNamespaces }}",
        "- --namespace={{ .Values.controllerManager.watchNamespaces }}",
        "{{- end }}",
    ]
    for arg in manager.get("args", []):
        if arg.startswith("--leader-elect="):
            manager_args.extend(
                [
                    "{{- if .Values.controllerManager.enableLeaderElection }}",
                    "- --leader-elect",
                    "{{- else }}",
                    "- --leader-elect=false",
                    "{{- end }}",
                ]
            )
        elif arg.startswith("--webhooks="):
            manager_args.append(
                "- --webhooks={{ .Values.controllerManager.enableWebhooks | default true }}"
            )
        elif arg.startswith("--enable-reconciler="):
            manager_args.append(
                "- --enable-reconciler={{ .Values.controllerManager.enableReconciler | default true }}"
            )
        else:
            manager_args.append(f"- {arg}")

    proxy_args = []
    for arg in proxy.get("args", []):
        if arg.startswith("--upstream=http://127.0.0.1:"):
            proxy_args.append(
                "- --upstream=http://127.0.0.1:{{ .Values.controllerManager.metricPort }}/"
            )
        else:
            proxy_args.append(f"- {arg}")

    env_lines: list[str] = []
    for env in manager.get("env", []):
        env_lines.extend(render_env_list_item(env))

    env_lines.extend(
        [
            "- name: KUBERNETES_LIST_WATCH_LIST_ENABLED",
            '  value: "false"',
            "- name: KUBE_FEATURE_WatchListClient",
            '  value: "false"',
        ]
    )

    kube_api_qps_defined = any(
        env.get("name") == "KUBE_API_QPS" for env in manager.get("env", [])
    )
    kube_api_burst_defined = any(
        env.get("name") == "KUBE_API_BURST" for env in manager.get("env", [])
    )
    if not kube_api_qps_defined:
        env_lines.extend(
            [
                "- name: KUBE_API_QPS",
                "  value: {{ .Values.controllerManager.kubeApiQps | quote }}",
            ]
        )
    if not kube_api_burst_defined:
        env_lines.extend(
            [
                "- name: KUBE_API_BURST",
                "  value: {{ .Values.controllerManager.kubeApiBurst | quote }}",
            ]
        )

    liveness = manager["livenessProbe"]
    readiness = manager["readinessProbe"]
    out = TEMPLATES_DIR / "controller-manager" / "deployment.yaml"

    lines = [
        "{{- /*",
        "Generated from eloq-operator/config/default via hack/sync_from_operator.py",
        "The base structure comes from `kustomize build config/default`; Helm values only override install-time knobs.",
        "*/ -}}",
        "apiVersion: apps/v1",
        "kind: Deployment",
        "metadata:",
        '  name: {{ include "eloq-operator.name" . }}-controller-manager',
        "  namespace: {{ .Release.Namespace }}",
        "  labels:",
        "    app.kubernetes.io/component: controller-manager",
        '    {{- include "eloq-operator.commonLabels" . | nindent 4 }}',
        "spec:",
        f"  replicas: {deployment['spec'].get('replicas', 1)}",
        "  selector:",
        "    matchLabels:",
        '      {{- include "eloq-operator.selectorLabels" . | nindent 6 }}',
        '      {{- include "eloq-operator.controlPlaneLabels" . | nindent 6 }}',
        "  template:",
        "    metadata:",
    ]

    annotations = deployment["spec"]["template"].get("metadata", {}).get("annotations")
    if annotations:
        lines.extend(["      annotations:", "        " + dump_yaml(annotations, 8)])

    lines.extend(
        [
            "      labels:",
            '        {{- include "eloq-operator.selectorLabels" . | nindent 8 }}',
            '        {{- include "eloq-operator.controlPlaneLabels" . | nindent 8 }}',
            "        app.kubernetes.io/component: controller-manager",
            "    spec:",
            "      {{- if .Values.controllerManager.nodeSelector }}",
            "      nodeSelector:",
            "        {{- toYaml .Values.controllerManager.nodeSelector | nindent 8 }}",
            "      {{- end }}",
            "      serviceAccountName: {{ .Values.controllerManager.serviceAccount.name }}",
            "      {{- with .Values.controllerManager.imagePullSecrets }}",
            "      imagePullSecrets:",
            "      {{- toYaml . | nindent 6 }}",
            "      {{- end }}",
            "      affinity:",
            "        " + dump_yaml(pod_spec.get("affinity", {}), 8),
            "      securityContext:",
            "        " + dump_yaml(pod_spec.get("securityContext", {}), 8),
            f"      terminationGracePeriodSeconds: {pod_spec.get('terminationGracePeriodSeconds', 10)}",
            "      volumes:",
            "      - name: cert",
            "        secret:",
            "          defaultMode: 420",
            '          secretName: {{ include "eloq-operator.name" . }}-webhook-server-cert',
            "      containers:",
            f"      - name: {manager['name']}",
            "        image: {{ .Values.controllerManager.image.repository }}:{{ .Values.controllerManager.image.tag }}",
            '        imagePullPolicy: {{ .Values.controllerManager.imagePullPolicy | default "IfNotPresent" }}',
            "        command:",
            "          " + dump_yaml(manager.get("command", []), 10),
            "        args:",
        ]
    )

    lines.extend("        " + item for item in manager_args)
    lines.extend(
        [
            "        ports:",
            "          " + dump_yaml(manager.get("ports", []), 10),
            "        livenessProbe:",
            "          httpGet:",
            f"            path: {liveness['httpGet']['path']}",
            "            port: {{ .Values.controllerManager.healthPort }}",
            f"          initialDelaySeconds: {liveness['initialDelaySeconds']}",
            f"          periodSeconds: {liveness['periodSeconds']}",
            "        readinessProbe:",
            "          httpGet:",
            f"            path: {readiness['httpGet']['path']}",
            "            port: {{ .Values.controllerManager.healthPort }}",
            f"          initialDelaySeconds: {readiness['initialDelaySeconds']}",
            f"          periodSeconds: {readiness['periodSeconds']}",
            "        resources: {{- toYaml .Values.controllerManager.resources | nindent 10 }}",
            "        securityContext:",
            "          " + dump_yaml(manager.get("securityContext", {}), 10),
            "        volumeMounts:",
            "          " + dump_yaml(manager.get("volumeMounts", []), 10),
            "        env:",
        ]
    )
    lines.extend("        " + item for item in env_lines)
    lines.extend(
        [
            f"      - name: {proxy['name']}",
            f"        image: {proxy['image']}",
            f"        imagePullPolicy: {proxy['imagePullPolicy']}",
            "        args:",
        ]
    )
    lines.extend("        " + item for item in proxy_args)
    lines.extend(
        [
            "        ports:",
            "          " + dump_yaml(proxy.get("ports", []), 10),
            "        resources:",
            "          " + dump_yaml(proxy.get("resources", {}), 10),
            "        securityContext:",
            "          " + dump_yaml(proxy.get("securityContext", {}), 10),
        ]
    )

    out.write_text("\n".join(lines) + "\n")
    print(f"synced deployment from {OPERATOR_REPO / 'config' / 'default'}")


def sync(selected: list[str]) -> None:
    targets = resolve_targets(selected)
    for target in targets:
        if target == "crds":
            sync_crds()
        elif target == "rbac":
            sync_rbac()
        elif target == "gatewayclass":
            sync_gatewayclass()
        elif target == "webhook":
            sync_webhook()
        elif target == "deployment":
            sync_deployment()
        else:
            raise SystemExit(f"unknown sync target: {target}")


def check_sync(selected: list[str]) -> None:
    require_tool("git")
    targets = resolve_targets(selected)
    paths = generated_paths_for_targets(targets)

    with tempfile.TemporaryDirectory(prefix="eloq-chart-sync-") as tmp_dir:
        backup_root = Path(tmp_dir)
        backups: list[tuple[Path, Path, bool]] = []
        for path in paths:
            backup_path = backup_root / path.relative_to(REPO_DIR)
            existed = path.exists()
            if existed:
                copy_path(path, backup_path)
            backups.append((path, backup_path, existed))

        try:
            sync(targets)
            result = subprocess.run(
                [
                    "git",
                    "diff",
                    "--exit-code",
                    "--",
                    *[str(path.relative_to(REPO_DIR)) for path in paths],
                ],
                cwd=REPO_DIR,
                text=True,
                capture_output=True,
            )
            if result.returncode != 0:
                if result.stdout:
                    sys.stdout.write(result.stdout)
                if result.stderr:
                    sys.stderr.write(result.stderr)
                raise SystemExit(
                    "generated chart artifacts are out of sync with the selected operator source; "
                    "run `python3 hack/sync_from_operator.py sync` and commit the result"
                )
        finally:
            for path, backup_path, existed in backups:
                remove_path(path)
                if existed:
                    copy_path(backup_path, path)

    print("generated chart artifacts match the selected operator source")


def render(release_name: str, rendered_path: Path) -> None:
    require_tool("helm")
    result = run(
        ["helm", "template", release_name, str(CHART_DIR)],
        cwd=REPO_DIR,
        capture_output=True,
    )
    rendered_path.write_text(result.stdout)
    print(f"rendered chart to {rendered_path}")


def verify(release_name: str, rendered_path: Path, server_dry_run: bool) -> None:
    require_tool("helm")
    run(["helm", "lint", str(CHART_DIR)], cwd=REPO_DIR)
    render(release_name, rendered_path)
    if server_dry_run:
        require_tool("kubectl")
        run(
            ["kubectl", "apply", "--dry-run=server", "-f", str(rendered_path)],
            cwd=REPO_DIR,
        )
        print("server-side dry-run validation passed")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync generated Helm chart artifacts from eloq-operator."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_parser = subparsers.add_parser(
        "sync", help="Sync generated resources from eloq-operator."
    )
    sync_parser.add_argument(
        "--operator-repo",
        type=Path,
        default=DEFAULT_OPERATOR_REPO,
        help=f"Path to the eloq-operator repository. Defaults to {DEFAULT_OPERATOR_REPO}.",
    )
    sync_parser.add_argument(
        "targets",
        nargs="*",
        choices=["all", "crds", "rbac", "gatewayclass", "webhook", "deployment"],
        help="Resource groups to sync. Defaults to all.",
    )

    check_sync_parser = subparsers.add_parser(
        "check-sync",
        help="Sync generated resources and fail if tracked generated artifacts would change.",
    )
    check_sync_parser.add_argument(
        "--operator-repo",
        type=Path,
        default=DEFAULT_OPERATOR_REPO,
        help=f"Path to the eloq-operator repository. Defaults to {DEFAULT_OPERATOR_REPO}.",
    )
    check_sync_parser.add_argument(
        "targets",
        nargs="*",
        choices=["all", "crds", "rbac", "gatewayclass", "webhook", "deployment"],
        help="Resource groups to sync. Defaults to all.",
    )

    render_parser = subparsers.add_parser("render", help="Render the Helm chart.")
    render_parser.add_argument("--release-name", default="test")
    render_parser.add_argument("--output", type=Path, default=RENDERED_CHART)

    verify_parser = subparsers.add_parser(
        "verify", help="Lint and render the Helm chart."
    )
    verify_parser.add_argument("--release-name", default="test")
    verify_parser.add_argument("--output", type=Path, default=RENDERED_CHART)
    verify_parser.add_argument("--server-dry-run", action="store_true")

    return parser


def main() -> None:
    global OPERATOR_REPO
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "sync":
        OPERATOR_REPO = args.operator_repo.resolve()
        sync(args.targets)
    elif args.command == "check-sync":
        OPERATOR_REPO = args.operator_repo.resolve()
        check_sync(args.targets)
    elif args.command == "render":
        render(args.release_name, args.output)
    elif args.command == "verify":
        verify(args.release_name, args.output, args.server_dry_run)
    else:
        parser.error(f"unsupported command: {args.command}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        if exc.stdout:
            sys.stdout.write(exc.stdout)
        if exc.stderr:
            sys.stderr.write(exc.stderr)
        raise SystemExit(exc.returncode)
