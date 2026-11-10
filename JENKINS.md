# Jenkins setup for EV Share

Start from the project folder. Jenkins runs in Docker, so Docker must be installed and running.

## 1. Build the Jenkins image
    docker build -t evshare-jenkins ./jenkins

## 2. Start Jenkins
    docker run -d --name jenkins -p 8080:8080 -p 50000:50000 \
      -v jenkins_home:/var/jenkins_home \
      -v /var/run/docker.sock:/var/run/docker.sock \
      --group-add "$(stat -c '%g' /var/run/docker.sock)" \
      evshare-jenkins

## 3. Unlock Jenkins
Open http://localhost:8080 and paste the password printed by:
    docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
Choose "Install suggested plugins", then create your admin user.
Then install the plugin "Docker Pipeline": Manage Jenkins > Plugins > Available plugins.

## 4. Add the GitHub credential (only needed to push the image)
1. On GitHub: Settings > Developer settings > Personal access tokens > Tokens (classic) > Generate new token.
   Tick the scopes write:packages and read:packages. Copy the token.
2. In Jenkins: Manage Jenkins > Credentials > System > Global credentials > Add Credentials.
   Kind: Username with password. Username: DHAYALANKANIAPPAN. Password: the token. ID: ghcr.

## 5. Create the job
1. Click New Item, type "EV Share", choose Pipeline, click OK.
2. Under Pipeline: Definition choose "Pipeline script from SCM", SCM "Git".
3. Repository URL: https://github.com/DHAYALANKANIAPPAN/EV_Share.git
4. Branch Specifier: */main
5. Script Path: Jenkinsfile
6. Save.

## 6. Run it
Click "Build with Parameters".
- Leave all boxes unticked to run only the tests and migration checks.
- Tick BUILD_IMAGE to also build the image.
- Tick PUSH_IMAGE (which also builds) to publish it to ghcr.io, with the tag you type in IMAGE_TAG.
Click Build. Open the build and then Console Output to see each stage.
