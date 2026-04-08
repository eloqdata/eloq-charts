## eloq operator Helm Chart

The current chart is for installing the eloq-operator (including CRD for `EloqDBCluster`).

### Development workflow

This chart now treats `eloq-operator` as the source of truth for generated install artifacts:

- CRDs come from `eloq-operator/config/crd/bases`
- RBAC comes from `eloq-operator/config/rbac`
- Webhook manifests come from `eloq-operator/config/webhook`
- The controller manager `Deployment` base comes from `kustomize build eloq-operator/config/default`

To sync generated artifacts from the sibling `eloq-operator` repository:

```shell
python3 hack/sync_from_operator.py sync
```

To sync from an explicit operator checkout:

```shell
python3 hack/sync_from_operator.py sync --operator-repo /path/to/eloq-operator
```

To sync only one category:

```shell
python3 hack/sync_from_operator.py sync crds
python3 hack/sync_from_operator.py sync rbac
python3 hack/sync_from_operator.py sync webhook
python3 hack/sync_from_operator.py sync deployment
```

To validate the chart after syncing:

```shell
python3 hack/sync_from_operator.py verify
```

To verify that committed generated artifacts already match a given operator checkout
without leaving generated changes in the working tree:

```shell
python3 hack/sync_from_operator.py check-sync --operator-repo /path/to/eloq-operator
```

If your local environment can reach the target Kubernetes API server, you can also run server-side schema validation:

```shell
python3 hack/sync_from_operator.py verify --server-dry-run
```

To render the chart to a file:

```shell
python3 hack/sync_from_operator.py render
```

### Install the eloq-operator

[Helm](https://helm.sh) must be installed to use the charts. Please refer to
Helm's [documentation](https://helm.sh/docs) to get started.

Once Helm has been set up correctly, install the chart directly from the OCI registry:

```shell
# Install eloq-operator from OCI registry
helm install eloq-operator \
  oci://ghcr.io/eloqdata/charts/eloq-operator \
  --version 1.0.1 \
  --namespace eloq-operator-system \
  --create-namespace
```

> NOTE: If the installation specifies namespace please create it first. Alternatively, use `--create-namespace` flag.

#### Install with Node Selector

To schedule the eloq-operator controller manager on specific nodes, you can specify a nodeSelector:

```shell
helm install eloq-operator \
  oci://ghcr.io/eloqdata/charts/eloq-operator \
  --version 1.0.1 \
  --namespace eloq-operator-system \
  --create-namespace \
  --set controllerManager.nodeSelector."eloqdata\.com/node"=control-plane
```

#### Install with Specific Image Version

To install the operator with a specific image version:

```shell
helm install eloq-operator \
  oci://ghcr.io/eloqdata/charts/eloq-operator \
  --version 1.0.1 \
  --namespace eloq-operator-system \
  --create-namespace \
  --set controllerManager.image.tag=1.0.1
```

### Upgrade the eloq-operator

To upgrade an existing eloq-operator release:

```shell
helm upgrade eloq-operator \
  oci://ghcr.io/eloqdata/charts/eloq-operator \
  --version 1.0.1 \
  --namespace eloq-operator-system
```

### Check the installed eloq operator

```shell
helm list --namespace eloq-operator-system
```

### Uninstall Helm Release and CRDs

The default value of `keepCrds` in `values.yaml` is set to `true`. This means that even after uninstalling the release,
Custom Resource Definitions (CRDs) associated with the release are retained. This behavior is particularly useful for
preserving CRDs that you might want to keep for future use or to maintain data integrity.

To uninstall a Helm release, use the following command:

```shell
helm uninstall eloq-operator --namespace eloq-operator-system
```

In cases where you wish to delete the CRDs manually, use the following command:

``` shell
kubectl delete crd EloqDBClusters.eloq-service.eloqdata.com
```

Alternatively, setting `keepCrds` to false will result in the automatic deletion of the associated CRDs when the Helm
release is uninstalled.

### eloq-operator chart arguments

The following parameters can be overridden by helm --set. For example: --set controllerManager.serviceAccoun="
eloq-op-sa"

| Name                                         | Type   | Default Value                       | Description                                                                                                 |
|----------------------------------------------|--------|-------------------------------------|-------------------------------------------------------------------------------------------------------------|
| nameOverride                                 | string | ""                                  | Overrides the "eloq-operator" with this name.                                                               |
| controllerManager.serviceAccount.name        | string | eloq-operator-controller-manager | The service account name of the eloq operator controller manager pods.                                      |
| controllerManager.serviceAccount.annotations | object | {}                                  | Annotations for the `controllerManager.serviceAccount`.                                                     |
| controllerManager.image.repository           | string | eloqdata/eloq-operator              | The image name of the eloq operator.                                                                        |
| controllerManager.image.tag                  | string | 1.1.0                               | The version tag for eloq operator docker image.                                                             |
| controllerManager.imagePullPolicy            | string | Always                              | -                                                                                                           |
| controllerManager.imagePullSecrets           | object | {}                                  | -                                                                                                           |
| controllerManager.resources                  | object | Same format as k8s resource         | Resource requests and limits for eloq operator controller manager pods.                                     |
| controllerManager.healthPort                 | string | 8081                                | -                                                                                                           |
| controllerManager.metricPort                 | string | 8080                                | -                                                                                                           |
| controllerManager.watchNamespaces            | string | "" (watch all namespaces)           | Set the controller to watch specific namespaces instead of all. (e.g. `""`, `"NAMESPACE"`, or `"N1,N2,N3"`) |
| controllerManager.enableLeaderElection       | bool   | true                                | Enable leader election for the operator manager.                                                            |
| controllerManager.kubeApiQps                 | int    | 100                                 | Client-side Kubernetes API QPS limit.                                                                       |
| controllerManager.kubeApiBurst               | int    | 200                                 | Client-side Kubernetes API burst limit.                                                                     |
| controllerManager.enableWebhooks             | bool   | true                                | Enable validating and mutating webhooks.                                                                    |
| controllerManager.enableReconciler           | bool   | true                                | Enable reconciler controllers.                                                                              |
| controllerManager.enableMonitor              | bool   | false                               | Enable metrics Service and ServiceMonitor resources.                                                        |
| controllerManager.serviceMonitor.release     | string | kube-prometheus-stack               | Set the release name for the controller's metric service monitor.                                           |
| controllerManager.dsyncImage                 | string | us-west1-docker.pkg.dev/eloqdev/eloqcloud/eloq-dsync:0.1.0 | Image used by Dsync-based import jobs.                                                                      |
| controllerManager.redisShakeImage            | string | us-west1-docker.pkg.dev/eloqdev/eloqcloud/redis-shake:4.5.0 | Image used by RedisShake-based import jobs.                                                                 |
| controllerManager.cacheSyncPeriod            | string | 1h                                  | Cache sync period passed to the operator manager.                                                           |
| controllerManager.googleCloudProject         | string | ""                                  | Google Cloud project injected into the operator manager environment.                                        |
| controllerManager.gcpPscVpc                  | string | ""                                  | GCP VPC name injected for Private Service Connect workflows.                                                |
| keepCrds                                     | bool   | true                                | Keep or not keep CRDs when uninstalling the helm release.                                                   |
| cert-manager.enabled                         | bool   | false                               | Set `certManager.enabled=true` will install the cert-menager to `release.namespace`.                        |
