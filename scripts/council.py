#!/usr/bin/env python3
"""
Council: multi-vendor adjudication via a Cloudflare AI Gateway.

ONE authoritative cross-vendor verdict per decision instead of guessing alone.
All members route through your AI Gateway, tagged with cf-aig-metadata, so
every council call is observable in your Cloudflare dashboard under
AI > AI Gateway > your gateway.

Members (credentials read from ~/.openclaw/openclaw.json + env, no hardcoded secrets):
  - Gemini flash      (Google)   via gateway/google-ai-studio
  - DeepSeek          (DeepSeek)  via gateway/deepseek/anthropic
  - Llama 3.3 70b     (Meta)      via gateway/workers-ai
  - NVIDIA Nemotron   (NVIDIA)    via gateway/nvidia (falls back to NVIDIA's hosted endpoint)
  - Granite 4.0       (IBM)       via gateway/workers-ai

Config (env vars, see ops-pack.env.example):
  CF_ACCOUNT_ID          Cloudflare account id (required)
  CF_AI_GATEWAY          AI Gateway name (default "atlas")
  CF_COUNCIL_PROJECT     default --project tag for telemetry (default "default")
  GEMINI_API_KEY, NVIDIA_API_KEY   optional, member disabled if absent
  openclaw.json          providers.anthropic-deepseek.apiKey, providers.cf-workers-ai.apiKey

Usage:
  council.py "DECISION with OPTION A / OPTION B" [--context FILE] [--json] [--project NAME]
  council.py --cf-trio DRAFT_FILE --purpose "what the draft is for"

Unanimous/majority -> CONSENSUS. Tie -> SPLIT_ESCALATE (human decides, all reasoning shown).
Telemetry: OPS_LOG_DIR/council-YYYY-MM-DD.jsonl (default ~/.openclaw/logs/)
"""
import os, sys, re, json, time, argparse, datetime, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

ACCOUNT = os.environ.get("CF_ACCOUNT_ID", "")
GATEWAY = os.environ.get("CF_AI_GATEWAY", "atlas")
DEFAULT_PROJECT = os.environ.get("CF_COUNCIL_PROJECT", "default")
BASE = f"https://gateway.ai.cloudflare.com/v1/{ACCOUNT}/{GATEWAY}"
LOGDIR = os.environ.get("OPS_LOG_DIR", os.path.expanduser("~/.openclaw/logs"))
OPENCLAW = os.path.expanduser("~/.openclaw/openclaw.json")


def _gemini_key():
    """env GEMINI_API_KEY > ~/.openclaw/gemini-key.txt. No hardcoded key;
    if neither is present the Gemini member is simply disabled and the council runs on the others."""
    v = os.environ.get("GEMINI_API_KEY")
    if v:
        return v.strip()
    p = os.path.expanduser("~/.openclaw/gemini-key.txt")
    if os.path.exists(p):
        k = open(p).read().strip()
        if k:
            return k
    return ""

def _nvidia_key():
    """env NVIDIA_API_KEY > ~/.openclaw/secrets/nvidia-api-key. Free key from build.nvidia.com.
    When absent, the NVIDIA NIM member is simply disabled and the council runs on the rest."""
    v = os.environ.get("NVIDIA_API_KEY")
    if v:
        return v.strip()
    p = os.path.expanduser("~/.openclaw/secrets/nvidia-api-key")
    if os.path.exists(p):
        k = open(p).read().strip()
        if k:
            return k
    return ""

def _load_keys():
    """Read provider keys from openclaw.json (canonical), fall back to env/key-file."""
    keys = {"gemini": _gemini_key(), "deepseek": "", "cf": "", "nvidia": _nvidia_key()}
    try:
        cfg = json.load(open(OPENCLAW))
        prov = cfg.get("models", {}).get("providers", {})
        keys["deepseek"] = prov.get("anthropic-deepseek", {}).get("apiKey", "") or os.environ.get("DEEPSEEK_API_KEY", "")
        keys["cf"] = prov.get("cf-workers-ai", {}).get("apiKey", "") or os.environ.get("CF_API_TOKEN", "")
    except Exception as e:
        print(f"[council] warn: could not read openclaw.json: {e}", file=sys.stderr)
        keys["deepseek"] = os.environ.get("DEEPSEEK_API_KEY", "")
        keys["cf"] = os.environ.get("CF_API_TOKEN", "")
    return keys

K = _load_keys()

MEMBERS = [
    {"name": "gemini-flash",    "vendor": "google",   "kind": "gemini",
     "model": "gemini-flash-latest",                  "enabled": bool(K["gemini"])},
    {"name": "deepseek",        "vendor": "deepseek",  "kind": "deepseek",
     "model": "deepseek-v4-flash",                     "enabled": bool(K["deepseek"])},
    {"name": "llama-3.3-70b",   "vendor": "meta",      "kind": "workers",
     "model": "@cf/meta/llama-3.3-70b-instruct-fp8-fast", "enabled": bool(K["cf"])},
    {"name": "nvidia-nemotron", "vendor": "nvidia",    "kind": "workers",
     "model": "@cf/nvidia/nemotron-3-120b-a12b",       "enabled": bool(K["cf"])},
    {"name": "granite-4.0",     "vendor": "ibm",       "kind": "workers",
     "model": "@cf/ibm-granite/granite-4.0-h-micro",   "enabled": bool(K["cf"])},
]

RUBRIC = (
    "You are ONE member of a multi-vendor adjudication COUNCIL resolving a build decision. "
    "Read the decision and options. Pick exactly one option label. "
    "Reply with STRICT JSON only, no markdown, no prose: "
    '{"choice":"<exact option label>","confidence":<0.0-1.0>,"reason":"<one sentence>"}'
)

def _meta(project, member):
    return json.dumps({"agent": "council", "operation": "council",
                       "project": project, "details": member})

def _post(url, headers, payload, timeout=70, retries=3):
    headers = {**headers, "User-Agent": "ops-pack-council/1.0"}
    data = json.dumps(payload).encode()
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 503, 529) and attempt < retries - 1:
                time.sleep(2.5 * (attempt + 1)); continue
            raise
    raise last

def ask_gemini(m, prompt, project):
    url = f"{BASE}/google-ai-studio/v1beta/models/{m['model']}:generateContent"
    h = {"Content-Type": "application/json", "x-goog-api-key": K["gemini"],
         "cf-aig-metadata": _meta(project, m["name"])}
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json", "maxOutputTokens": 800}}
    j = _post(url, h, body)
    return j["candidates"][0]["content"]["parts"][0]["text"]

def ask_deepseek(m, prompt, project):
    url = f"{BASE}/deepseek/anthropic/v1/messages"
    h = {"Content-Type": "application/json", "x-api-key": K["deepseek"],
         "anthropic-version": "2023-06-01", "cf-aig-metadata": _meta(project, m["name"])}
    # DeepSeek V4 MUST get thinking disabled or it emits only thinking blocks
    # (no content[type=text]) and the parse below fails.
    body = {"model": m["model"], "max_tokens": 800, "temperature": 0.2,
            "thinking": {"type": "disabled"},
            "messages": [{"role": "user", "content": prompt}]}
    j = _post(url, h, body)
    # Tolerate both anthropic-shape (content[].text) and openai-shape (choices[].message.content)
    if isinstance(j.get("content"), list):
        for blk in j["content"]:
            if isinstance(blk, dict) and blk.get("text"):
                return blk["text"]
    if j.get("choices"):
        return j["choices"][0]["message"]["content"]
    raise KeyError(f"unparseable deepseek shape: {list(j.keys())}")

def ask_workers(m, prompt, project):
    url = f"{BASE}/workers-ai/v1/chat/completions"
    h = {"Content-Type": "application/json", "Authorization": f"Bearer {K['cf']}",
         "cf-aig-metadata": _meta(project, m["name"])}
    body = {"model": m["model"], "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt}]}
    j = _post(url, h, body)
    return j["choices"][0]["message"]["content"]

def ask_nvidia(m, prompt, project):
    """NVIDIA NIM (build.nvidia.com). Routes through the Cloudflare AI Gateway first so the
    call is observable, falls back to NVIDIA's hosted endpoint if the gateway leg fails."""
    body = {"model": m["model"], "max_tokens": 800, "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt}]}
    attempts = [
        (f"{BASE}/nvidia/v1/chat/completions",
         {"Content-Type": "application/json", "Authorization": f"Bearer {K['nvidia']}",
          "cf-aig-metadata": _meta(project, m["name"])}),
        ("https://integrate.api.nvidia.com/v1/chat/completions",
         {"Content-Type": "application/json", "Authorization": f"Bearer {K['nvidia']}"}),
    ]
    last = None
    for url, h in attempts:
        try:
            j = _post(url, h, body)
            return j["choices"][0]["message"]["content"]
        except Exception as e:
            last = e
    raise last

DISPATCH = {"gemini": ask_gemini, "deepseek": ask_deepseek, "workers": ask_workers, "nvidia": ask_nvidia}

def _salvage(raw):
    import re
    ch = re.search(r'"choice"\s*:\s*"([^"]+)"', raw)
    cf = re.search(r'"confidence"\s*:\s*([0-9.]+)', raw)
    rs = re.search(r'"reason"\s*:\s*"([^"]*)', raw)
    return {"choice": ch.group(1) if ch else "PARSE_FAIL",
            "confidence": float(cf.group(1)) if cf else 0,
            "reason": (rs.group(1) if rs else raw[:120]) + " [salvaged]"}

def query_member(m, prompt, project):
    t0 = time.time()
    try:
        raw = DISPATCH[m["kind"]](m, prompt, project)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.strip("`").lstrip("json").strip()
        try:
            v = json.loads(raw)
        except json.JSONDecodeError:
            v = _salvage(raw)
        v.update({"member": m["name"], "vendor": m["vendor"], "ms": int((time.time()-t0)*1000), "ok": True})
        return v
    except Exception as e:
        return {"member": m["name"], "vendor": m["vendor"], "ok": False, "choice": "ERROR",
                "confidence": 0, "reason": f"{type(e).__name__}: {str(e)[:120]}", "ms": int((time.time()-t0)*1000)}

def convene(question, context="", project=DEFAULT_PROJECT):
    if not ACCOUNT:
        print("[council] error: CF_ACCOUNT_ID not set, see ops-pack.env.example", file=sys.stderr)
        sys.exit(2)
    prompt = f"{RUBRIC}\n\n=== DECISION ===\n{question}\n"
    if context:
        prompt += f"\n=== CONTEXT / CONSTRAINTS ===\n{context}\n"
    active = [m for m in MEMBERS if m["enabled"]]
    votes = []
    with ThreadPoolExecutor(max_workers=min(5, len(active) or 1)) as ex:
        futs = {ex.submit(query_member, m, prompt, project): m for m in active}
        for f in as_completed(futs):
            votes.append(f.result())

    import re as _re
    def norm(c):
        # "OPTION A" / "Option A." / "A" -> "A"; otherwise uppercased core token.
        s = _re.sub(r'(?i)\boption\b', '', str(c)).strip().strip('.:').strip()
        return s.upper() if s else str(c).upper()

    tally, vendors_for = {}, {}
    for v in votes:
        if v["ok"] and v["choice"] not in ("ERROR", "PARSE_FAIL"):
            nc = norm(v["choice"])
            v["choice_norm"] = nc
            tally[nc] = tally.get(nc, 0) + 1
            vendors_for.setdefault(nc, set()).add(v["vendor"])
    ranked = sorted(tally.items(), key=lambda kv: -kv[1])

    if not ranked:
        consensus, status = None, "NO_VALID_VOTES"
    elif len(ranked) == 1:
        consensus, status = ranked[0][0], "UNANIMOUS"
    elif ranked[0][1] > ranked[1][1]:
        consensus, status = ranked[0][0], "MAJORITY_WITH_DISSENT"
    else:
        consensus, status = None, "SPLIT_ESCALATE"

    result = {"ts": datetime.datetime.now().isoformat(timespec="seconds"),
              "project": project, "question": question[:200], "status": status,
              "consensus": consensus, "tally": tally,
              "vendors_per_choice": {k: sorted(v) for k, v in vendors_for.items()},
              "votes": votes, "members_active": len(active)}
    os.makedirs(LOGDIR, exist_ok=True)
    with open(os.path.join(LOGDIR, f"council-{datetime.date.today()}.jsonl"), "a") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")
    return result

# --- cf-trio: 3-model reasoning-model draft critique via CF Workers AI (OpenAI-compatible) ---
CF_TRIO_URL_TMPL = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1/chat/completions"
CF_TRIO_MODELS = [
    "@cf/deepseek-ai/deepseek-v4-pro-0813",
    "@cf/moonshotai/kimi-k2.6",
    "@cf/openai/gpt-oss-120b",
]

def _cf_trio_bearer():
    try:
        cfg = json.load(open(OPENCLAW))
        return cfg.get("models", {}).get("providers", {}).get("cf-workers-ai", {}).get("apiKey", "") or os.environ.get("CF_API_TOKEN", "")
    except Exception as e:
        print(f"[council] warn: could not read openclaw.json: {e}", file=sys.stderr)
        return os.environ.get("CF_API_TOKEN", "")

def _cf_trio_extract_json(raw):
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lstrip().lower().startswith("json"):
            raw = raw.lstrip()[4:]
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {"verdict": "ERROR", "top_issues": [], "one_line": f"unparseable output: {raw[:150]}"}
    try:
        v = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"verdict": "ERROR", "top_issues": [], "one_line": f"json parse failed: {raw[:150]}"}
    v.setdefault("verdict", "ERROR")
    v.setdefault("top_issues", [])
    v.setdefault("one_line", "")
    return v

def _cf_trio_query(model, prompt, bearer, url):
    t0 = time.time()
    h = {"Content-Type": "application/json", "Authorization": f"Bearer {bearer}"}
    # reasoning effort low: keeps the token budget for the JSON verdict instead of
    # letting the model burn it all on chain-of-thought and return empty content.
    body = {"model": model, "max_tokens": 2000, "temperature": 0.2,
            "messages": [{"role": "system", "content": "You are a cold reviewer. Return only one JSON object, no prose, no code fences."},
                         {"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "reasoning": {"effort": "low"}}
    try:
        j = _post(url, h, body)
        ms = int((time.time() - t0) * 1000)
        msg = j["choices"][0].get("message", {})
        content = msg.get("content") or msg.get("reasoning_content") or msg.get("reasoning") or ""
        v = _cf_trio_extract_json(content)
        v["latency_ms"] = ms
        v["neurons"] = j.get("usage", {}).get("neurons", 0)
        return model, v
    except Exception as e:
        return model, {"verdict": "ERROR", "top_issues": [],
                        "one_line": f"{type(e).__name__}: {str(e)[:120]}",
                        "latency_ms": int((time.time() - t0) * 1000), "neurons": 0}

def cf_trio(draft_path, purpose):
    if not ACCOUNT:
        print("[council] error: CF_ACCOUNT_ID not set, see ops-pack.env.example", file=sys.stderr)
        sys.exit(2)
    if not os.path.exists(draft_path):
        print(f"[council] error: draft file not found: {draft_path}", file=sys.stderr)
        sys.exit(3)
    draft = open(draft_path).read()
    bearer = _cf_trio_bearer()
    if not bearer:
        print("[council] error: no cf-workers-ai key in openclaw.json or CF_API_TOKEN", file=sys.stderr)
        sys.exit(3)
    url = CF_TRIO_URL_TMPL.format(account=ACCOUNT)
    prompt = (
        f"You are a cold reviewer. Draft purpose: {purpose or 'unspecified'}\n\n"
        f"=== DRAFT ===\n{draft}\n\n"
        "Find factual risks, tone problems, AI-tell vocabulary, missing facts, and anything "
        "that would embarrass the sender. Return JSON: "
        '{"verdict":"SEND|FIX|HOLD","top_issues":[max 3 strings],"one_line":"..."}'
    )
    results = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = [ex.submit(_cf_trio_query, m, prompt, bearer, url) for m in CF_TRIO_MODELS]
        for f in as_completed(futs):
            model, v = f.result()
            results[model] = v

    print(json.dumps(results, ensure_ascii=False, indent=2))

    verdicts = [v["verdict"] for v in results.values() if v["verdict"] in ("SEND", "FIX", "HOLD")]
    total_neurons = sum(v.get("neurons", 0) for v in results.values())
    os.makedirs(LOGDIR, exist_ok=True)
    logline = {"ts": datetime.datetime.now().isoformat(timespec="seconds"), "mode": "cf-trio",
               "models": list(results.keys()),
               "verdicts": {m: results[m]["verdict"] for m in results},
               "total_neurons": total_neurons}

    if len(verdicts) < 2:
        print("COUNCIL: ERROR")
        logline["council"] = "ERROR"
        with open(os.path.join(LOGDIR, f"council-cf-{datetime.date.today()}.jsonl"), "a") as f:
            f.write(json.dumps(logline, ensure_ascii=False) + "\n")
        sys.exit(3)

    council = "HOLD" if "HOLD" in verdicts else ("FIX" if "FIX" in verdicts else "SEND")
    print(f"COUNCIL: {council}")
    logline["council"] = council
    with open(os.path.join(LOGDIR, f"council-cf-{datetime.date.today()}.jsonl"), "a") as f:
        f.write(json.dumps(logline, ensure_ascii=False) + "\n")
    sys.exit({"SEND": 0, "FIX": 1, "HOLD": 2}[council])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="?", default="")
    ap.add_argument("--question-file"); ap.add_argument("--context")
    ap.add_argument("--project", default=DEFAULT_PROJECT); ap.add_argument("--json", action="store_true")
    ap.add_argument("--cf-trio", metavar="DRAFT_FILE",
                     help="critique a draft with 3 CF Workers AI reasoning models (deepseek-v4-pro, kimi-k2.6, gpt-oss-120b)")
    ap.add_argument("--purpose", default="", help="what the --cf-trio draft is for")
    a = ap.parse_args()
    if a.cf_trio:
        cf_trio(a.cf_trio, a.purpose)
        return
    q = a.question or (open(a.question_file).read() if a.question_file else "")
    if not q.strip():
        print('usage: council.py "DECISION with options" [--context FILE] [--project NAME]'); sys.exit(2)
    ctx = open(a.context).read() if a.context and os.path.exists(a.context) else (a.context or "")
    r = convene(q, ctx, a.project)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2)); return
    print(f"\n  COUNCIL VERDICT: {r['status']}")
    if r["consensus"]:
        vfc = r["vendors_per_choice"].get(r["consensus"], [])
        print(f"  >>> {r['consensus']}   (vendors: {', '.join(vfc)})")
    print(f"  tally: {r['tally']}   ({r['members_active']} members active)\n")
    for v in sorted(r["votes"], key=lambda x: x["vendor"]):
        mark = "OK" if v["ok"] else "XX"
        print(f"  [{mark}] {v['vendor']:<9} {v['member']:<14} {str(v['choice'])[:30]:<30} c={v.get('confidence',0)}  {v.get('reason','')[:70]}")
    print()

if __name__ == "__main__":
    main()
