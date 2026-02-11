## eloq operator Helm Chart

The current chart is for installing the eloq-operator (including CRD for `EloqDBCluster`).

### Install the eloq-operator

[Helm](https://helm.sh) must be installed to use the charts. Please refer to
Helm's [documentation](https://helm.sh/docs) to get started.

Once Helm has been set up correctly, authenticate to GitHub Container Registry and install as follows:

```shell
# Authenticate (use GitHub Personal Access Token with read:packages scope)
export GITHUB_TOKEN=your_github_token
echo $GITHUB_TOKEN | helm registry login ghcr.io -u your-username --password-stdin

# Install eloq-operator from OCI registry
helm install eloq-operator oci://ghcr.io/eloqdata/charts/eloq-operator --version 1.0.0 --namespace eloq-operator-system
```

> NOTE: If the installation specifies namespace please create it first.

#### Install with Node Selector

To schedule the eloq-operator controller manager on specific nodes, you can specify a nodeSelector:

```shell
helm install eloq-operator oci://ghcr.io/eloqdata/charts/eloq-operator --version 1.0.0 --namespace eloq-operator-system \
  --set controllerManager.nodeSelector."eloqdata\.com/node"=control-plane
```

### Upgrade the eloq-operator

To upgrade an existing eloq-operator release:

```shell
helm upgrade eloq-operator oci://ghcr.io/eloqdata/charts/eloq-operator --version 1.0.1 --namespace eloq-operator-system
```

### Check the installed eloq operator

```shell
# for example: helm list --namespace eloq-operator-system / helm list --all --all-namespaces
helm list --namespace [NAMESPACE_NAME]
```

### Uninstall Helm Release and CRDs

The default value of `keepCrds` in `values.yaml` is set to `true`. This means that even after uninstalling the release,
Custom Resource Definitions (CRDs) associated with the release are retained. This behavior is particularly useful for
preserving CRDs that you might want to keep for future use or to maintain data integrity.

To uninstall a Helm release, use the following command:

```shell
helm uninstall [RELEASE_NAME] --namespace [NAMESPACE_NAME]
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
| controllerManager.serviceAccount.name        | string | eloq-operator-controller-manager-sa | The service account name of the eloq operator controller manager pods.                                      |
| controllerManager.serviceAccount.annotations | object | {}                                  | Annotations for the `controllerManager.serviceAccount`.                                                     |
| controllerManager.image.repository           | string | eloqdata/eloq-operator           | The image name of the eloq operator.                                                                        |
| controllerManager.image.tag                  | string | v1.0.4                              | The version tag for eloq operator docker image.                                                             |
| controllerManager.imagePullPolicy            | string | IfNotPresent                        | -                                                                                                           |
| controllerManager.imagePullSecrets           | object | {}                                  | -                                                                                                           |
| controllerManager.resources                  | object | Same format as k8s resource         | Resource requests and limits for eloq operator controller manager pods.                                     |
| controllerManager.healthPort                 | string | 18080                               | -                                                                                                           |
| controllerManager.metricPort                 | string | 18081                               | -                                                                                                           |
| controllerManager.watchNamespaces            | string | "" (watch all namespaces)           | Set the controller to watch specific namespaces instead of all. (e.g. `""`, `"NAMESPACE"`, or `"N1,N2,N3"`) |
| controllerManager.serviceMonitor.release     | string | kube-prometheus-stack               | Set the release name for the controller's metric service monitor.                                           |
| controllerManager.env                        | list   | []                                  | The environment variable of the eloq operator controller manager pods.                                      |
| keepCrds                                     | bool   | true                                | Keep or not keep CRDs when uninstalling the helm release.                                                   |
| cert-manager.enabled                         | bool   | false                               | Set `certManager.enabled=true` will install the cert-menager to `release.namespace`.                        |
