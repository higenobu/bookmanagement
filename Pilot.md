If your application code is in GitHub, you can use TestSprite CLI, and GitHub actually gives you two useful ways to use it.
The simplest setup is to clone the repository onto your computer, enter the project directory, install TestSprite CLI, and configure it:
git clone <your-github-repository>
cd <your-project>

npm install -g @testsprite/testsprite-cli
testsprite setup
TestSprite currently requires a supported Node.js 20+ version and a TestSprite account/API key. You can also use npx @testsprite/testsprite-cli instead of installing globally. (TestSprite)
For your existing application
Your application is already running at the URL you showed:
http://3.131.245.175:8050/login
That's important because TestSprite CLI normally tests the running application, not simply the GitHub source files. For frontend testing, it drives a real browser against a live URL. (TestSprite)
So your architecture could be:
GitHub Repository
       ↓
git clone
       ↓
Local source code
       ↓
Claude Code / Codex
       ↓
modify source
       ↓
deploy/start application
       ↓
http://3.131.245.175:8050
       ↓
TestSprite CLI
       ↓
PASS / FAIL
This is especially useful for the failure you just found. You can have a coding agent inspect your GitHub code, fix the search-field problem, and then ask TestSprite to rerun the failing test.
Conceptually:
TestSprite:
"Search field cannot be cleared"
            ↓
Claude Code
            ↓
inspect GitHub source
            ↓
find search-field implementation
            ↓
modify code
            ↓
redeploy/restart
            ↓
TestSprite CLI
            ↓
rerun test
        ↙       ↘
     PASS       FAIL
                 ↓
             fix again
TestSprite specifically supports rerunning tests after a change, and its CLI can return failure information in a form coding agents can consume. (TestSprite)
Even better: GitHub Actions + CLI
Once this works manually, you can put TestSprite into GitHub Actions:
Developer changes code
          ↓
       git push
          ↓
        GitHub
          ↓
    GitHub Actions
          ↓
   Build / Deploy
          ↓
   TestSprite CLI
          ↓
    ┌─────┴─────┐
   PASS        FAIL
    ↓            ↓
  Merge       Block /
              Fix code
TestSprite explicitly supports GitHub Actions and can use its exit code to make a failed test fail the CI job. It also provides testsprite ci init github to scaffold a GitHub Actions workflow. (TestSprite)
There is also a separate TestSprite GitHub App approach that listens for deployment events and reports results back to pull requests without requiring you to add TestSprite commands to your workflow. (TestSprite)
For your current experiment, I would start simpler
Don't start with GitHub Actions yet. First prove the repair loop manually:
GitHub code
    ↓
Claude Code
    ↓
TestSprite CLI
    ↓
Find failure
    ↓
Claude fixes code
    ↓
TestSprite CLI retests
If that works reliably for the “clear title search field” failure you just showed me, then we can move the same process into GitHub Actions.
TestSprite CLI official page
If you give me the GitHub repository name/link, I can show you the exact TestSprite CLI setup for this particular application.
