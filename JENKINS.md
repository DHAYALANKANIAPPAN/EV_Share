# Jenkins for EV Share

Jenkins is the only build pipeline for this project. It runs the tests, checks the database migrations, and can build and publish the Docker image. Nothing runs automatically: every build starts when you press **Build with Parameters**.

## What you need
- Jenkins installed on your computer and running as a service (`sudo systemctl status jenkins` shows "active (running)")
- Docker installed and running (`docker info` prints information, with no errors)
- The `jenkins` user allowed to use Docker. Check with:
  ```bash
  sudo -u jenkins docker info > /dev/null && echo "Jenkins can use Docker"
  ```
  If that shows "permission denied", run `sudo usermod -aG docker jenkins`, then `sudo systemctl restart jenkins`, then check again.

## 1. Open Jenkins and check the plugins
**Where:** browser, `http://localhost:8080`

Manage Jenkins > Plugins > Installed plugins. These must be installed and enabled:
- **Pipeline** and **Git**
- **Docker Pipeline**
- **Pipeline Stage View**, which draws the stage graph on the job page

If one is missing, open Available plugins, search for its name, tick it, and click Install.

## 2. Create the job (once)
**Where:** browser, Jenkins home page
1. Click **New Item**. Type `EV Share`, choose **Pipeline**, and click **OK**.
2. Under **Pipeline**, set **Definition** to **Pipeline script from SCM** and **SCM** to **Git**.
3. **Repository URL:** `https://github.com/DHAYALANKANIAPPAN/EV_Share.git`
4. **Branch Specifier:** `*/main`
5. **Script Path:** `Jenkinsfile`
6. Click **Save**.

The repository is public, so no login is needed to read it.

## 3. Run a build
**Where:** browser, the EV Share job page
1. Click **Build with Parameters**.
2. Choose one of these:
   - **Tests only:** leave both boxes unticked. This is the normal check.
   - **Build the image:** tick **BUILD_IMAGE**.
   - **Publish a release:** tick **PUSH_IMAGE** (see section 4).
3. Click **Build**.
4. Watch the Stage View. Click the build number, then **Console Output** if a stage fails.

**A green build looks like this:**
- **Test and migrations:** ends with `90 passed` and `No new upgrade operations detected.`
- **Build image:** only runs when BUILD_IMAGE or PUSH_IMAGE is ticked. Ends with the image name.
- **Push image:** only runs when PUSH_IMAGE is ticked. Ends with the pushed image.
- The post message: `EV Share pipeline passed.`

The first build after a change is slower, because packages are downloaded. Later builds reuse them from the `evshare-pip-cache` Docker volume.

## 4. Publish a release image (later, when the project is ready)
This pushes the image to GitHub Container Registry as `ghcr.io/dhayalankaniappan/ev_share`.

**Create a token once:**
1. **Where:** GitHub, Settings > Developer settings > Personal access tokens > Tokens (classic) > Generate new token.
2. Tick the scopes **write:packages** and **read:packages**. Copy the token.

**Store the token in Jenkins once:**
1. **Where:** Jenkins, Manage Jenkins > Credentials > System > Global credentials > Add Credentials.
2. Kind: **Username with password**. Username: `DHAYALANKANIAPPAN`. Password: the token. ID: `ghcr`.
3. Click **Create**.

**Publish:**
1. **Where:** EV Share job, **Build with Parameters**.
2. Tick **PUSH_IMAGE**. This also builds the image.
3. Type the version in **IMAGE_TAG**, for example `v0.1.1`.
4. Click **Build**.

Check the result at GitHub, your profile, Packages, `ev_share`. The new tag appears in the list.

Releases are not created automatically any more. If you want a GitHub release page, create it by hand: Releases > Draft a new release, choose the tag, and publish.

## Troubleshooting
- **"permission denied while trying to connect to the docker API"**: Jenkins can't use Docker. See "What you need" above.
- **"Couldn't find any revision" or "Jenkinsfile not found"**: check the branch is `*/main` and Script Path is `Jenkinsfile`, and that `main` contains the Jenkinsfile.
- **Test stage fails**: open Console Output and read the first red line. The test names are listed there.
- **Push fails with "denied"**: the token is missing the write:packages scope, or the `ghcr` credential ID doesn't match exactly.
- **Stage View missing**: install the Pipeline Stage View plugin (section 1).
