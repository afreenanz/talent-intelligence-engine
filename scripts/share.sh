#!/usr/bin/env bash
# Share the running app through a temporary public link (Cloudflare quick tunnel).
#
#   scripts/share.sh          start the app (if needed) and the tunnel, print the link
#   scripts/share.sh url      print the current link again
#   scripts/share.sh stop     close the link (the app keeps running locally)
#
# The link works only while this machine is on and Docker is running, and it changes every
# time the tunnel restarts. Anyone who has it can open the site, so rate limits stay on.
set -euo pipefail
cd "$(dirname "$0")/.."

compose() { docker compose --profile app --profile share "$@"; }

# Ask Cloudflare's resolver directly: checking a brand-new name through the system resolver too
# early makes the OS cache "does not exist" for a while, which would break the link for you.
answers() {
  local host="${1#https://}" ip=""
  if command -v dig >/dev/null; then ip="$(dig +short @1.1.1.1 "$host" A | head -1)"; fi
  if [ -n "$ip" ]; then
    curl -fsS -o /dev/null --max-time 10 --resolve "$host:443:$ip" "$1/health/live" 2>/dev/null
  else
    return 1
  fi
}

current_url() {
  compose logs tunnel 2>/dev/null | grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1
}

case "${1:-start}" in
  start)
    if [ ! -f .env ]; then echo "No .env file. Copy .env.example to .env first (see README)."; exit 1; fi
    echo "Starting the app and the tunnel..."
    compose up -d
    printf "Waiting for the public link"
    for _ in $(seq 1 60); do
      url="$(current_url || true)"
      if [ -n "$url" ]; then break; fi
      printf "."; sleep 1
    done
    echo
    if [ -z "${url:-}" ]; then
      echo "No link after 60 s. Check: docker compose --profile share logs tunnel"; exit 1
    fi
    # A new link needs a few seconds before DNS and Cloudflare route it.
    printf "Checking the link answers"
    ok=""
    for _ in $(seq 1 30); do
      if answers "$url"; then ok=1; break; fi
      printf "."; sleep 3
    done
    echo
    if [ -z "$ok" ]; then
      cat <<MSG

  The tunnel started ($url) but the link isn't answering yet.
  Wait a minute and open it. If it still fails, get a fresh link:
    scripts/share.sh stop && scripts/share.sh

MSG
      exit 1
    fi
    cat <<MSG

  Public link:  $url

  Demo sign-in: demo@example.com
  Password:     the DEMO_PASSWORD value in your .env file

  - Works only while this laptop is on and Docker is running.
  - The link changes if the tunnel restarts. Run 'scripts/share.sh url' to see it again.
  - To let visitors use only the demo account, set SIGNUP_ENABLED=false in .env and run
    'docker compose --profile app up -d' once.
  - Close it with: scripts/share.sh stop

MSG
    ;;
  url)
    url="$(current_url || true)"
    if [ -n "$url" ]; then echo "$url"; else echo "Not sharing right now. Run scripts/share.sh"; fi
    ;;
  stop)
    compose stop tunnel >/dev/null 2>&1 || true
    compose rm -f tunnel >/dev/null 2>&1 || true
    echo "The public link is closed. The app is still running at http://localhost:${WEB_HOST_PORT:-8090}"
    ;;
  *)
    echo "usage: scripts/share.sh [start|url|stop]"; exit 2
    ;;
esac
