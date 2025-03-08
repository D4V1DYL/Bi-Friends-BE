pipeline {
    agent any

    environment {
        IMAGE_NAME = "bi-friends-be"
        CONTAINER_NAME = "fastapi-container"
        ENV_FILE = "/var/lib/jenkins/.env"
    }

    stages {
        stage('Clone Repository') {
            steps {
                git branch: 'main', 
                    credentialsId: 'github-ssh-key',
                    url: 'git@github.com:D4V1DYL/Bi-Friends-BE.git'
            }
        }

        stage('Build Docker Image') {
            steps {
                sh 'docker build -t $IMAGE_NAME .'
            }
        }

        stage('Stop Old Container') {
            steps {
                script {
                    def running = sh(script: "docker ps -q -f name=$CONTAINER_NAME", returnStdout: true).trim()
                    if (running) {
                        sh "docker stop $CONTAINER_NAME && docker rm $CONTAINER_NAME"
                    }
                }
            }
        }

        stage('Check .env File') {
            steps {
                script {
                    def envExists = sh(script: "[ -f $ENV_FILE ] && echo 'exists' || echo 'missing'", returnStdout: true).trim()
                    if (envExists != 'exists') {
                        error "ERROR: .env file is missing at $ENV_FILE!"
                    }
                }
            }
        }

        stage('Run New Container') {
            steps {
                sh 'docker run -d --name $CONTAINER_NAME --env-file $ENV_FILE -p 8000:8000 $IMAGE_NAME'
            }
        }
    }

    post {
        success {
            echo "Deployment Successful!"
        }
        failure {
            echo "Deployment Failed!"
        }
    }
}
