import os
import requests
import html
import json
import time
import re

# הגדרות
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = "1106351250"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
SEEN_JOBS_FILE = "seen_jobs.txt"
COMPANIES_FILE = "companies.json"

def get_seen_jobs():
    if not os.path.exists(SEEN_JOBS_FILE): return set()
    with open(SEEN_JOBS_FILE, "r") as f: return set(f.read().splitlines())

def save_seen_jobs(job_ids):
    if not job_ids: return
    with open(SEEN_JOBS_FILE, "a") as f:
        for jid in job_ids: f.write(str(jid) + "\n")

def get_companies():
    with open(COMPANIES_FILE, "r") as f:
        return json.load(f)

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"❌ כשל בטלגרם: {e}")

def is_title_relevant(title):
    title_lower = title.lower()
    blacklist = ['senior', 'lead', 'manager', 'director', 'vp', 'marketing', 'sales', 'finance', 'hr', 'legal']
    if any(word in title_lower for word in blacklist): return False
    whitelist = ['student', 'intern', 'junior', 'software', 'developer', 'backend', 'full stack', 'engineer', 'automation', 'cyber']
    return any(word in title_lower for word in whitelist)

def is_experience_too_high(description):
    desc_lower = description.lower()
    patterns = [r'[2-9]\+?\s*years', r'[2-9]\s*-\s*[0-9]+\s*years', r'(at least|minimum)\s+[2-9]\s*years']
    for p in patterns:
        if re.search(p, desc_lower): return True
    return False

def scrape_greenhouse(board_token):
    jobs = []
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            for j in res.json().get('jobs', []):
                loc = j.get('location', {}).get('name', '').lower()
                if any(k in loc for k in ['israel', 'tel aviv', 'remote', 'herzliya', 'haifa']):
                    jobs.append({
                        'id': str(j['id']),
                        'title': j['title'],
                        'content': html.unescape(j.get('content', '')),
                        'url': j.get('absolute_url')
                    })
    except: pass
    return jobs

def scrape_comeet(company_id):
    jobs = []
    # ה-API הציבורי של Comeet
    url = f"https://www.comeet.co/careers-api/v1/company/{company_id}/positions?details=true"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            for j in res.json():
                # סינון לוקיישן בקומיט
                loc = j.get('location', {}).get('name', '').lower()
                if any(k in loc for k in ['israel', 'tel aviv', 'remote', 'herzliya', 'haifa']):
                    jobs.append({
                        'id': str(j['uid']),
                        'title': j['name'],
                        'content': html.unescape(j.get('description', '') + j.get('requirements', '')),
                        'url': j.get('url_active_page')
                    })
    except: pass
    return jobs

def check_jobs_batch(jobs_to_check):
    if not GROQ_API_KEY or not jobs_to_check: return []
    matched_ids = []
    chunk_size = 4
    for i in range(0, len(jobs_to_check), chunk_size):
        chunk = jobs_to_check[i:i + chunk_size]
        jobs_text = ""
        for j in chunk:
            jobs_text += f"ID: {j['id']}\nTitle: {j['title']}\nDescription: {j['content'][:3500]}\n---\n"
        
        prompt = f"Analyze these jobs. Return ONLY a JSON list of IDs for jobs that are TRULY entry-level, junior, or student positions. Reject if 2+ years experience required. Jobs:\n{jobs_text}\nResponse format: [\"id1\"]"
        
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0 
        }
        try:
            res = requests.post("https://api.groq.com/openai/v1/chat/completions", 
                                headers={"Authorization": f"Bearer {GROQ_API_KEY}"}, json=payload)
            if res.status_code == 200:
                content = res.json()['choices'][0]['message']['content']
                clean_res = content.replace('```json', '').replace('```', '').strip()
                matched_ids.extend(json.loads(clean_res))
        except: pass
        time.sleep(2)
    return matched_ids

def main():
    print("🚀 מתחיל סריקה רב-פלטפורמית (Greenhouse + Comeet)...")
    seen_jobs = get_seen_jobs()
    companies = get_companies()
    
    for name, info in companies.items():
        print(f"🔎 סורק את {name} ({info['platform']})...")
        raw_jobs = []
        if info['platform'] == 'greenhouse':
            raw_jobs = scrape_greenhouse(info['id'])
        elif info['platform'] == 'comeet':
            raw_jobs = scrape_comeet(info['id'])
            
        # --- השורה שנוסיף כדי לראות את הנתונים זורמים: ---
        print(f"   נמשכו {len(raw_jobs)} משרות גלובליות מהלוח.")
        # ------------------------------------------------
            
        relevant_for_ai = []
        for job in raw_jobs:
            if job['id'] not in seen_jobs and is_title_relevant(job['title']):
                if not is_experience_too_high(job['content']):
                    relevant_for_ai.append(job)
        
        if relevant_for_ai:
            print(f"  מעביר {len(relevant_for_ai)} משרות לניתוח AI...")
            matched_ids = check_jobs_batch(relevant_candidates := relevant_for_ai)
            for job in relevant_for_ai:
                if job['id'] in matched_ids:
                    print(f"  ✅ התאמה! {job['title']}")
                    msg = f"🔥 <b>משרה חדשה ב-{name}!</b>\n\nתפקיד: {job['title']}\n<a href='{job['url']}'>הגש מועמדות כאן</a>"
                    send_telegram_message(msg)
            save_seen_jobs([j['id'] for j in relevant_for_ai])
        
        time.sleep(5) # הפסקה בין חברות

    print("\n✅ סריקה הסתיימה בהצלחה.")

if __name__ == "__main__":
    main()