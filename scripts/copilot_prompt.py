#!/usr/bin/env python3
# scripts/copilot_action.py
import os, sys, json, requests, time

def get_copilot_token(session_id):
    print("[DEBUG] Getting Copilot token...")
    url = "https://github.com/github-copilot/chat/token"
    headers = {
        "Cookie": f"user_session={session_id}",
        "X-Requested-With": "XMLHttpRequest",
        "GitHub-Verified-Fetch": "true",
        "Origin": "https://github.com",
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0 (compatible)"
    }
    print(f"[DEBUG] Requesting token from {url}")
    r = requests.post(url, headers=headers, timeout=20)
    print(f"[DEBUG] Token response status: {r.status_code}")
    if r.status_code != 200:
        print(f"[DEBUG] Token response body: {r.text}")
        raise RuntimeError(f"Failed to get token: {r.status_code} {r.text}")
    j = r.json()
    print(f"[DEBUG] Copilot token received (truncated): {str(j.get('token'))[:20]}...")
    return j.get("token")

def create_thread(token):
    print("[DEBUG] Creating new Copilot thread...")
    url = "https://api.individual.githubcopilot.com/github/chat/threads"
    headers = {
        "Authorization": f"GitHub-Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {"name": "GH Actions automation"}
    print(f"[DEBUG] POST {url} with payload {payload}")
    r = requests.post(url, headers=headers, json=payload, timeout=20)
    print(f"[DEBUG] Thread creation status: {r.status_code}")
    if r.status_code not in (200,201):
        print(f"[DEBUG] Thread creation response: {r.text}")
        raise RuntimeError(f"Failed to create thread: {r.status_code} {r.text}")
    data = r.json()
    print(f"[DEBUG] Thread creation response JSON: {data}")
    thread_id = data.get("thread_id") or (data.get("thread") or {}).get("id")
    if not thread_id:
        raise RuntimeError(f"Couldn't parse thread id from: {data}")
    print(f"[DEBUG] Created thread_id: {thread_id}")
    return thread_id

def send_prompt_stream(token, thread_id, prompt, repo_context):
    print("[DEBUG] Sending prompt to Copilot thread...")
    url = f"https://api.individual.githubcopilot.com/github/chat/threads/{thread_id}/messages"
    headers = {
        "Authorization": f"GitHub-Bearer {token}",
        "Content-Type": "application/json"
    }

    message = {
        "content": prompt,
        "intent": "conversation",
        "streaming": True,
        "context": [repo_context] if repo_context else [],
        "currentURL": f"https://github.com/{repo_context.get('ownerLogin')+'/'+repo_context.get('name')}" if repo_context else None
    }

    print(f"[DEBUG] POST {url} with prompt: {prompt}")
    print(f"[DEBUG] Repo context: {repo_context}")
    r = requests.post(url, headers=headers, json=message, stream=True, timeout=120)
    print(f"[DEBUG] Prompt send status: {r.status_code}")
    if r.status_code not in (200,201):
        print(f"[DEBUG] Prompt send response: {r.text}")
        raise RuntimeError(f"Failed to send prompt: {r.status_code} {r.text}")

    full = ""
    print("[DEBUG] Reading streaming response...")
    for raw in r.iter_lines(decode_unicode=True):
        if not raw:
            continue
        line = raw.strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if payload == "[DONE]":
            break
        try:
            obj = json.loads(payload)
        except Exception as ex:
            print(f"[DEBUG] Failed to parse payload line: {payload} — {ex}")
            continue
        if obj.get("type") == "content":
            body = obj.get("body", "")
            print(f"[DEBUG] Received chunk: {body}")
            full += body
        if obj.get("type") == "done":
            break
    print(f"[DEBUG] Full Copilot response collected.")
    return full

def delete_thread(token, thread_id):
    print(f"[DEBUG] Deleting Copilot thread {thread_id}...")
    url = f"https://api.individual.githubcopilot.com/github/chat/threads/{thread_id}"
    headers = {"Authorization": f"GitHub-Bearer {token}"}
    try:
        r = requests.delete(url, headers=headers, timeout=10)
        print(f"[DEBUG] Delete thread status: {r.status_code}")
    except Exception as e:
        print(f"[DEBUG] Delete thread failed: {e}")

def write_github_output(name, value):
    outpath = os.environ.get("GITHUB_OUTPUT")
    print(f"[DEBUG] Writing to GITHUB_OUTPUT: {name}")
    if outpath:
        with open(outpath, "a") as fh:
            fh.write(f"{name}<<EOF\n{value}\nEOF\n")
    else:
        print(f"OUTPUT {name}:\n{value}")

def main():
    print("[DEBUG] Starting copilot_action.py main()")
    session = os.environ.get("SESSION_ID")
    prompt = os.environ.get("PROMPT")
    repo = os.environ.get("REPO")
    issue = os.environ.get("ISSUE_NUMBER")

    print(f"[DEBUG] SESSION_ID present: {bool(session)}")
    print(f"[DEBUG] PROMPT: {prompt}")
    print(f"[DEBUG] REPO: {repo}")
    print(f"[DEBUG] ISSUE_NUMBER: {issue}")

    if not session or not prompt:
        print("Missing SESSION_ID or PROMPT", file=sys.stderr)
        sys.exit(2)

    repo_context = {}
    if repo and "/" in repo:
        owner, name = repo.split("/", 1)
        repo_context = {
            "name": name,
            "ownerLogin": owner,
            "type": "repository",
            "ref": os.environ.get("GITHUB_REF", ""),
            "commitOID": os.environ.get("GITHUB_SHA", "")
        }
    print(f"[DEBUG] Repo context built: {repo_context}")

    try:
        token = get_copilot_token(session)
        thread_id = create_thread(token)
        answer = send_prompt_stream(token, thread_id, prompt, repo_context)
        delete_thread(token, thread_id)
        write_github_output("copilot_response", answer)
        print("[DEBUG] Done — copilot_response written to GITHUB_OUTPUT")
    except Exception as e:
        print("ERROR:", str(e), file=sys.stderr)
        write_github_output("copilot_error", str(e))
        sys.exit(1)

if __name__ == "__main__":
    main()
