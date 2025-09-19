#!/usr/bin/env python3
import os, json, sys, requests, time

def main():
    session_id = os.environ.get("COPILOT_SESSION")
    prompt = os.environ.get("PROMPT")
    if not session_id or not prompt:
        print("Missing COPILOT_SESSION or PROMPT")
        sys.exit(1)

    headers = {
        "Cookie": f"user_session={session_id}",
        "Accept": "application/json",
        "User-Agent": "CopilotMCP/1.0"
    }

    # 1. Get a Copilot chat token
    r = requests.post(
        "https://api.github.com/copilot_internal/v2/token",
        headers=headers
    )
    if r.status_code != 200:
        print("Failed to get token:", r.status_code, r.text)
        sys.exit(1)

    copilot_token = r.json()["token"]

    # 2. Bootstrap a chat thread
    thread_req = {
        "title": "Automated Copilot Workflow",
        "metadata": {},
        "visibility": "unlisted"
    }
    r = requests.post(
        "https://api.githubcopilot.com/chat/threads",
        headers={
            "Authorization": f"Bearer {copilot_token}",
            "Accept": "application/json"
        },
        json=thread_req
    )
    if r.status_code != 201:
        print("Failed to create thread:", r.status_code, r.text)
        sys.exit(1)

    thread_id = r.json()["id"]

    # 3. Send prompt to Copilot
    message_req = {
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }
    r = requests.post(
        f"https://api.githubcopilot.com/chat/threads/{thread_id}/messages",
        headers={
            "Authorization": f"Bearer {copilot_token}",
            "Accept": "application/json"
        },
        json=message_req
    )
    if r.status_code != 200:
        print("Failed to send prompt:", r.status_code, r.text)
        sys.exit(1)

    data = r.json()
    answer = data["choices"][0]["message"]["content"]
    print("===== COPILOT RESPONSE =====")
    print(answer)

    # 4. Output to GitHub Actions
    with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
        fh.write(f"response<<EOF\n{answer}\nEOF\n")

if __name__ == "__main__":
    main()
