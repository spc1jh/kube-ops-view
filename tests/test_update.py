import gevent
import json_delta
import pytest

from kube_ops_view.cluster_discovery import MockDiscoverer
from kube_ops_view.mock import query_mock_cluster
from kube_ops_view.stores import MemoryStore
from kube_ops_view.update import handle_query_failure
from kube_ops_view.update import update_clusters


def test_json_delta_roundtrip():
    old = {"nodes": {"n1": {"pods": {"a": {"phase": "Running"}}}}, "list": [1, 2, 3]}
    new = {
        "nodes": {
            "n1": {"pods": {"a": {"phase": "Failed"}, "b": {"phase": "Running"}}}
        },
        "list": [1, 2, 4],
    }
    delta = json_delta.diff(old, new, array_align=False, compare_lengths=False)
    assert json_delta.patch(old, delta) == new


def test_handle_query_failure_backoff_grows():
    cluster = next(iter(MockDiscoverer().get_clusters()))
    backoff = handle_query_failure(RuntimeError("x"), cluster, None)
    assert backoff["tries"] == 1
    backoff = handle_query_failure(RuntimeError("x"), cluster, backoff)
    assert backoff["tries"] == 2
    assert backoff["next_try"] > 0


def test_update_clusters_stores_cluster_data(monkeypatch):
    store = MemoryStore()

    class StopLoop(Exception):
        pass

    def stop_after_first_round(seconds):
        raise StopLoop()

    monkeypatch.setattr(gevent, "sleep", stop_after_first_round)
    with pytest.raises(StopLoop):
        update_clusters(MockDiscoverer(), query_mock_cluster, store)
    assert store.get_cluster_ids() == [f"mock-cluster-{i}" for i in range(3)]
    assert store.get_cluster_data("mock-cluster-0")["id"] == "mock-cluster-0"
