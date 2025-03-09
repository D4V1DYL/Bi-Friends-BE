pipeline {
    agent any

    environment {
        IMAGE_NAME = "bi-friends-be"
        CONTAINER_NAME = "fastapi-container"
        ENV_FILE = "/var/lib/jenkins/.env"
        DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1348391496319111241/Q2-Y2zNTe3MC-PlAsziHoKhD6pWdWb6ZPcLoLqtkUq4f5J5CmmYqcR0uIGddt7ajGVux"
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
            script {
                def commitMessage = sh(script: "git log -1 --pretty=%B", returnStdout: true).trim()
                def author = sh(script: "git log -1 --pretty=%an", returnStdout: true).trim()

                sh """
                    curl -H "Content-Type: application/json" -X POST -d '{
                        "username": "BiFriends Bot - Jenkins",
                        "avatar_url": "https://www.jenkins.io/images/logos/jenkins/jenkins.png",
                        "content": "✅ **Deployment Successful!** \\n **Job:** BiFriendsFE \\n **Build:** #\${BUILD_NUMBER} \\n **Deployed By:** \${author} \\n **Commit:** \${commitMessage} \\n 🔗 ${env.BUILD_URL}"
                    }' $DISCORD_WEBHOOK_URL
                """
            }
        }
        failure {
            script {
                def commitMessage = sh(script: "git log -1 --pretty=%B", returnStdout: true).trim()
                def author = sh(script: "git log -1 --pretty=%an", returnStdout: true).trim()

                sh """
                    curl -H "Content-Type: application/json" -X POST -d '{
                        "username": "BiFriends Bot - Jenkins",
                        "avatar_url": "https://www.jenkins.io/images/logos/jenkins/jenkins.png",
                        "content": "❌ **Deployment Failed!** \\n **Job:** BiFriendsFE \\n **Build:** #\${BUILD_NUMBER} \\n **Deployed By:** \${author} \\n **Commit:** \${commitMessage} \\n 🔗 ${env.BUILD_URL}"
                    }' $DISCORD_WEBHOOK_URL
                """
            }
        }
    }
}
