import json
import os
import sys
import textwrap

from kube_ops_view import cluster_discovery
from kube_ops_view.cluster_discovery import ClusterRegistryDiscoverer
from kube_ops_view.cluster_discovery import DEFAULT_CLUSTERS
from kube_ops_view.cluster_discovery import generate_cluster_id
from kube_ops_view.cluster_discovery import KubeconfigDiscoverer
from kube_ops_view.cluster_discovery import MockDiscoverer
from kube_ops_view.cluster_discovery import read_token
from kube_ops_view.cluster_discovery import StaticClusterDiscoverer
from kube_ops_view.kubernetes import query_kubernetes_cluster


def authorization_headers(fake_api, path="/api/v1/nodes"):
    return [h.get("authorization") for p, h in fake_api.requests if p == path]


def fill_api(fake_api):
    fake_api.set_items("/api/v1/nodes", [{"metadata": {"name": "n1"}, "status": {}}])
    fake_api.set_items("/api/v1/pods", [])


def test_generate_cluster_id():
    assert generate_cluster_id("https://Kube-1.example.org:443/") == (
        "kube-1-example-org:443"
    )
    assert generate_cluster_id(DEFAULT_CLUSTERS) == "localhost:8001"


def test_read_token_from_env(monkeypatch):
    monkeypatch.setenv("CLUSTER_REGISTRY_TOKEN", " secret \n")
    assert read_token() == "secret"


def test_read_token_from_file_is_reread(monkeypatch, tmp_path):
    monkeypatch.delenv("CLUSTER_REGISTRY_TOKEN", raising=False)
    monkeypatch.setenv("CREDENTIALS_DIR", str(tmp_path))
    token_file = tmp_path / "read-only-token-secret"
    token_file.write_text("first\n")
    assert read_token("read-only") == "first"
    token_file.write_text("second\n")
    assert read_token("read-only") == "second"


def test_mock_discoverer():
    assert len(list(MockDiscoverer().get_clusters())) == 3


def test_static_discoverer_with_urls(fake_api):
    fill_api(fake_api)
    clusters = StaticClusterDiscoverer([fake_api.url + "/"]).get_clusters()
    assert len(clusters) == 1
    assert query_kubernetes_cluster(clusters[0])["nodes"]["n1"]["name"] == "n1"


def test_static_discoverer_defaults_to_kubectl_proxy(monkeypatch):
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
    monkeypatch.delenv("KUBERNETES_SERVICE_PORT", raising=False)
    (cluster,) = StaticClusterDiscoverer([]).get_clusters()
    assert cluster.api_server_url == DEFAULT_CLUSTERS
    assert cluster.client.configuration.host == "http://localhost:8001"


def test_static_discoverer_in_cluster_refreshes_token(monkeypatch, tmp_path):
    from kubernetes.config import incluster_config

    token_file = tmp_path / "token"
    token_file.write_text("token-1")
    ca_file = tmp_path / "ca.crt"
    ca_file.write_text("dummy")
    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.0.0.1")
    monkeypatch.setenv("KUBERNETES_SERVICE_PORT", "443")
    # the default file names are bound at import time, so patch the loading function
    monkeypatch.setattr(
        cluster_discovery.k8s_config,
        "load_incluster_config",
        lambda client_configuration: incluster_config.InClusterConfigLoader(
            token_filename=str(token_file), cert_filename=str(ca_file)
        ).load_and_set(client_configuration),
    )

    (cluster,) = StaticClusterDiscoverer([]).get_clusters()

    assert cluster.api_server_url == "https://10.0.0.1:443"
    assert cluster.id == "10-0-0-1:443"
    configuration = cluster.client.configuration
    assert configuration.get_api_key_with_prefix("BearerToken") == "bearer token-1"
    # simulate the rotation of the (bound) service account token
    # (the client only re-reads the token file once per minute)
    token_file.write_text("token-2")
    loader = next(
        cell.cell_contents
        for cell in configuration.refresh_api_key_hook.__closure__
        if hasattr(cell.cell_contents, "token_expires_at")
    )
    loader.token_expires_at = loader.token_expires_at.replace(year=2000)
    assert configuration.get_api_key_with_prefix("BearerToken") == "bearer token-2"


def test_cluster_registry_discoverer(fake_api, monkeypatch, tmp_path):
    fill_api(fake_api)
    monkeypatch.delenv("CLUSTER_REGISTRY_TOKEN", raising=False)
    monkeypatch.setenv("CREDENTIALS_DIR", str(tmp_path))
    (tmp_path / "read-only-token-secret").write_text("t0ken\n")
    fake_api.responses["/kubernetes-clusters"] = (
        200,
        {
            "items": [
                {"id": "a", "alias": "alias-a", "api_server_url": fake_api.url},
                {
                    "id": "b",
                    "alias": "alias-b",
                    "api_server_url": fake_api.url,
                    "lifecycle_status": "decommissioned",
                },
            ]
        },
    )

    discoverer = ClusterRegistryDiscoverer(fake_api.url)
    clusters = discoverer.get_clusters()

    assert [(c.id, c.name) for c in clusters] == [("a", "alias-a")]
    assert authorization_headers(fake_api, "/kubernetes-clusters") == ["Bearer t0ken"]
    query_kubernetes_cluster(clusters[0])
    assert authorization_headers(fake_api) == ["Bearer t0ken"]
    # token rotation is picked up without recreating the clients
    (tmp_path / "read-only-token-secret").write_text("rotated\n")
    query_kubernetes_cluster(clusters[0])
    assert authorization_headers(fake_api)[-1] == "Bearer rotated"


def test_cluster_registry_discoverer_failure_returns_no_clusters(fake_api, monkeypatch):
    monkeypatch.setenv("CLUSTER_REGISTRY_TOKEN", "t")
    fake_api.responses["/kubernetes-clusters"] = (500, {})
    discoverer = ClusterRegistryDiscoverer(fake_api.url)
    assert discoverer.get_clusters() == []


def write_kubeconfig(path, server):
    exec_credential = json.dumps(
        {
            "apiVersion": "client.authentication.k8s.io/v1",
            "kind": "ExecCredential",
            "status": {"token": "exec-token"},
        }
    )
    exec_script = "print(" + repr(exec_credential) + ")"
    path.write_text(textwrap.dedent(f"""\
            apiVersion: v1
            kind: Config
            clusters:
            - name: c1
              cluster: {{server: "{server}"}}
            - name: c2
              cluster: {{server: "{server}"}}
            users:
            - name: static
              user: {{token: static-token}}
            - name: exec
              user:
                exec:
                  apiVersion: client.authentication.k8s.io/v1
                  command: {json.dumps(sys.executable)}
                  args: ["-S", "-c", {json.dumps(exec_script)}]
                  interactiveMode: Never
            contexts:
            - name: static-ctx
              context: {{cluster: c1, user: static}}
            - name: exec-ctx
              context: {{cluster: c2, user: exec}}
            current-context: static-ctx
            """))


def test_kubeconfig_discoverer_multiple_contexts_with_exec_auth(fake_api, tmp_path):
    fill_api(fake_api)
    kubeconfig = tmp_path / "kubeconfig"
    write_kubeconfig(kubeconfig, fake_api.url)

    discoverer = KubeconfigDiscoverer(kubeconfig, set())
    clusters = discoverer.get_clusters()

    assert [c.id for c in clusters] == ["static-ctx", "exec-ctx"]
    assert all(c.api_server_url == fake_api.url for c in clusters)
    for cluster in clusters:
        query_kubernetes_cluster(cluster)
    assert sorted(authorization_headers(fake_api)) == [
        "Bearer exec-token",
        "Bearer static-token",
    ]
    # clients are cached
    assert discoverer.get_clusters()[0] is clusters[0]


def test_kubeconfig_discoverer_context_filter(fake_api, tmp_path):
    kubeconfig = tmp_path / "kubeconfig"
    write_kubeconfig(kubeconfig, fake_api.url)
    clusters = KubeconfigDiscoverer(kubeconfig, {"exec-ctx"}).get_clusters()
    assert [c.id for c in clusters] == ["exec-ctx"]


def test_kubeconfig_discoverer_failing_context_does_not_block_others(
    fake_api, tmp_path, monkeypatch
):
    kubeconfig = tmp_path / "kubeconfig"
    write_kubeconfig(kubeconfig, fake_api.url)
    original = cluster_discovery.k8s_config.new_client_from_config
    calls = []

    def new_client(config_file, context):
        calls.append(context)
        if context == "static-ctx":
            raise RuntimeError("boom")
        return original(config_file=config_file, context=context)

    monkeypatch.setattr(
        cluster_discovery.k8s_config, "new_client_from_config", new_client
    )
    discoverer = KubeconfigDiscoverer(kubeconfig, set())

    assert [c.id for c in discoverer.get_clusters()] == ["exec-ctx"]
    # failed context is not retried immediately
    assert [c.id for c in discoverer.get_clusters()] == ["exec-ctx"]
    assert calls == ["static-ctx", "exec-ctx"]


def test_kubeconfig_discoverer_reloads_changed_file(fake_api, tmp_path):
    kubeconfig = tmp_path / "kubeconfig"
    write_kubeconfig(kubeconfig, fake_api.url)
    discoverer = KubeconfigDiscoverer(kubeconfig, {"static-ctx"})
    first = discoverer.get_clusters()[0]
    stat = kubeconfig.stat()
    os.utime(kubeconfig, (stat.st_atime, stat.st_mtime + 10))
    assert discoverer.get_clusters()[0] is not first
