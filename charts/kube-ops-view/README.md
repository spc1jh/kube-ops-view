# kube-ops-view Helm chart

Successor of the deprecated `helm/charts` `stable/kube-ops-view` chart (1.2.4), for the
maintained fork. Most `values.yaml` keys are unchanged (`replicaCount`, `image`, `service`,
`resources`, `ingress`, `rbac`, `env`, `podLabels`, `affinity`, `nodeSelector`, `tolerations`,
`securityContext`, `podSecurityContext`).

## Install

Build the image first (`make docker`) and push it to a registry the cluster can pull from.

```bash
helm upgrade --install kube-ops-view charts/kube-ops-view -n ops --create-namespace \
  --set image.repository=<registry>/kube-ops-view --set image.tag=<tag>

kubectl -n ops port-forward svc/kube-ops-view 8080:80
```

Without further options the cluster the pod runs in is shown (read-only ServiceAccount).

## Multiple clusters

Mount a kubeconfig from an existing Secret (all contexts, or the ones listed in `kubeconfig.contexts`):

```bash
kubectl -n ops create secret generic kov-kubeconfig --from-file=config=./kubeconfig
helm upgrade --install kube-ops-view charts/kube-ops-view -n ops \
  --set kubeconfig.existingSecret=kov-kubeconfig --set 'kubeconfig.contexts={tokyo,us}'
```

The pod has no `aws` CLI, so `exec` based credentials (`aws eks get-token`) do not work inside
the pod. Use kubeconfig entries with a read-only ServiceAccount token (apply `deploy/rbac.yaml` in each
target cluster and put its token into the kubeconfig), or add the credential helper to the image.
If both `kubeconfig` and `clusters` are set, the kubeconfig wins.

## Redis

`redis.enabled=true` deploys a small single-replica Redis (pub/sub and job lock) which is
required for `replicaCount > 1`. To use an existing Redis, leave it disabled and set
`env.REDIS_URL`.

## Differences to the old chart

- `apiVersion: v2`; Ingress uses `networking.k8s.io/v1` (`ingress.className`, `ingress.pathType`),
  RBAC uses `rbac.authorization.k8s.io/v1` (the old beta APIs were removed in Kubernetes 1.22).
- `rbac.create` now defaults to `true`.
- Pods run with a restricted `securityContext` by default (non-root, read-only root filesystem, seccomp).
- Redis is no longer a subchart: `redis.master.*`, `redis.usePassword` etc. are gone.
- Selector labels changed, so an existing release of the old chart cannot be upgraded in place;
  uninstall it first.
