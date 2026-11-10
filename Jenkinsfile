// Jenkins pipeline for EV Share.
// Runs only when you press "Build with Parameters" in Jenkins (no automatic triggers).
pipeline {
    agent none

    options {
        timestamps()
        disableConcurrentBuilds()
        timeout(time: 30, unit: 'MINUTES')
    }

    parameters {
        booleanParam(name: 'BUILD_IMAGE', defaultValue: false, description: 'Build the Docker image on this Jenkins server (needs Docker)')
        booleanParam(name: 'PUSH_IMAGE', defaultValue: false, description: 'Push the image to GitHub Container Registry (needs the ghcr credential)')
        string(name: 'IMAGE_TAG', defaultValue: 'dev', description: 'Image tag, for example v0.1.1')
    }

    environment {
        IMAGE = 'ghcr.io/dhayalankaniappan/ev_share'
    }

    stages {
        stage('Test and migrations') {
            agent {
                docker {
                    image 'python:3.12-slim'
                    // The named volume keeps downloaded packages between builds, so later builds install much faster.
                    args '-u root -v evshare-pip-cache:/root/.cache/pip'
                }
            }
            environment {
                PIP_ROOT_USER_ACTION = 'ignore'
            }
            steps {
                sh '''
                    pip install -q -r requirements-dev.txt -r requirements-redis.txt -r requirements-s3.txt
                    pytest -q
                    rm -f evshare.db
                    alembic upgrade head
                    alembic check
                '''
            }
        }

        stage('Build image') {
            when { expression { params.BUILD_IMAGE || params.PUSH_IMAGE } }
            agent any
            steps {
                sh 'docker build -t "$IMAGE:$IMAGE_TAG" .'
            }
        }

        stage('Push image') {
            when { expression { params.PUSH_IMAGE } }
            agent any
            steps {
                withCredentials([usernamePassword(credentialsId: 'ghcr', usernameVariable: 'GH_USER', passwordVariable: 'GH_TOKEN')]) {
                    sh '''
                        echo "$GH_TOKEN" | docker login ghcr.io -u "$GH_USER" --password-stdin
                        docker push "$IMAGE:$IMAGE_TAG"
                    '''
                }
            }
        }
    }

    post {
        success { echo 'EV Share pipeline passed.' }
        failure { echo 'EV Share pipeline failed. Open the failed stage log above.' }
    }
}
