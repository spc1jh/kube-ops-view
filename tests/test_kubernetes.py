import time

from kubernetes.client.exceptions import ApiException

from kube_ops_view.cluster_discovery import Cluster
from kube_ops_view.cluster_discovery import create_url_client
from kube_ops_view.kubernetes import map_container
from kube_ops_view.kubernetes import map_containers
from kube_ops_view.kubernetes import map_node
from kube_ops_view.kubernetes import map_pod
from kube_ops_view.kubernetes import parse_time
from kube_ops_view.kubernetes import query_kubernetes_cluster
from kube_ops_view.utils import get_short_error_message

RUNNING = {"running": {"startedAt": "2026-01-01T00:00:00Z"}}


def make_pod(name="p", namespace="default", node="n1", phase="Running", **spec):
    pod = {
        "metadata": {"name": name, "namespace": namespace},
        "spec": {
            "nodeName": node,
            "containers": [
                {
                    "name": "app",
                    "image": "app:1",
                    "resources": {"requests": {"cpu": "100m"}},
                }
            ],
        },
        "status": {
            "phase": phase,
            "startTime": "2026-01-01T00:00:00Z",
            "containerStatuses": [
                {"name": "app", "image": "app:1", "ready": True, "state": RUNNING}
            ],
        },
    }
    pod["spec"].update(spec)
    return pod


def test_map_node_without_labels_and_status():
    node = map_node({"metadata": {"name": "n1"}})
    assert node == {
        "name": "n1",
        "labels": {},
        "status": {"addresses": None, "capacity": None, "allocatable": None},
        "pods": {},
    }


def test_map_pod_without_status():
    pod = map_pod({"metadata": {"name": "p", "namespace": "ns"}})
    assert pod["phase"] is None
    assert pod["startTime"] == ""
    assert pod["labels"] == {}


def test_map_container_without_resources_and_status():
    cont = map_container({"name": "c", "image": "i"}, {})
    assert cont == {"name": "c", "image": "i", "resources": {}}


def test_map_container_keeps_spec_resources_over_status_resources():
    pod = make_pod()
    # Kubernetes 1.31+ reports the actual resources in the container status
    pod["status"]["containerStatuses"][0]["resources"] = {"limits": {"cpu": "1"}}
    pod["status"]["containerStatuses"][0]["allocatedResources"] = {"cpu": "100m"}
    cont = map_container(pod["spec"]["containers"][0], pod)
    assert cont["resources"] == {"requests": {"cpu": "100m"}}
    assert "allocatedResources" not in cont
    assert cont["ready"] is True
    assert cont["state"] == RUNNING


def test_map_containers_native_sidecar_and_init():
    pod = make_pod(
        initContainers=[
            {"name": "migrate", "image": "m:1"},
            {"name": "setup", "image": "s:1"},
            {"name": "proxy", "image": "px:1", "restartPolicy": "Always"},
        ]
    )
    pod["status"]["initContainerStatuses"] = [
        {"name": "migrate", "state": {"terminated": {"exitCode": 0}}},
        {"name": "setup", "state": {"running": {}}},
        {"name": "proxy", "ready": True, "state": RUNNING, "started": True},
    ]
    containers = {c["name"]: c for c in map_containers(pod)}
    # completed init container is not shown
    assert set(containers) == {"app", "setup", "proxy"}
    assert "init" not in containers["app"]
    assert containers["setup"]["init"] is True
    assert "sidecar" not in containers["setup"]
    assert containers["proxy"]["init"] is True
    assert containers["proxy"]["sidecar"] is True
    assert containers["proxy"]["ready"] is True


def test_map_containers_failed_init_container_is_shown():
    pod = make_pod(initContainers=[{"name": "migrate", "image": "m:1"}])
    pod["status"]["initContainerStatuses"] = [
        {"name": "migrate", "state": {"terminated": {"exitCode": 1}}}
    ]
    names = [c["name"] for c in map_containers(pod)]
    assert names == ["app", "migrate"]


def test_map_containers_ephemeral():
    pod = make_pod(
        ephemeralContainers=[
            {"name": "debug-running", "image": "busybox"},
            {"name": "debug-done", "image": "busybox"},
        ]
    )
    pod["status"]["ephemeralContainerStatuses"] = [
        {"name": "debug-running", "state": RUNNING},
        {"name": "debug-done", "state": {"terminated": {"exitCode": 0}}},
    ]
    containers = {c["name"]: c for c in map_containers(pod)}
    assert set(containers) == {"app", "debug-running"}
    assert containers["debug-running"]["ephemeral"] is True


def test_parse_time():
    assert parse_time("1970-01-01T00:01:00Z") == 60


def test_get_short_error_message_api_exception():
    assert (
        get_short_error_message(ApiException(status=403, reason="Forbidden"))
        == "403 Forbidden"
    )


def finished_at(seconds_ago):
    ts = time.time() - seconds_ago
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def test_query_kubernetes_cluster(fake_api):
    fake_api.set_items(
        "/api/v1/nodes",
        [
            {
                "metadata": {"name": "n1", "labels": {"role": "worker"}},
                "status": {"capacity": {"cpu": "4"}, "allocatable": {"cpu": "3"}},
            },
            # node without labels
            {"metadata": {"name": "n2"}, "status": {}},
        ],
    )
    pending = make_pod("pending", node=None, phase="Pending")
    del pending["status"]["containerStatuses"]
    old_job = make_pod("old-job", phase="Succeeded")
    old_job["status"]["containerStatuses"][0]["state"] = {
        "terminated": {"finishedAt": finished_at(7200)}
    }
    new_job = make_pod("new-job", phase="Succeeded")
    new_job["status"]["containerStatuses"][0]["state"] = {
        "terminated": {"finishedAt": finished_at(60)}
    }
    evicted = make_pod("evicted", phase="Failed")
    evicted["status"]["reason"] = "Evicted"
    terminating = make_pod("terminating")
    terminating["metadata"]["deletionTimestamp"] = "1970-01-01T00:01:00Z"
    sidecar_pod = make_pod(
        "sidecar",
        initContainers=[{"name": "s", "image": "s", "restartPolicy": "Always"}],
    )
    fake_api.set_items(
        "/api/v1/pods",
        [
            make_pod("web"),
            pending,
            old_job,
            new_job,
            evicted,
            terminating,
            sidecar_pod,
            # pod scheduled on a node which does not exist (anymore)
            make_pod("orphan", node="gone"),
        ],
    )
    fake_api.set_items(
        "/apis/metrics.k8s.io/v1beta1/nodes",
        [{"metadata": {"name": "n1"}, "usage": {"cpu": "1", "memory": "1Gi"}}],
    )
    fake_api.set_items(
        "/apis/metrics.k8s.io/v1beta1/pods",
        [
            {
                "metadata": {"name": "web", "namespace": "default"},
                "containers": [{"name": "app", "usage": {"cpu": "10m"}}],
            },
            {"metadata": {"name": "unknown", "namespace": "default"}, "containers": []},
        ],
    )
    cluster = Cluster("c1", "c1", fake_api.url, create_url_client(fake_api.url))

    data = query_kubernetes_cluster(cluster)

    assert data["id"] == "c1"
    assert data["api_server_url"] == fake_api.url
    assert set(data["nodes"]) == {"n1", "n2"}
    assert data["nodes"]["n1"]["usage"] == {"cpu": "1", "memory": "1Gi"}
    assert data["nodes"]["n2"]["labels"] == {}
    assert set(data["nodes"]["n1"]["pods"]) == {
        "default/web",
        "default/new-job",
        "default/terminating",
        "default/sidecar",
    }
    assert set(data["unassigned_pods"]) == {"default/pending", "default/orphan"}
    web = data["nodes"]["n1"]["pods"]["default/web"]
    assert web["containers"][0]["resources"] == {
        "requests": {"cpu": "100m"},
        "usage": {"cpu": "10m"},
    }
    assert data["nodes"]["n1"]["pods"]["default/terminating"]["deleted"] == 60
    sidecar = data["nodes"]["n1"]["pods"]["default/sidecar"]
    assert [c["name"] for c in sidecar["containers"]] == ["app", "s"]


def test_query_kubernetes_cluster_metrics_failure_is_not_fatal(fake_api, caplog):
    fake_api.set_items("/api/v1/nodes", [{"metadata": {"name": "n1"}, "status": {}}])
    fake_api.set_items("/api/v1/pods", [make_pod("web")])
    fake_api.responses["/apis/metrics.k8s.io/v1beta1/nodes"] = (403, {})
    # pod metrics are not found (404)
    cluster = Cluster("c1", "c1", fake_api.url, create_url_client(fake_api.url))

    data = query_kubernetes_cluster(cluster)

    assert "usage" not in data["nodes"]["n1"]
    assert "Failed to query node metrics c1: 403" in caplog.text
    assert "Failed to query pod metrics for cluster c1: 404" in caplog.text
