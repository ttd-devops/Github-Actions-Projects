#!/usr/bin/env python3
# scripts/copilot_action.py
import os, sys, json, requests, time

def get_copilot_token(session_id):
    url = "https://github.com/github-copilot/chat/token"
    headers = {
        "Cookie": f"user_session={session_id}",
        "X-Requested-With": "XMLHttpRequest",
        "GitHub-Verified-Fetch": "true",
        "Origin": "https://github.com",
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0 (compatible)"
    }
    r = requests.post(url, headers=headers, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"Failed to get token: {r.status_code} {r.text}")
    j = r.json()
    return j.get("token")

def create_thread(token):
    url = "https://api.individual.githubcopilot.com/github/chat/threads"
    headers = {
        "Authorization": f"GitHub-Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {"name": "GH Actions automation"}
    r = requests.post(url, headers=headers, json=payload, timeout=20)
    if r.status_code not in (200,201):
        raise RuntimeError(f"Failed to create thread: {r.status_code} {r.text}")
    data = r.json()
    thread_id = data.get("thread_id") or (data.get("thread") or {}).get("id")
    if not thread_id:
        raise RuntimeError(f"Couldn't parse thread id from: {data}")
    return thread_id

def send_prompt_stream(token, thread_id, prompt, repo_context):
    url = f"https://api.individual.githubcopilot.com/github/chat/threads/{thread_id}/messages"
    headers = {
        "Authorization": f"GitHub-Bearer {token}",
        "Content-Type": "application/json"
    }

    message = {
        "content": prompt,
        "intent": "conversation",
        "streaming": True,
        # include a minimal repository context so Copilot can reference repo items
        "context": [repo_context] if repo_context else [],
        "currentURL": f"https://github.com/{repo_context.get('ownerLogin')+'/'+repo_context.get('name')}" if repo_context else None
    }

    r = requests.post(url, headers=headers, json=message, stream=True, timeout=120)
    if r.status_code not in (200,201):
        raise RuntimeError(f"Failed to send prompt: {r.status_code} {r.text}")

    # response is SSE: parse lines starting with 'data: '
    full = ""
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
        except Exception:
            continue
        # Den's stream emits pieces like {"type":"content","body":"..."}
        if obj.get("type") == "content":
            body = obj.get("body", "")
            full += body
        # optional: handle other types (done, error) if present
        if obj.get("type") == "done":
            break
    return full

def delete_thread(token, thread_id):
    url = f"https://api.individual.githubcopilot.com/github/chat/threads/{thread_id}"
    headers = {"Authorization": f"GitHub-Bearer {token}"}
    try:
        requests.delete(url, headers=headers, timeout=10)
    except Exception:
        pass

def write_github_output(name, value):
    outpath = os.environ.get("GITHUB_OUTPUT")
    if outpath:
        with open(outpath, "a") as fh:
            fh.write(f"{name}<<EOF\n{value}\nEOF\n")
    else:
        # not running in GH actions — print to stdout
        print(f"OUTPUT {name}:\n{value}")

def main():
    session = os.environ.get("SESSION_ID")
    prompt = os.environ.get("PROMPT")
    repo = os.environ.get("REPO")  # e.g. owner/repo
    issue = os.environ.get("ISSUE_NUMBER")

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
            # optional minimal fields:
            "ref": os.environ.get("GITHUB_REF", ""),
            "commitOID": os.environ.get("GITHUB_SHA", "")
        }

    try:
        token = get_copilot_token(session)
        thread_id = create_thread(token)
        answer = send_prompt_stream(token, thread_id, prompt, repo_context)
        # cleanup:
        delete_thread(token, thread_id)
        # write to actions output
        write_github_output("copilot_response", answer)
        print("Done — copilot_response written to GITHUB_OUTPUT")
    except Exception as e:
        print("ERROR:", str(e), file=sys.stderr)
        # write error for easier debugging
        write_github_output("copilot_error", str(e))
        sys.exit(1)

if __name__ == "__main__":
    main()
