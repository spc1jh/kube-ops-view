{{/* vim: set filetype=mustache: */}}
{{/*
Expand the name of the chart.
*/}}
{{- define "kube-ops-view.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "kube-ops-view.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "kube-ops-view.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels
*/}}
{{- define "kube-ops-view.labels" -}}
app.kubernetes.io/name: {{ include "kube-ops-view.name" . }}
helm.sh/chart: {{ include "kube-ops-view.chart" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/part-of: {{ .Release.Name }}
{{- end -}}

{{/*
Selector labels of the kube-ops-view pods
*/}}
{{- define "kube-ops-view.selectorLabels" -}}
app.kubernetes.io/name: {{ include "kube-ops-view.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: frontend
{{- end -}}

{{/*
Selector labels of the Redis pods
*/}}
{{- define "kube-ops-view.redisSelectorLabels" -}}
app.kubernetes.io/name: {{ include "kube-ops-view.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: redis
{{- end -}}

{{/*
Name of the ServiceAccount to use
*/}}
{{- define "kube-ops-view.serviceAccountName" -}}
{{- if .Values.rbac.create -}}
{{- include "kube-ops-view.fullname" . -}}
{{- else -}}
{{- .Values.rbac.serviceAccountName -}}
{{- end -}}
{{- end -}}
