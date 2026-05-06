import os
import requests
import google.generativeai as genai

# --- הגדרות סביבה ---
# אם אתה מריץ מקומית, פשוט תחליף את ה-os.getenv במחרוזת של הטוקנים שלך לבדיקה
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "הטוקן_שלך_כאן")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "האיידי_שלך_כאן")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "המפתח_של_ג'מיני_כאן")
CHAT_ID = '1106351250'


SEEN_JOBS_FILE = "seen_jobs.txt"

# הגדרת המודל של ג'מיני
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')

def get_seen_jobs():
    """קורא את קובץ הזיכרון כדי לא לשלוח כפילויות"""
    if not os.path.exists(SEEN_JOBS_FILE):
        return set()
    with open(SEEN_JOBS_FILE, "r") as f:
        return set(f.read().splitlines())

def save_seen_job(job_id):
    """שומר משרה חדשה לקובץ"""
    with open(SEEN_JOBS_FILE, "a") as f:
        f.write(str(job_id) + "\n")

def send_telegram_message(text):
    """שולח את ההתראה אליך לטלגרם"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Failed to send telegram: {e}")

def is_title_relevant(title):
    """השומר שלנו: סינון מהיר לפי כותרת בלבד"""
    title_lower = title.lower()
    
    # פוסל בכירים ומחלקות לא קשורות
    blacklist = [
        'senior', 'lead', 'manager', 'director', 'vp', 'principal',
        'marketing', 'sales', 'finance', 'hr', 'legal', 'support'
    ]
    if any(word in title_lower for word in blacklist):
        return False
        
    # מוודא שיש משהו רלוונטי
    whitelist = ['student', 'intern', 'junior', 'software', 'developer', 'backend', 'full stack']
    if any(word in title_lower for word in whitelist):
        return True
        
    return False

def check_with_llm(job_title, job_description):
    """המוח: מעביר את המשרה לג'מיני להחלטה סופית"""
    prompt = f"""
    You are an expert technical recruiter. 
    I am a Computer Science student (graduating in 1 semester) looking for a student position or a junior role.
    My tech stack includes Java, Python, React, Node.js, and C++.
    
    Analyze this job posting:
    Title: {job_title}
    Description: {job_description}
    
    Does this job match a student/junior level AND align with software engineering or my tech stack? 
    Ensure it DOES NOT require years of full-time experience or a lot of study time left (3 semesters and above).
    Respond with ONLY one word: "YES" if it's a match, or "NO" if it's not.
    """
    try:
        response = model.generate_content(prompt)
        return "YES" in response.text.upper()
    except Exception as e:
        print(f"LLM Error: {e}")
        return False

def scrape_greenhouse(board_token):
    """מושך משרות מה-API הציבורי של גרינהאוס"""
    print(f"🔎 סורק את {board_token}...")
    # הפרמטר content=true מביא לנו גם את תיאור המשרה המלא בלי עוד בקשה
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    response = requests.get(url)
    
    if response.status_code != 200:
        print(f"Failed to fetch {board_token}")
        return []
        
    return response.json().get('jobs', [])

def main():
    seen_jobs = get_seen_jobs()
    
    # רשימת חברות לבדיקה (אפשר להוסיף עוד המון)
    companies = ['appsflyer', 'cyberark'] 
    
    for company in companies:
        jobs = scrape_greenhouse(company)
        
        for job in jobs:
            job_id = str(job.get('id'))
            
            # 1. האם כבר ראינו אותה?
            if job_id in seen_jobs:
                continue
                
            title = job.get('title', '')
            
            # 2. סינון מהיר (השומר)
            if not is_title_relevant(title):
                # שומרים אותה בכל זאת כדי לא לבדוק אותה שוב מחר
                save_seen_job(job_id)
                continue
                
            # 3. סינון חכם (המוח)
            import html # לנקות את ה-HTML מהתיאור
            description = html.unescape(job.get('content', ''))
            
            print(f"🤖 שולח לג'מיני לבדיקה: {title}")
            is_match = check_with_llm(title, description)
            
            if is_match:
                print(f"✅ נמצאה משרה מתאימה! {title}")
                msg = f"🔥 <b>משרה מתאימה נמצאה!</b>\n\nחברה: {company.capitalize()}\nתפקיד: {title}\n<a href='{job.get('absolute_url')}'>לחץ כאן להגשה</a>"
                send_telegram_message(msg)
            else:
                print(f"❌ נפסל על ידי ג'מיני: {title}")
            
            # שומרים בזיכרון בכל מקרה, כדי לא לשלוח לג'מיני פעמיים
            save_seen_job(job_id)

if __name__ == "__main__":
    main()