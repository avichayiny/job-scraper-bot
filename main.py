import os
import requests
import html
import json

# הגדרות
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = "1106351250" # השארנו את ה-ID שעובד
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
SEEN_JOBS_FILE = "seen_jobs.txt"
    

def get_seen_jobs():
    if not os.path.exists(SEEN_JOBS_FILE): return set()
    with open(SEEN_JOBS_FILE, "r") as f: return set(f.read().splitlines())

def save_seen_jobs(job_ids):
    with open(SEEN_JOBS_FILE, "a") as f:
        for jid in job_ids: f.write(str(jid) + "\n")

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=payload)
        # השורה הזו קריטית - היא תדפיס לנו אם טלגרם החזיר שגיאה
        if response.status_code != 200:
            print(f"❌ שגיאת טלגרם: {response.status_code} - {response.text}")
        else:
            print("✅ ההודעה נשלחה בהצלחה לטלגרם!")
    except Exception as e:
        print(f"❌ כשל בחיבור לטלגרם: {e}")

def is_title_relevant(title):
    title_lower = title.lower()
    blacklist = ['senior', 'lead', 'manager', 'director', 'vp', 'marketing', 'sales', 'finance', 'hr', 'legal']
    if any(word in title_lower for word in blacklist): return False
    whitelist = ['student', 'intern', 'junior', 'software', 'developer', 'backend', 'full stack', 'engineer']
    return any(word in title_lower for word in whitelist)

def check_jobs_batch(jobs_to_check):
    """שולח קבוצת משרות לניתוח ב-Groq API (Llama 3)"""
    if not GROQ_API_KEY or not jobs_to_check: return []
    
    jobs_text = ""
    for j in jobs_to_check:
        jobs_text += f"ID: {j['id']}\nTitle: {j['title']}\nDescription: {j['content'][:1500]}\n---\n"

    prompt = f"""
    You are a technical recruiter. Analyze these job postings for a Computer Science student in their final stages of study.
    Return ONLY a JSON list of IDs that are entry-level, junior, or student positions suitable for a fresh graduate.
    Exclude roles requiring 2+ years of experience.
    
    Jobs:
    {jobs_text}
    
    Response format: ["id1", "id2"]
    """
    
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama3-8b-8192",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1 # טמפרטורה נמוכה לתשובות מדויקות ויציבות
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            content = response.json()['choices'][0]['message']['content']
            clean_res = content.replace('```json', '').replace('```', '').strip()
            return json.loads(clean_res)
        else:
            print(f"❌ שגיאת Groq: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        print(f"LLM Error: {e}")
        return []
    
def main():
    print("🚀 מתחיל סריקה חכמה...")
    seen_jobs = get_seen_jobs()
    relevant_candidates = []
    
    # סריקת AppsFlyer
    response = requests.get("https://boards-api.greenhouse.io/v1/boards/appsflyer/jobs?content=true")
    if response.status_code == 200:
        all_jobs = response.json().get('jobs', [])
        for job in all_jobs:
            jid = str(job['id'])
            if jid not in seen_jobs and is_title_relevant(job['title']):
                relevant_candidates.append({
                    'id': jid,
                    'title': job['title'],
                    'content': html.unescape(job.get('content', '')),
                    'url': job.get('absolute_url')
                })

    if not relevant_candidates:
        print("לא נמצאו משרות חדשות פוטנציאליות.")
        return

    # שליחה לג'מיני בבת אחת (Batch)
    print(f"בודק {len(relevant_candidates)} משרות מול ג'מיני...")
    matched_ids = check_jobs_batch(relevant_candidates)
    
    for job in relevant_candidates:
        if job['id'] in matched_ids:
            print(f"✅ נמצאה התאמה: {job['title']}")
            msg = f"🔥 <b>משרה חדשה נמצאה!</b>\n\nחברה: AppsFlyer\nתפקיד: {job['title']}\n<a href='{job['url']}'>הגש מועמדות כאן</a>"
            send_telegram_message(msg)
    
    # שמירת כל המשרות שבדקנו כדי לא לחזור עליהן
    save_seen_jobs([j['id'] for j in relevant_candidates])
    print("✅ סריקה הסתיימה.")

if __name__ == "__main__":
    main()