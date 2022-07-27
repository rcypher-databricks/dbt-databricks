# Using GitHub Actions for dbt CI/CD on Databricks
dbt encourages software development lifecycle best-practices, including continuous integration (CI) and continuous deployment (CD). This page describes how you can execute dbt tests on every pull request (PR), only merging when tests pass and you are confident of the build quality.

> The capability of running dbt in a Job is currently in private preview. You must be enrolled in the private preview to follow the steps in this guide. Features, capabilities and pricing may change at any time.

## Overview
![image](/docs/img/ci-cd-overview.png "CI/CD overview")
1. Analytics engineers will issue a pull request on GitHub
2. The GitHub Action will use Databricks CLI to [create and trigger a one-time run](https://docs.databricks.com/dev-tools/api/latest/jobs.html#operation/JobsRunsSubmit).
3. The Job will run `dbt test`
4. SQL generated by dbt will run on a Databricks Cluster. For ease of development, we will use an All Purpose cluster which is already running. You can run dbt on an Automated Cluster instead.

## Prerequisites
- Access to a Databricks workspace
- Ability to create a Personal Access Token (PAT)
- A fork of the [jaffle_shop](https://github.com/dbt-labs/jaffle_shop) demo project. You can, alternatively, follow along with your own dbt project.

## Create GitHub Action
1. Create a `.github/workflows` directory

```
$ mkdir -p .github/workflows
$ cd .github/workflows
```

2. Create a `requirements.txt` file and paste the following, which specifies the version of the Databricks CLI to install

```nofmt
databricks-cli
```

3. Create a file named `job.json` and paste the following content. Please replace the value of `git_url` with your open repository's URL.

```json
{
    "run_name": "jaffle_shop_ci",
    "tasks": [
        {
            "task_key": "jaffle_shop_tests",
            "dbt_task": {
                "commands": [
                    "dbt debug",
                    "dbt test"
                ]
            },
            "existing_cluster_id": "_EXISTING_CLUSTER_ID_",
            "libraries": [
                {
                    "pypi": {
                        "package": "dbt-databricks>=1.0.0,<2.0.0"
                    }
                }
            ]
        }
    ],
    "git_source": {
        "git_url": "https://github.com/dbt/jaffle_shop",
        "git_provider": "gitHub",
        "git_branch": "_GITHUB_BRANCH_"
    }
}
```

Note that we have two template placeholders in the JSON document which will get replaced by the GitHub Action:
- `_EXISTING_CLUSTER_ID_` is the Cluster ID of an existing All Purpose Cluster
- `_GITHUB_BRANCH_` is the Git branch of our project we want to deploy

5. Create a file called `main.yml` and paste the GitHub Action definition in it. This GitHub Action will check out your dbt repo, install the Databricks CLI, submit the job spec you defined above using the Databricks CLI, and check until the job completes or fails.


```yml
name: Databricks Job

on:
  workflow_dispatch:
    branches: [main]
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  DATABRICKS_TOKEN: ${{ secrets.DATABRICKS_TOKEN }}
  DATABRICKS_HOST: ${{ secrets.DATABRICKS_HOST }}
  EXISTING_CLUSTER_ID: ${{ secrets.DATABRICKS_CLUSTER_ID }}

jobs:
  build:
    runs-on: ubuntu-latest
    environment: your-workspace
    strategy:
      matrix:
        python-version: ["pypy-3.8"]
    steps:
      - name: Checkout repository
        uses: actions/checkout@v2

      - name: "Get branch name and save to env"
        env:
          IS_PR: ${{ github.EVENT_NAME == 'pull_request' }}
        run: |
          if ${IS_PR}; then
            BRANCH_NAME="${GITHUB_HEAD_REF}"
          else
            BRANCH_NAME="${GITHUB_REF##*/}"
          fi
          echo "BRANCH_NAME=${BRANCH_NAME}" >> $GITHUB_ENV

      - name: Setup Python
        uses: actions/setup-python@v2
        with:
          python-version: ${{ matrix.python-version }}
          architecture: x64

      - run: python -m pip install -r .github/workflows/requirements.txt

      - name: Set values in Databricks Job spec
        id: set_branch_name
        run: |
          sed -i 's/_GITHUB_BRANCH_/${{ env.BRANCH_NAME }}/g' .github/workflows/job.json
          sed -i 's/_EXISTING_CLUSTER_ID_/${{ env.EXISTING_CLUSTER_ID }}/g' .github/workflows/job.json

      - name: Submit Databricks Job
        id: submit_job
        run: |
          job_run_submit_result=$( databricks runs submit --version=2.1 --json-file .github/workflows/job.json )
          job_run_id=$( echo $job_run_submit_result | jq .run_id )
          echo "::set-output name=job_run_id::$job_run_id"

      - name: Check Databricks Job status
        id: check_job_status
        run: |
          sleep 1
          while [ $(databricks runs get --version=2.1 --run-id ${{steps.submit_job.outputs.job_run_id}} | jq -r ".state.life_cycle_state") != "TERMINATED" ];do
            echo "Run ID ${{steps.submit_job.outputs.job_run_id}} is running."
            sleep 3
          done

          echo "Run ID ${{steps.submit_job.outputs.job_run_id}} has terminated."

          # Check if the result state is SUCCESS
          if [ $(databricks runs get --version=2.1 --run-id ${{steps.submit_job.outputs.job_run_id}} | jq -r ".state.result_state") == "SUCCESS" ]
          then
            echo "Success."
            exit 0
          else
            echo "Run ID ${{steps.submit_job.outputs.job_run_id}} did not run successfully"
            exit 1
          fi

```


## Configure GitHub Secrets

Now we will configure some secrets in GitHub, which will substitute two placeholder values in our job spec:

1. Go to your repo on GitHub
2. Click _Settings_
3. In the left navigation bar, click _Secrets > Actions_
4. Add an environment secret called `DATABRICKS_HOST`. The value should be the hostname of your workspace e.g. `myworkspace.cloud.databricks.com`
5. Add an environment secret called `DATABRICKS_TOKEN`. The value should be the PAT you created earlier.

## Test GitHub Action

Follow these steps to test your new GitHub Action:
1. Go to your repo on GitHub
2. Click _Actions_ in the top navigation bar
3. Click the Action named "Databricks Job" and click _Run workflow_