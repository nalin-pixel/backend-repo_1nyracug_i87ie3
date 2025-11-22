import os
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId

from database import db

app = FastAPI(title="AptLearn – 15-Day Interview Preparation Portal API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------
# Utility functions
# -----------------

def collection(name: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    return db[name]


def seed_data():
    """Seed modules, days and simple questions if not already present"""
    modules_col = collection("module")
    if modules_col.count_documents({}) > 0:
        return

    modules = [
        {"key": "aptitude", "title": "Aptitude", "order": 1},
        {"key": "technical", "title": "Technical", "order": 2},
        {"key": "hr", "title": "HR", "order": 3},
    ]
    modules_col.insert_many(modules)

    days_col = collection("day")
    questions_col = collection("question")

    # Create 15 days, 1-5 aptitude, 6-10 technical, 11-15 HR
    for d in range(1, 16):
        if d <= 5:
            mk = "aptitude"
            title = f"Aptitude Day {d}"
        elif d <= 10:
            mk = "technical"
            title = f"Technical Day {d-5}"
        else:
            mk = "hr"
            title = f"HR Day {d-10}"

        day_doc = {
            "day_number": d,
            "module_key": mk,
            "title": title,
            "video_url": "https://www.youtube.com/embed/dQw4w9WgXcQ",
            "notes": f"Concise notes for {title}. Key concepts, examples, and tips.",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        days_col.insert_one(day_doc)

        # Add 5 simple MCQs for each day
        qs = []
        for i in range(1, 6):
            prompt = f"Question {i} for Day {d}: Choose the correct option."
            options = ["Option A", "Option B", "Option C", "Option D"]
            answer_index = (i - 1) % 4
            qs.append({
                "day_number": d,
                "prompt": prompt,
                "options": options,
                "answer_index": answer_index,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            })
        questions_col.insert_many(qs)


@app.on_event("startup")
async def on_startup():
    try:
        if db is not None:
            seed_data()
    except Exception:
        pass


# -----------------
# Models
# -----------------

class UserIn(BaseModel):
    name: str
    email: str

class AttemptIn(BaseModel):
    user_id: str
    day_number: int
    answers: List[int]
    violations: int = 0


# -----------------
# Basic routes
# -----------------

@app.get("/")
def read_root():
    return {"message": "AptLearn API Running"}

@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    return response


# -----------------
# Portal Endpoints
# -----------------

@app.post("/users")
def create_or_get_user(user: UserIn):
    users = collection("user")
    existing = users.find_one({"email": user.email})
    if existing:
        return {"id": str(existing.get("_id")), "name": existing.get("name"), "email": existing.get("email")}
    doc = {
        "name": user.name,
        "email": user.email,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    res = users.insert_one(doc)
    # create progress
    collection("progress").insert_one({
        "user_id": str(res.inserted_id),
        "completed_days": [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })
    return {"id": str(res.inserted_id), "name": user.name, "email": user.email}


@app.get("/modules")
def get_modules():
    mods = list(collection("module").find({}, {"_id": 0}))
    return sorted(mods, key=lambda m: m.get("order", 0))


@app.get("/days")
def get_days(module_key: Optional[str] = None):
    filt: Dict[str, Any] = {}
    if module_key:
        filt["module_key"] = module_key
    days = list(collection("day").find(filt, {"_id": 0}))
    return sorted(days, key=lambda d: d.get("day_number", 0))


@app.get("/day/{day_number}")
def get_day(day_number: int):
    d = collection("day").find_one({"day_number": day_number}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Day not found")
    return d


@app.get("/quiz/{day_number}")
def get_quiz(day_number: int):
    qs = list(collection("question").find({"day_number": day_number}, {"_id": 0}))
    if not qs:
        raise HTTPException(status_code=404, detail="Quiz not found for this day")
    # do not reveal answers
    for q in qs:
        q.pop("answer_index", None)
    return {"day_number": day_number, "questions": qs}


@app.post("/attempt")
def submit_attempt(payload: AttemptIn):
    # Fetch questions to score
    qdocs = list(collection("question").find({"day_number": payload.day_number}))
    if not qdocs:
        raise HTTPException(status_code=400, detail="No questions for this day")

    total = len(qdocs)
    score = 0
    for i, q in enumerate(qdocs):
        if i < len(payload.answers) and payload.answers[i] == q.get("answer_index"):
            score += 1

    flagged = payload.violations > 0

    attempts = collection("attempt")
    doc = {
        "user_id": payload.user_id,
        "day_number": payload.day_number,
        "answers": payload.answers,
        "score": score,
        "total": total,
        "violations": payload.violations,
        "flagged": flagged,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    attempts.insert_one(doc)

    # Passing criteria: at least 60% and no violations
    passed = (score / total) >= 0.6 and not flagged

    # Update progress if passed
    if passed:
        prog_col = collection("progress")
        prog = prog_col.find_one({"user_id": payload.user_id})
        if prog:
            completed_days = prog.get("completed_days", [])
            if payload.day_number not in completed_days:
                completed_days.append(payload.day_number)
                prog_col.update_one(
                    {"_id": prog["_id"]},
                    {"$set": {"completed_days": completed_days, "updated_at": datetime.now(timezone.utc)}}
                )

    # Check progress to possibly create certificate
    prog = collection("progress").find_one({"user_id": payload.user_id})
    if prog and len(prog.get("completed_days", [])) >= 15:
        cert_col = collection("certificate")
        existing = cert_col.find_one({"user_id": payload.user_id})
        if not existing:
            name = "Participant"
            try:
                user_doc = collection("user").find_one({"_id": ObjectId(payload.user_id)})
                if user_doc and user_doc.get("name"):
                    name = user_doc["name"]
            except Exception:
                user_doc = collection("user").find_one({"email": {"$exists": True}})
                if user_doc and user_doc.get("name"):
                    name = user_doc["name"]

            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            svg = generate_certificate_svg(name=name, date_str=now)
            cert_col.insert_one({
                "user_id": payload.user_id,
                "name": name,
                "issued_at": now,
                "svg": svg,
                "created_at": datetime.now(timezone.utc),
            })

    return {"score": score, "total": total, "passed": passed, "flagged": flagged, "violations": payload.violations}


@app.get("/progress/{user_id}")
def get_progress(user_id: str):
    prog = collection("progress").find_one({"user_id": user_id}, {"_id": 0})
    if not prog:
        return {"user_id": user_id, "completed_days": []}
    return prog


@app.get("/certificate/{user_id}")
def get_certificate(user_id: str):
    cert = collection("certificate").find_one({"user_id": user_id}, {"_id": 0})
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not issued yet")
    return cert


# -----------------
# Certificate SVG
# -----------------

def generate_certificate_svg(name: str, date_str: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="850">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#1e3a8a"/>
      <stop offset="100%" stop-color="#0ea5e9"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" fill="#0b1220"/>
  <rect x="40" y="40" width="1120" height="770" rx="24" fill="none" stroke="url(#g)" stroke-width="6"/>
  <text x="600" y="160" text-anchor="middle" fill="#e2e8f0" font-size="42" font-family="Inter, sans-serif">Certificate of Completion</text>
  <text x="600" y="300" text-anchor="middle" fill="#93c5fd" font-size="28" font-family="Inter, sans-serif">This certifies that</text>
  <text x="600" y="380" text-anchor="middle" fill="#f8fafc" font-size="56" font-weight="700" font-family="Inter, sans-serif">{name}</text>
  <text x="600" y="460" text-anchor="middle" fill="#cbd5e1" font-size="24" font-family="Inter, sans-serif">has successfully completed the</text>
  <text x="600" y="505" text-anchor="middle" fill="#cbd5e1" font-size="28" font-family="Inter, sans-serif">AptLearn – 15-Day Interview Preparation Challenge</text>
  <text x="600" y="590" text-anchor="middle" fill="#93c5fd" font-size="20" font-family="Inter, sans-serif">Issued on {date_str}</text>
  <circle cx="600" cy="690" r="36" fill="url(#g)"/>
  <text x="600" y="700" text-anchor="middle" fill="#0b1220" font-size="24" font-weight="700" font-family="Inter, sans-serif">AL</text>
</svg>'''


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
