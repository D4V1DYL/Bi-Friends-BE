pipeline {
    agent any

    environment {
        IMAGE_NAME = "bi-friends-be"
        CONTAINER_NAME = "fastapi-container"
        ENV_FILE = "/var/lib/jenkins/.env"
        PORT = "8000"
        DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1348391496319111241/Q2-Y2zNTe3MC-PlAsziHoKhD6pWdWb6ZPcLoLqtkUq4f5J5CmmYqcR0uIGddt7ajGVux"
        JENKINS_URL = "https://jenkins.bifriends.my.id/"
    }

    triggers {
        githubPush()
    }

    stages {
        stage('Check Branch') {
            steps {
                script {
                    def branchName = sh(
                        script: 'git name-rev --name-only HEAD || git rev-parse --abbrev-ref HEAD',
                        returnStdout: true
                    ).trim()

                    // Remove 'origin/' prefix and '^0' suffix if present
                    branchName = branchName.replaceAll('^origin/', '').replaceAll('\\^0$', '')

                    echo "Current branch: ${branchName}"

                    if (branchName != 'remotes/origin/main') {
                        error "Skipping deployment: Changes were pushed to '${branchName}', not 'main'."
                    }
                }
            }
        }

        stage('Clone Repository') {
            steps {
                git branch: 'main', 
                    credentialsId: 'github-ssh-key',
                    url: 'git@github.com:D4V1DYL/Bi-Friends-BE.git'
            }
        }

        stage('Extract Commit Info') {
            steps {
                script {
                    env.GIT_COMMITTER = sh(script: "git log -1 --pretty=format:'%an'", returnStdout: true).trim()
                    env.GIT_COMMIT_MESSAGE = sh(script: "git log -1 --pretty=format:'%s'", returnStdout: true).trim()
                }
            }
        }

        stage('Build Docker Image') {
            steps {
                sh 'docker build -t $IMAGE_NAME .'
            }
        }

        stage('Stop and Remove Old Container') {
            steps {
                script {
                    def existingContainer = sh(script: "docker ps -aq -f name=$CONTAINER_NAME", returnStdout: true).trim()
                    if (existingContainer) {
                        echo "Stopping and removing old container: $CONTAINER_NAME"
                        sh "docker rm -f $CONTAINER_NAME"
                    } else {
                        echo "No existing container found with name: $CONTAINER_NAME"
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
                sh 'docker run -d --name $CONTAINER_NAME --env-file $ENV_FILE -p $PORT:8000 $IMAGE_NAME'
            }
        }
    }

    post {
        success {
            script {
                def payload = """
                {
                    "username": "BiFriends Bot - Jenkins",
                    "avatar_url": "https://www.jenkins.io/images/logos/jenkins/jenkins.png",
                    "content": "✅ **Deployment Successful!** \\n **Job:** BiFriendsBE \\n **Build:** #${env.BUILD_NUMBER} \\n **Deployed By:** ${env.GIT_COMMITTER} \\n **Commit:** ${env.GIT_COMMIT_MESSAGE} \\n 🔗 ${JENKINS_URL}job/BiFriendsBE/${env.BUILD_NUMBER}/"
                }
                """
                sh """
                curl -H "Content-Type: application/json" -X POST -d '${payload}' $DISCORD_WEBHOOK_URL
                """
            }
        }
        failure {
            script {
                def payload = """
                {
                    "username": "BiFriends Bot - Jenkins",
                    "avatar_url": "https://www.jenkins.io/images/logos/jenkins/jenkins.png",
                    "content": "❌ **Deployment Failed!** \\n **Job:** BiFriendsBE \\n **Build:** #${env.BUILD_NUMBER} \\n **Deployed By:** ${env.GIT_COMMITTER} \\n **Commit:** ${env.GIT_COMMIT_MESSAGE} \\n 🔗 ${JENKINS_URL}job/BiFriendsBE/${env.BUILD_NUMBER}/"
                }
                """
                sh """
                curl -H "Content-Type: application/json" -X POST -d '${payload}' $DISCORD_WEBHOOK_URL
                """
            }
        }
    }
}
