FROM docker.elastic.co/elasticsearch/elasticsearch:8.10.2

# Run as root to install plugin
USER root

# Install IK analysis plugin for Elasticsearch 8.10.2
# If this release asset URL changes, update to the correct release artifact URL.
RUN elasticsearch-plugin install --batch https://get.infini.cloud/elasticsearch/analysis-ik/8.10.2

# Return to non-root user
USER elasticsearch
