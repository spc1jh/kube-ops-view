.PHONY: clean test appjs docker push mock

IMAGE            ?= kube-ops-view
VERSION          ?= $(shell git describe --tags --always --dirty)
TAG              ?= $(VERSION)
TTYFLAGS         = $(shell test -t 0 && echo "-it")

default: docker

.PHONY: install
install:
	uv sync

clean:
	rm -fr kube_ops_view/static/build

.PHONY: lint
lint: install
	uv run pre-commit run --all-files

test: lint install
	uv run pytest -v --cov=kube_ops_view --cov-report=term

version:
	sed -i "s/kube-ops-view:.*/kube-ops-view:$(VERSION)/" deploy/*.yaml

appjs:
	cd app && npm ci && npm run build

docker:
	docker build --build-arg "VERSION=$(VERSION)" -t "$(IMAGE):$(TAG)" .
	@echo 'Docker image $(IMAGE):$(TAG) can now be used.'

docker-arm:
	docker run --rm --privileged multiarch/qemu-user-static --reset -p yes
	docker buildx create --name arm-node --append --use --platform "linux/arm"
	docker buildx build --build-arg "VERSION=$(VERSION)" --platform "linux/arm" -t $(IMAGE):$(TAG) --load .
	docker buildx rm arm-node
	@echo 'Docker image $(IMAGE):$(TAG) can now be used.'

push: docker
	docker push "$(IMAGE):$(TAG)"
	docker tag "$(IMAGE):$(TAG)" "$(IMAGE):latest"
	docker push "$(IMAGE):latest"

mock:
	docker run $(TTYFLAGS) -p 8080:8080 "$(IMAGE):$(TAG)" --mock \
		--node-link-url-template "https://kube-web-view.example.org/clusters/{cluster}/nodes/{name}" \
		--pod-link-url-template "https://kube-web-view.example.org/clusters/{cluster}/namespaces/{namespace}/pods/{name}"
