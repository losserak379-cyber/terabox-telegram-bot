# TeraBox Telegram Bot

Telegram bot that accepts TeraBox share links, asks a separately deployed API for a download URL, downloads a bounded temporary file, and sends it as a Telegram video.

## Railway variables
- `BOT_TOKEN`: token from BotFather (keep secret)
- `TERABOX_API_URL`: base URL of your deployed API, without a trailing slash
- `MAX_DOWNLOAD_MB`: defaults to 45 MB to stay conservative for Bot API uploads
- `DOWNLOAD_TIMEOUT`: defaults to 180 seconds

## Deploy
Connect this repository to Railway and deploy as a worker service. Add the variables above. Do not put secrets in GitHub.

## Important
This bot is not fully functional until `terabox-api` is configured with a working, trusted extraction provider. Provider URL formats vary and must be integrated from its documentation. Check current Telegram Bot API upload limits and your Railway storage/bandwidth limits before increasing `MAX_DOWNLOAD_MB`.
