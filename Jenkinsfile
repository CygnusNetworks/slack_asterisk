@Library("jenkins-pipelines") _

pipeline {
    agent {
      label 'docker-jenkins'
    }

    stages {
        stage('Checkout SCM') {
            steps {
                script {
                    checkout scm
                }
            }
        }
        stage('Build') {
            steps {
                script {
                    dockerBuild.buildAndPush(["linux/amd64", "linux/arm64"])
                }
            }
        }
    }
}
