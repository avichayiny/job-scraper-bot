import os
import requests
import html
import json

# הגדרות
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = "1106351250"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
SEEN_JOBS_FILE = "seen_jobs.txt"

def get_seen_jobs():
    if not os.path.exists(SEEN_JOBS_FILE): return set()
    with open(SEEN_JOBS_FILE, "r") as f: return set(f.read().splitlines())

def save_seen_jobs(job_ids):
    if not job_ids: return
    with open(SEEN_JOBS_FILE, "a") as f:
        for jid in job_ids: f.write(str(jid) + "\n")

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=payload)
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

def is_location_israel(location_obj):
    """מסנן משרות שאינן בישראל (או Remote) כדי לחסוך טוקנים מול ה-LLM"""
    if not location_obj: return False
    loc_str = location_obj.get('name', '').lower()
    israel_keywords = ['israel', 'tel aviv', 'herzliya', 'haifa', 'jerusalem', 'remote']
    return any(keyword in loc_str for keyword in israel_keywords)

def check_jobs_batch(jobs_to_check):
    """שולח קבוצת משרות לניתוח נוקשה ב-Groq API עם טקסט ארוך יותר"""
    if not GROQ_API_KEY or not jobs_to_check: return []
    
    jobs_text = ""
    for j in jobs_to_check:
        # הגדלנו משמעותית ל-4000 תווים כדי שדרישות הניסיון ("What you have") ייכנסו בוודאות
        jobs_text += f"ID: {j['id']}\nTitle: {j['title']}\nDescription: {j['content'][:4000]}\n---\n"

    # Prompt שמכריח את המודל להיות "צייד" של שנות ניסיון
    prompt = f"""
    You are a strict technical recruiter. Analyze these job postings for a fresh Computer Science graduate or student.

    CRITICAL RULES:
    1. Scan the text specifically for sections like "Requirements", "What you have", or "Experience".
    2. Look for the word "years". If the job requires 2 or more years of experience (e.g., "3+ years", "3-5 years"), you MUST REJECT IT immediately.
    3. Only approve jobs that are clearly entry-level, junior, student positions, or require 0-1 years of experience.

    Return ONLY a JSON list of IDs for the APPROVED jobs. If none are approved, return [].
    Do not return any conversational text.
    Example: ["123", "456"]
    
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
            return json.loads(clean_res)
        else:
            print(f"❌ שגיאת Groq: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        print(f"LLM Error: {e}")
        return []

def main():
    print("🚀 מתחיל סריקה חכמה (עם סינון מיקום מוקדם)...")
    seen_jobs = get_seen_jobs()
    relevant_candidates = []
    
    # סריקת AppsFlyer
    response = requests.get("https://boards-api.greenhouse.io/v1/boards/appsflyer/jobs?content=true")
    if response.status_code == 200:
        all_jobs = response.json().get('jobs', [])
        for job in all_jobs:
            jid = str(job['id'])
            # פה הוספנו את החומה: רק משרות בישראל ועם טייטל רלוונטי עוברות הלאה
            if jid not in seen_jobs and is_title_relevant(job['title']) and is_location_israel(job.get('location')):
                relevant_candidates.append({
                    'id': jid,
                    'title': job['title'],
                    'content': html.unescape(job.get('content', '')),
                    'url': job.get('absolute_url')
                })

    if not relevant_candidates:
        print("לא נמצאו משרות חדשות פוטנציאליות.")
        return

    # שליחה ל-Groq
    print(f"בודק {len(relevant_candidates)} משרות מול Groq...")
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