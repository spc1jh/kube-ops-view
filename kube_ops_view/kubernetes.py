import datetime
import json
import logging
import time

from kubernetes import client as k8s_client

from .utils import get_short_error_message

logger = logging.getLogger(__name__)

# (connect, read) timeout in seconds
REQUEST_TIMEOUT = (5, 60)

# fields of container statuses which would override or bloat the container data
# (e.g. "resources" in the status contains the *actual* resources after in-place resize)
IGNORED_STATUS_FIELDS = ("resources", "allocatedResources", "volumeMounts", "user")


def get_items(list_function, *args, **kwargs):
    """Call the Kubernetes API list function and return the raw "items" (avoids slow model deserialization)."""
    response = list_function(
        *args, _preload_content=False, _request_timeout=REQUEST_TIMEOUT, **kwargs
    )
    try:
        return json.loads(response.data).get("items") or []
    finally:
        response.release_conn()


def map_node_status(status: dict):
    return {
        "addresses": status.get("addresses"),
        "capacity": status.get("capacity"),
        "allocatable": status.get("allocatable"),
    }


def map_node(node: dict):
    return {
        "name": node["metadata"]["name"],
        "labels": node["metadata"].get("labels", {}),
        "status": map_node_status(node.get("status", {})),
        "pods": {},
    }


def map_pod(pod: dict):
    status = pod.get("status", {})
    return {
        "name": pod["metadata"]["name"],
        "namespace": pod["metadata"]["namespace"],
        "labels": pod["metadata"].get("labels", {}),
        "phase": status.get("phase"),
        "startTime": status.get("startTime", ""),
        "containers": [],
    }


def map_container(cont: dict, pod: dict, status_key: str = "containerStatuses"):
    obj = {
        "name": cont["name"],
        "image": cont["image"],
        "resources": cont.get("resources", {}),
    }
    status = [
        s
        for s in pod.get("status", {}).get(status_key, [])
        if s["name"] == cont["name"]
    ]
    if status:
        obj.update(
            **{k: v for k, v in status[0].items() if k not in IGNORED_STATUS_FIELDS}
        )
    return obj


def map_containers(pod: dict):
    """Map all containers of the pod which should be displayed.

    Besides the regular containers this includes:
    * native sidecar containers (init containers with restartPolicy "Always", marked with "sidecar": True)
    * init containers which have not completed successfully yet (marked with "init": True)
    * running ephemeral (debug) containers (marked with "ephemeral": True)
    """
    spec = pod["spec"]
    containers = [map_container(c, pod) for c in spec.get("containers", [])]
    for cont in spec.get("initContainers", []):
        obj = map_container(cont, pod, "initContainerStatuses")
        if cont.get("restartPolicy") == "Always":
            obj["init"] = True
            obj["sidecar"] = True
        else:
            terminated = obj.get("state", {}).get("terminated")
            if terminated and terminated.get("exitCode") == 0:
                # completed init containers are not interesting anymore
                continue
            obj["init"] = True
        containers.append(obj)
    for cont in spec.get("ephemeralContainers", []):
        obj = map_container(cont, pod, "ephemeralContainerStatuses")
        if "running" not in obj.get("state", {}):
            # finished debug containers would make the pod look "not ready"
            continue
        obj["ephemeral"] = True
        containers.append(obj)
    return containers


def parse_time(s: str):
    return (
        datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")
        .replace(tzinfo=datetime.timezone.utc)
        .timestamp()
    )


def query_kubernetes_cluster(cluster):
    cluster_id = cluster.id
    api_server_url = cluster.api_server_url
    core_api = k8s_client.CoreV1Api(cluster.client)
    nodes = {}
    pods_by_namespace_name = {}
    unassigned_pods = {}
    for node in get_items(core_api.list_node):
        obj = map_node(node)
        nodes[obj["name"]] = obj
    now = time.time()
    for pod in get_items(core_api.list_pod_for_all_namespaces):
        obj = map_pod(pod)
        metadata = pod["metadata"]
        if "deletionTimestamp" in metadata:
            obj["deleted"] = parse_time(metadata["deletionTimestamp"])
        obj["containers"] = map_containers(pod)
        if obj["phase"] in ("Succeeded", "Failed"):
            last_termination_time = 0
            for container in obj["containers"]:
                termination_time = (
                    container.get("state", {}).get("terminated", {}).get("finishedAt")
                )
                if termination_time:
                    termination_time = parse_time(termination_time)
                    if termination_time > last_termination_time:
                        last_termination_time = termination_time
            if (last_termination_time and last_termination_time < now - 3600) or (
                pod.get("status", {}).get("reason") == "Evicted"
            ):
                # the job/pod finished more than an hour ago or if it is evicted by cgroup limits
                # => filter out
                continue
        pods_by_namespace_name[(obj["namespace"], obj["name"])] = obj
        pod_key = f"{obj['namespace']}/{obj['name']}"
        node_name = pod["spec"].get("nodeName")
        if node_name in nodes:
            nodes[node_name]["pods"][pod_key] = obj
        else:
            unassigned_pods[pod_key] = obj

    custom_api = k8s_client.CustomObjectsApi(cluster.client)
    try:
        for node_metrics in get_items(
            custom_api.list_cluster_custom_object, "metrics.k8s.io", "v1beta1", "nodes"
        ):
            node = nodes.get(node_metrics["metadata"]["name"])
            if node:
                node["usage"] = node_metrics.get("usage", {})
    except Exception as e:
        logger.warning(
            "Failed to query node metrics {}: {}".format(
                cluster.id, get_short_error_message(e)
            )
        )
    try:
        for pod_metrics in get_items(
            custom_api.list_cluster_custom_object, "metrics.k8s.io", "v1beta1", "pods"
        ):
            key = (
                pod_metrics["metadata"]["namespace"],
                pod_metrics["metadata"]["name"],
            )
            pod = pods_by_namespace_name.get(key)
            if pod:
                for container in pod["containers"]:
                    for container_metrics in pod_metrics.get("containers", []):
                        if container["name"] == container_metrics["name"]:
                            container["resources"]["usage"] = container_metrics["usage"]
    except Exception as e:
        logger.warning(
            "Failed to query pod metrics for cluster {}: {}".format(
                cluster.id, get_short_error_message(e)
            )
        )
    return {
        "id": cluster_id,
        "api_server_url": api_server_url,
        "nodes": nodes,
        "unassigned_pods": unassigned_pods,
    }
