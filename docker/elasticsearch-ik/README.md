# Elasticsearch (8.10.2) with IK plugin for tests

This folder contains a Dockerfile that builds an Elasticsearch 8.10.2 image with the IK Chinese analyzer plugin installed. The test code in this repo expects a Testcontainers image tagged as `local/elasticsearch-ik:8.10.2` by default.

Steps to build and use locally:

1. Build the image (PowerShell):

```powershell
cd docker\elasticsearch-ik
./build.ps1
```

2. Verify image exists:

```powershell
docker images -f "reference=local/elasticsearch-ik:8.10.2"
```

3. Run tests (the test base will by default use `local/elasticsearch-ik:8.10.2`):

```powershell
# From project root
mvn -Dtest=AuthorEsQueryControllerTest test -DfailIfNoTests=false
```

Notes:
- The Dockerfile downloads the IK plugin release for Elasticsearch 8.10.2 from the project's GitHub releases. If that URL changes, update the Dockerfile to point to the correct artifact.
- If you prefer to use a different image name or tag, set the environment variable `TEST_ES_IMAGE` before running tests, e.g.

```powershell
$env:TEST_ES_IMAGE = 'myrepo/elasticsearch-ik:8.10.2'
mvn -Dtest=AuthorEsQueryControllerTest test -DfailIfNoTests=false
```

- If your environment blocks downloads during `docker build`, you can manually prepare an image with the IK plugin and tag it `local/elasticsearch-ik:8.10.2`.
