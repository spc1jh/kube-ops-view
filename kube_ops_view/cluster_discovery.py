import logging
import os
import re
import time
from pathlib import Path
from typing import List
from urllib.parse import urljoin

import requests
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from kubernetes.config import ConfigException
from requests.auth import AuthBase

# default URL points to kubectl proxy
DEFAULT_CLUSTERS = "http://localhost:8001/"
CLUSTER_ID_INVALID_CHARS = re.compile("[^a-z0-9:-]")
# how long to wait before retrying to load a kubeconfig context which failed
CONTEXT_RETRY_SECONDS = 60

logger = logging.getLogger(__name__)


def generate_cluster_id(url: str):
    """Generate some "cluster ID" from given API server URL."""
    for prefix in ("https://", "http://"):
        if url.startswith(prefix):
            url = url[len(prefix) :]
    return CLUSTER_ID_INVALID_CHARS.sub("-", url.lower()).strip("-")


def read_token(token_name: str = "read-only"):
    """Read a bearer token from the environment or from a file (potentially mounted from a Kubernetes secret).

    The token is read from the environment variable CLUSTER_REGISTRY_TOKEN or otherwise
    from the file "<token_name>-token-secret" in CREDENTIALS_DIR.
    The token is read on every call to pick up rotated secrets.
    """
    token = os.getenv("CLUSTER_REGISTRY_TOKEN")
    if token:
        return token.strip()
    path = os.path.join(os.getenv("CREDENTIALS_DIR", ""), f"{token_name}-token-secret")
    with open(path) as fd:
        return fd.read().strip()


class StaticAuthorizationHeaderAuth(AuthBase):
    """Static authentication with given "Authorization" header."""

    def __init__(self, authorization):
        self.authorization = authorization

    def __call__(self, request):
        request.headers["Authorization"] = self.authorization
        return request


class FileTokenAuth(AuthBase):
    """Dynamic authentication using the bearer token from environment/file (see read_token)."""

    def __init__(self, token_name):
        self.token_name = token_name

    def __call__(self, request):
        token = read_token(self.token_name)
        request.headers["Authorization"] = f"Bearer {token}"
        return request


class Cluster:
    def __init__(
        self,
        id: str,
        name: str,
        api_server_url: str,
        client: k8s_client.ApiClient | None,
    ):
        self.id = id
        self.name = name
        self.api_server_url = api_server_url
        self.client = client


def create_url_client(api_server_url: str):
    """Create an unauthenticated API client (e.g. for "kubectl proxy")."""
    configuration = k8s_client.Configuration()
    configuration.host = api_server_url.rstrip("/")
    return k8s_client.ApiClient(configuration)


def create_token_client(api_server_url: str, token_name: str):
    """Create an API client sending the bearer token from environment/file (re-read on every request)."""
    configuration = k8s_client.Configuration()
    configuration.host = api_server_url.rstrip("/")
    configuration.api_key_prefix["BearerToken"] = "Bearer"

    def refresh_api_key(configuration):
        configuration.api_key["BearerToken"] = read_token(token_name)

    refresh_api_key(configuration)
    configuration.refresh_api_key_hook = refresh_api_key
    return k8s_client.ApiClient(configuration)


class StaticClusterDiscoverer:
    def __init__(self, api_server_urls: list):
        self._clusters = []

        if not api_server_urls:
            configuration = k8s_client.Configuration()
            try:
                # the service account token is refreshed automatically
                k8s_config.load_incluster_config(client_configuration=configuration)
            except ConfigException:
                # we are not running inside a cluster
                # => assume default kubectl proxy URL
                cluster = Cluster(
                    generate_cluster_id(DEFAULT_CLUSTERS),
                    "cluster",
                    DEFAULT_CLUSTERS,
                    create_url_client(DEFAULT_CLUSTERS),
                )
            else:
                cluster = Cluster(
                    generate_cluster_id(configuration.host),
                    "cluster",
                    configuration.host,
                    k8s_client.ApiClient(configuration),
                )
            self._clusters.append(cluster)
        else:
            for api_server_url in api_server_urls:
                generated_id = generate_cluster_id(api_server_url)
                self._clusters.append(
                    Cluster(
                        generated_id,
                        generated_id,
                        api_server_url,
                        create_url_client(api_server_url),
                    )
                )

    def get_clusters(self):
        return self._clusters


class ClusterRegistryDiscoverer:
    def __init__(self, cluster_registry_url: str, cache_lifetime=60):
        self._url = cluster_registry_url
        self._cache_lifetime = cache_lifetime
        self._last_cache_refresh = 0
        self._clusters: List[Cluster] = []
        self._session = requests.Session()
        self._session.auth = FileTokenAuth("read-only")

    def refresh(self):
        try:
            response = self._session.get(
                urljoin(self._url, "/kubernetes-clusters"), timeout=10
            )
            response.raise_for_status()
            clusters = []
            for row in response.json()["items"]:
                # only consider "ready" clusters
                if row.get("lifecycle_status", "ready") == "ready":
                    client = create_token_client(row["api_server_url"], "read-only")
                    clusters.append(
                        Cluster(row["id"], row["alias"], row["api_server_url"], client)
                    )
            self._clusters = clusters
            self._last_cache_refresh = time.time()
        except Exception as e:
            logger.exception(
                f"Failed to refresh from cluster registry {self._url}: {e}"
            )

    def get_clusters(self):
        now = time.time()
        if now - self._last_cache_refresh > self._cache_lifetime:
            self.refresh()
        return self._clusters


class KubeconfigDiscoverer:
    def __init__(self, kubeconfig_path: Path, contexts: set):
        self._path = kubeconfig_path
        self._contexts = contexts
        # clients are cached as e.g. "exec" credential plugins are expensive and refresh their tokens themselves
        self._mtime = None
        self._clusters: dict[str, Cluster] = {}
        self._failed: dict[str, float] = {}

    def get_clusters(self):
        # Kubernetes Python client expects "vintage" string path
        config_file = str(self._path)
        mtime = self._path.stat().st_mtime
        if mtime != self._mtime:
            # kubeconfig changed => reload everything
            self._mtime = mtime
            self._clusters = {}
            self._failed = {}
        contexts, _ = k8s_config.list_kube_config_contexts(config_file=config_file)
        clusters = []
        for context in contexts:
            name = context["name"]
            if self._contexts and name not in self._contexts:
                # filter out
                continue
            if name not in self._clusters:
                if time.time() < self._failed.get(name, 0) + CONTEXT_RETRY_SECONDS:
                    continue
                try:
                    client = k8s_config.new_client_from_config(
                        config_file=config_file, context=name
                    )
                except Exception as e:
                    self._failed[name] = time.time()
                    logger.error(f"Failed to load kubeconfig context {name}: {e}")
                    continue
                self._clusters[name] = Cluster(
                    name, name, client.configuration.host, client
                )
            clusters.append(self._clusters[name])
        return clusters


class MockDiscoverer:
    def get_clusters(self):
        for i in range(3):
            yield Cluster(
                f"mock-cluster-{i}",
                f"mock-cluster-{i}",
                api_server_url=f"https://kube-{i}.example.org",
                client=None,
            )
