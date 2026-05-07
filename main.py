import os
import requests
import html
import json
import time
import re # הוספנו את ספריית הביטויים הרגולריים

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
    if not os.path.exists(COMPANIES_FILE):
        return {"AppsFlyer": "appsflyer"}
    with open(COMPANIES_FILE, "r") as f:
        return json.load(f)

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"❌ כשל בחיבור לטלגרם: {e}")

def is_title_relevant(title):
    title_lower = title.lower()
    blacklist = ['senior', 'lead', 'manager', 'director', 'vp', 'marketing', 'sales', 'finance', 'hr', 'legal']
    if any(word in title_lower for word in blacklist): return False
    whitelist = ['student', 'intern', 'junior', 'software', 'developer', 'backend', 'full stack', 'engineer', 'automation', 'test automation', 'cyber']
    return any(word in title_lower for word in whitelist)

def is_location_israel(location_obj):
    if not location_obj: return False
    loc_str = location_obj.get('name', '').lower()
    israel_keywords = ['israel', 'tel aviv', 'herzliya', 'haifa', 'jerusalem', 'remote', 'petah tikva', 'ramat gan']
    return any(keyword in loc_str for keyword in israel_keywords)

def is_experience_too_high(description):
    """סינון חומרה מבוסס פייתון: מעיף משרות עם דרישות ניסיון לפני ה-AI"""
    desc_lower = description.lower()
    # תבניות שמזהות 2 ומעלה שנות ניסיון (למשל "3+ years", "2-4 years", "minimum 3 years")
    patterns = [
        r'[2-9]\+?\s*years', 
        r'[2-9]\s*-\s*[0-9]+\s*years',
        r'(at least|minimum)\s+[2-9]\s*years'
    ]
    for p in patterns:
        if re.search(p, desc_lower):
            return True
    return False

def check_jobs_batch(jobs_to_check):
    if not GROQ_API_KEY or not jobs_to_check: return []
    
    # חילוק לקבוצות של 4 כדי לא להקריס את השרת (Chunking)
    matched_ids = []
    chunk_size = 4
    
    for i in range(0, len(jobs_to_check), chunk_size):
        chunk = jobs_to_check[i:i + chunk_size]
        jobs_text = ""
        for j in chunk:
            jobs_text += f"ID: {j['id']}\nTitle: {j['title']}\nDescription: {j['content'][:3500]}\n---\n"

        prompt = f"""
        You are a technical recruiter. The following jobs have already passed basic filters.
        Analyze them and return ONLY a JSON list of IDs for jobs that are TRULY entry-level, junior, or student positions.
        If a job secretly implies senior responsibilities or requires more than 1 year of experience, REJECT IT.
        Return ONLY the JSON list.
        Example: ["123"]
        
        Jobs:
        {jobs_text}
        """
        
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0 
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                content = response.json()['choices'][0]['message']['content']
                clean_res = content.replace('```json', '').replace('```', '').strip()
                matched_ids.extend(json.loads(clean_res))
            else:
                print(f"❌ שגיאת Groq: {response.status_code}")
        except Exception as e:
            print(f"LLM Error: {e}")
            
        time.sleep(2) # השהייה קטנה בין Chunks
        
    return matched_ids

def main():
    print("🚀 מתחיל סריקה רוחבית עם הגנות נגד קריסות (Chunking & Regex)...")
    seen_jobs = get_seen_jobs()
    companies_dict = get_companies()
    
    for display_name, board_token in companies_dict.items():
        print(f"\n🔎 סורק את: {display_name}")
        relevant_candidates = []
        
        try:
            response = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true")
            if response.status_code == 200:
                all_jobs = response.json().get('jobs', [])
                for job in all_jobs:
                    jid = str(job['id'])
                    
                    # החומה המשולשת: מיקום + כותרת + סינון ניסיון בפייתון!
                    if jid not in seen_jobs and is_title_relevant(job['title']) and is_location_israel(job.get('location')):
                        content_text = html.unescape(job.get('content', ''))
                        
                        if not is_experience_too_high(content_text):
                            relevant_candidates.append({
                                'id': jid,
                                'title': job['title'],
                                'content': content_text,
                                'url': job.get('absolute_url'),
                                'company_name': display_name
                            })
                        else:
                            print(f"   נפסל מראש (דרישת ניסיון גבוהה): {job['title']}")
            else:
                print(f"⚠️ לא נמצא לוח. נדלג.")
                continue
                
        except Exception as e:
            continue

        if not relevant_candidates:
            print(f"לא נשארו משרות לבדיקת AI ב-{display_name}.")
            continue

        print(f"מעביר {len(relevant_candidates)} משרות לגרוק...")
        matched_ids = check_jobs_batch(relevant_candidates)
        
        for job in relevant_candidates:
            if job['id'] in matched_ids:
                print(f"✅ התאמה סופית: {job['title']}")
                msg = f"🔥 <b>משרה חדשה נמצאה!</b>\n\nחברה: {job['company_name']}\nתפקיד: {job['title']}\n<a href='{job['url']}'>הגש מועמדות כאן</a>"
                send_telegram_message(msg)
        
        save_seen_jobs([j['id'] for j in relevant_candidates])
        time.sleep(5)

    print("\n✅ סריקה הסתיימה.")

if __name__ == "__main__":
    main()