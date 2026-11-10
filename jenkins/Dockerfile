# Jenkins with the Docker command-line tool, so pipelines can build images.
# Build it once:  docker build -t evshare-jenkins ./jenkins
FROM jenkins/jenkins:lts
USER root
RUN apt-get update && apt-get install -y --no-install-recommends docker.io \
    && rm -rf /var/lib/apt/lists/*
USER jenkins
