import time

import fakeredis
import pytest

from kube_ops_view import stores
from kube_ops_view.stores import check_token
from kube_ops_view.stores import generate_token
from kube_ops_view.stores import generate_token_data
from kube_ops_view.stores import MemoryStore
from kube_ops_view.stores import RedisStore


@pytest.fixture
def redis_store(monkeypatch):
    server = fakeredis.FakeServer()
    monkeypatch.setattr(
        stores.redis.Redis,
        "from_url",
        lambda url: fakeredis.FakeRedis(server=server),
    )
    return RedisStore("redis://fake")


def test_generate_token():
    token = generate_token(10)
    assert len(token) == 10 and token.isalnum()
    assert generate_token(10) != token


def test_check_token_binds_to_remote_addr():
    data = generate_token_data()
    data = check_token(data["token"], "1.2.3.4", data)
    assert data["remote_addr"] == "1.2.3.4"
    check_token(data["token"], "1.2.3.4", data)
    with pytest.raises(ValueError):
        check_token(data["token"], "5.6.7.8", data)


def test_check_token_expired_or_unknown():
    with pytest.raises(ValueError):
        check_token("x", "1.2.3.4", None)
    data = generate_token_data()
    data["expires"] = time.time() - 1
    with pytest.raises(ValueError):
        check_token(data["token"], "1.2.3.4", data)


@pytest.mark.parametrize("store_name", ["memory", "redis"])
def test_cluster_data_and_screen_tokens(store_name, request):
    store = (
        MemoryStore()
        if store_name == "memory"
        else request.getfixturevalue("redis_store")
    )
    assert store.get_cluster_ids() == []
    store.set_cluster_ids({"b", "a"})
    assert store.get_cluster_ids() == ["a", "b"]
    assert store.get_cluster_status("a") == {}
    store.set_cluster_status("a", {"last_query_time": 1})
    assert store.get_cluster_status("a") == {"last_query_time": 1}
    store.set_cluster_data("a", {"id": "a"})
    assert store.get_cluster_data("a") == {"id": "a"}

    token = store.create_screen_token()
    store.redeem_screen_token(token, "1.2.3.4")
    store.redeem_screen_token(token, "1.2.3.4")
    with pytest.raises(ValueError):
        store.redeem_screen_token(token, "5.6.7.8")
    with pytest.raises(ValueError):
        store.redeem_screen_token("unknown", "1.2.3.4")


def test_redis_lock_is_exclusive(redis_store):
    lock = redis_store.acquire_lock()
    assert lock
    assert redis_store.acquire_lock() is None
    redis_store.release_lock(lock)
    assert redis_store.acquire_lock()


def test_redis_lock_release_only_by_owner(redis_store):
    lock = redis_store.acquire_lock()
    redis_store.release_lock("not-the-owner")
    assert redis_store.acquire_lock() is None
    redis_store.release_lock(lock)
    assert redis_store.acquire_lock()


def test_redis_lock_expires(redis_store, monkeypatch):
    monkeypatch.setattr(stores, "LOCK_TIMEOUT_MILLIS", 50)
    lock = redis_store.acquire_lock()
    time.sleep(0.1)
    other = redis_store.acquire_lock()
    assert other and other != lock
    # releasing the expired lock must not release the lock of the new owner
    redis_store.release_lock(lock)
    assert redis_store.acquire_lock() is None
