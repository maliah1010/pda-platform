# Deploying PDA Platform on Render

This guide explains how to deploy your own instance of PDA Platform on Render. Running your own instance gives you control over the environment, allows you to set your own API keys, and removes any dependency on the shared public endpoint.

---

## Prerequisites

- A Render account (free tier is sufficient to get started)
- A GitHub account (to fork the repository)
- An Anthropic API key (required for AI-powered tools; not required for data parsing and validation)

---

## Step 1: Fork the Repository

Go to [github.com/antnewman/pda-platform](https://github.com/antnewman/pda-platform) and fork the repository to your own GitHub account. Render will deploy from your fork, which means you control when updates are applied.

---

## Step 2: Deploy to Render

The repository includes a `render.yaml` file that configures the deployment. Use the one-click deploy button:

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/antnewman/pda-platform)

Alternatively, in the Render dashboard:

1. Select **New > Web Service**
2. Connect your GitHub account and select your fork of `pda-platform`
3. Render will detect the `render.yaml` and pre-populate the service settings

---

## Step 3: Set Environment Variables

In the Render dashboard for your new service, add the following environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | For AI tools | Your Anthropic API key. Required for `track_review_actions`, `generate_narrative`, and recurrence detection. |
| `PORT` | Optional | The port the server listens on. Render sets this automatically; you do not usually need to override it. |
| `PDA_STORE_PATH` | Optional | Path to the AssuranceStore SQLite file. If not set, defaults to the container home directory, which is ephemeral on Render's free tier. |

For persistent data storage on Render, add a Render Disk and set `PDA_STORE_PATH` to a path on that disk (e.g. `/data/store.db`).

---

## Step 4: Verify the Health Check

Once the deploy completes, Render will show the service as Live. Confirm it is running by visiting the health endpoint:

```
https://<your-service-name>.onrender.com/health
```

You should receive a `200 OK` response with a JSON body confirming the server status.

---

## Step 5: Connect Claude.ai

With your service running, copy the SSE endpoint URL:

```
https://<your-service-name>.onrender.com/sse
```

In Claude.ai, open Settings and add a new MCP server connection using this URL. Once connected, Claude will have access to all 58 PDA Platform tools via your own instance.

---

## Free Tier Considerations

Render's free tier spins down services that are idle for 15 minutes. The first request after a cold start may take several seconds to respond while the server initialises. Subsequent requests within the active window respond normally.

If your team needs consistent response times, consider upgrading to a paid Render plan or running the server locally using `pda-platform-remote`.

---

## Updating Your Deployment

To apply updates from the upstream repository, sync your fork on GitHub and then trigger a manual deploy in the Render dashboard, or enable automatic deploys so that pushes to your fork's main branch trigger a redeploy.
