import os
import requests
import google.generativeai as genai
import html
import time  # הוספנו את ספריית הזמן

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

SEEN_JOBS_FILE = "seen_jobs.txt"

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-pro')

def get_seen_jobs():
    if not os.path.exists(SEEN_JOBS_FILE):
        return set()
    with open(SEEN_JOBS_FILE, "r") as f:
        return set(f.read().splitlines())

def save_seen_job(job_id):
    with open(SEEN_JOBS_FILE, "a") as f:
        f.write(str(job_id) + "\n")

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    requests.post(url, json=payload)

def is_title_relevant(title):
    title_lower = title.lower()
    blacklist = ['senior', 'lead', 'manager', 'director', 'vp', 'marketing', 'sales', 'finance', 'hr', 'legal']
    if any(word in title_lower for word in blacklist):
        return False
    whitelist = ['student', 'intern', 'junior', 'software', 'developer', 'backend', 'full stack', 'engineer']
    return any(word in title_lower for word in whitelist)

def check_with_llm(job_title, job_description):
    if not GEMINI_API_KEY:
        return True 
        
    prompt = f"""
    You are an expert technical recruiter. I am a Computer Science student.
    Does this job match a student/junior level in software engineering?
    Ensure it DOES NOT require years of full-time experience.
    Title: {job_title}
    Description: {job_description}
    Respond with ONLY one word: "YES" or "NO".
    """
    try:
        response = model.generate_content(prompt)
        return "YES" in response.text.upper()
    except Exception as e:
        print(f"LLM Error: {e}")
        return False

def main():
    print("🚀 מתחיל סריקה...")
    # הודעת פינג לוודא שהטלגרם מחובר ועובד
    send_telegram_message("בדיקת מערכת: הסורק התחיל לרוץ! 🤖")
    
    seen_jobs = get_seen_jobs()
    
    # השארנו כרגע רק את החברה שעבדה לנו
    companies = ['appsflyer']
    
    for company in companies:
        print(f"🔎 סורק את {company}...")
        response = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true")
        if response.status_code != 200:
            print(f"Failed to fetch {company}")
            continue
            
        jobs = response.json().get('jobs', [])
        
        for job in jobs:
            job_id = str(job.get('id'))
            if job_id in seen_jobs:
                continue
                
            title = job.get('title', '')
            if not is_title_relevant(title):
                save_seen_job(job_id)
                continue
                
            description = html.unescape(job.get('content', ''))
            
            print(f"🤖 שולח לג'מיני לבדיקה: {title}")
            
            is_match = check_with_llm(title, description)
            
            if is_match:
                print(f"✅ משרה מתאימה: {title}")
                msg = f"🔥 <b>משרה חדשה!</b>\n\nחברה: {company}\nתפקיד: {title}\n<a href='{job.get('absolute_url')}'>לחץ להגשה</a>"
                send_telegram_message(msg)
            else:
                print(f"❌ נפסל על ידי ג'מיני: {title}")
                
            save_seen_job(job_id)
            
            # ההשהיה הקריטית! מחכים 5 שניות כדי לא לעצבן את ג'מיני
            print("ממתין 5 שניות לפני המשרה הבאה...")
            time.sleep(5)
            
    print("✅ סריקה הסתיימה בהצלחה.")

if __name__ == "__main__":
    main()