#!/usr/bin/env python3
"""
Seed sample dev data:
  - 2 agencies
  - 4 consultants (2 per agency)
  - 10 students
  - 5 universities + 15 programs
  - 50 applications spread across statuses

Usage:
  python scripts/seed_sample_data.py

Note: This script creates Supabase Auth users for students and consultants
using the admin API (service role key required).
"""
import asyncio
import random
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.client import get_client
from app.models.application import STATUS_TRANSITIONS

# ─── Sample data ──────────────────────────────────────────────────────────────

AGENCIES = [
    {"name": "EduPath Bangladesh", "license_no": "BD-EDU-2021-001", "address": "Gulshan-2, Dhaka"},
    {"name": "GlobalVisa Consultants", "license_no": "BD-EDU-2019-042", "address": "Dhanmondi, Dhaka"},
]

CONSULTANTS_DATA = [
    {"full_name": "Rahim Chowdhury",   "role": "admin", "agency_idx": 0},
    {"full_name": "Fatima Begum",      "role": "staff", "agency_idx": 0},
    {"full_name": "Karim Ahmed",       "role": "admin", "agency_idx": 1},
    {"full_name": "Nusrat Islam",      "role": "staff", "agency_idx": 1},
]

STUDENT_NAMES = [
    "Arif Hossain",   "Sumaiya Khan",   "Tanvir Rahman",  "Mitu Akter",
    "Sabbir Hasan",   "Tania Sultana",  "Mahfuz Ali",     "Rima Parvin",
    "Imran Uddin",    "Sadia Noor",
]

UNIVERSITIES_SEED = [
    {
        "name": "University of Toronto",
        "country": "CA", "city": "Toronto",
        "ranking_qs": 25,
        "tuition_usd_per_year": 32000,
        "acceptance_rate_overall": 43.0,
        "acceptance_rate_bd": 35.0,
        "min_ielts": 6.5, "min_gpa_percentage": 65,
        "scholarships_available": True, "max_scholarship_pct": 50,
        "website": "https://utoronto.ca",
        "data_source": "manual",
    },
    {
        "name": "University of British Columbia",
        "country": "CA", "city": "Vancouver",
        "ranking_qs": 34,
        "tuition_usd_per_year": 28000,
        "acceptance_rate_overall": 52.0,
        "acceptance_rate_bd": 42.0,
        "min_ielts": 6.5, "min_gpa_percentage": 60,
        "scholarships_available": True, "max_scholarship_pct": 40,
        "website": "https://ubc.ca",
        "data_source": "manual",
    },
    {
        "name": "University of Manchester",
        "country": "GB", "city": "Manchester",
        "ranking_qs": 32,
        "tuition_usd_per_year": 25000,
        "acceptance_rate_overall": 55.0,
        "acceptance_rate_bd": 48.0,
        "min_ielts": 6.5, "min_gpa_percentage": 55,
        "scholarships_available": True, "max_scholarship_pct": 30,
        "website": "https://manchester.ac.uk",
        "data_source": "manual",
    },
    {
        "name": "Monash University",
        "country": "AU", "city": "Melbourne",
        "ranking_qs": 42,
        "tuition_usd_per_year": 23000,
        "acceptance_rate_overall": 60.0,
        "acceptance_rate_bd": 55.0,
        "min_ielts": 6.0, "min_gpa_percentage": 55,
        "scholarships_available": True, "max_scholarship_pct": 35,
        "website": "https://monash.edu",
        "data_source": "manual",
    },
    {
        "name": "TU Munich",
        "country": "DE", "city": "Munich",
        "ranking_qs": 37,
        "tuition_usd_per_year": 2000,   # Germany public tuition
        "acceptance_rate_overall": 35.0,
        "acceptance_rate_bd": 28.0,
        "min_ielts": 6.0, "min_gpa_percentage": 70,
        "scholarships_available": True, "max_scholarship_pct": 100,
        "website": "https://tum.de",
        "data_source": "manual",
    },
]

PROGRAM_TEMPLATES = [
    {"name": "MSc Computer Science",     "degree_level": "master", "field": "cs",          "duration_years": 1.5, "intake_months": [9, 1]},
    {"name": "MSc Data Science",         "degree_level": "master", "field": "cs",          "duration_years": 1.0, "intake_months": [9]},
    {"name": "MBA",                      "degree_level": "master", "field": "business",    "duration_years": 2.0, "intake_months": [9, 1]},
    {"name": "MEng Electrical Engineering", "degree_level": "master", "field": "engineering", "duration_years": 1.5, "intake_months": [9]},
    {"name": "BSc Computer Science",     "degree_level": "bachelor", "field": "cs",         "duration_years": 4.0, "intake_months": [9]},
    {"name": "BEng Mechanical Engineering", "degree_level": "bachelor", "field": "engineering", "duration_years": 4.0, "intake_months": [9]},
]

ALL_STATUSES = list(STATUS_TRANSITIONS.keys())


def random_student_row(user_id: str, name: str) -> dict:
    return {
        "user_id": user_id,
        "full_name": name,
        "phone": f"880171{random.randint(1000000, 9999999)}",
        "academic_history": {
            "ssc_gpa": round(random.uniform(3.5, 5.0), 2),
            "hsc_gpa": round(random.uniform(3.5, 5.0), 2),
            "bachelor_cgpa": round(random.uniform(2.8, 4.0), 2),
            "bachelor_subject": random.choice(["CSE", "EEE", "BBA", "Civil Eng", "Physics"]),
            "gpa_percentage": random.randint(55, 85),
        },
        "test_scores": {
            "ielts": round(random.uniform(6.0, 8.0), 1),
            "toefl": random.randint(80, 110),
        },
        "budget_usd_per_year": random.choice([10000, 15000, 20000, 25000, 30000, 35000]),
        "preferred_countries": random.sample(["CA", "GB", "AU", "DE", "US"], k=random.randint(2, 4)),
        "preferred_degree": random.choice(["master", "bachelor"]),
        "preferred_fields": random.sample(["cs", "engineering", "business", "health"], k=random.randint(1, 3)),
    }


async def seed():
    client = await get_client()

    print("Seeding agencies...")
    agency_ids = []
    for ag in AGENCIES:
        res = await client.table("agencies").insert(ag).execute()
        agency_ids.append(res.data[0]["id"])
        print(f"  Agency: {ag['name']} → {agency_ids[-1]}")

    print("\nSeeding consultants (creating auth users)...")
    consultant_ids = []
    for c in CONSULTANTS_DATA:
        email = f"{c['full_name'].lower().replace(' ', '.')}@seed.test"
        # Create Supabase Auth user
        auth_res = await client.auth.admin.create_user({
            "email":            email,
            "password":         "Seed@12345",
            "email_confirm":    True,
            "app_metadata":     {"role": "consultant", "agency_id": agency_ids[c["agency_idx"]]},
        })
        user_id = auth_res.user.id
        row = {
            "user_id":   user_id,
            "agency_id": agency_ids[c["agency_idx"]],
            "role":      c["role"],
            "full_name": c["full_name"],
        }
        res = await client.table("consultants").insert(row).execute()
        consultant_ids.append(res.data[0]["id"])
        print(f"  Consultant: {c['full_name']} → {consultant_ids[-1]}")

    print("\nSeeding universities + programs...")
    uni_ids = []
    program_ids = []
    for uni in UNIVERSITIES_SEED:
        res = await client.table("universities").insert(uni).execute()
        uid = res.data[0]["id"]
        uni_ids.append(uid)

        # Add 3 programs per university
        for pt in random.sample(PROGRAM_TEMPLATES, 3):
            p_row = {
                "university_id":        uid,
                "name":                 pt["name"],
                "degree_level":         pt["degree_level"],
                "field":                pt["field"],
                "duration_years":       pt["duration_years"],
                "intake_months":        pt["intake_months"],
                "tuition_usd_per_year": uni["tuition_usd_per_year"] + random.randint(-3000, 3000),
                "min_requirements": {
                    "ielts":    uni.get("min_ielts", 6.0),
                    "gpa_pct":  uni.get("min_gpa_percentage", 55),
                },
                "application_deadline": date(2025, 12, 1).isoformat(),
            }
            p_res = await client.table("programs").insert(p_row).execute()
            program_ids.append(p_res.data[0]["id"])

        print(f"  Uni: {uni['name']} → {uid} (3 programs)")

    print("\nSeeding students...")
    student_ids = []
    for name in STUDENT_NAMES:
        email = f"{name.lower().replace(' ', '.')}@seed.test"
        auth_res = await client.auth.admin.create_user({
            "email":         email,
            "password":      "Seed@12345",
            "email_confirm": True,
            "app_metadata":  {"role": "student"},
        })
        user_id = auth_res.user.id
        row = random_student_row(user_id, name)
        res = await client.table("students").insert(row).execute()
        student_ids.append(res.data[0]["id"])
        print(f"  Student: {name} → {student_ids[-1]}")

    print("\nSeeding 50 applications...")
    for i in range(50):
        student_id    = random.choice(student_ids)
        program_id    = random.choice(program_ids)
        consultant_id = random.choice(consultant_ids)
        agency_idx    = 0 if consultant_id in consultant_ids[:2] else 1
        agency_id     = agency_ids[agency_idx]

        # Random status progression
        status = random.choice(ALL_STATUSES[:6])  # bias toward earlier statuses
        history = [{"status": "lead", "changed_by": "seed", "changed_at": datetime.now(timezone.utc).isoformat(), "note": "Seeded"}]
        if status != "lead":
            history.append({"status": status, "changed_by": "seed", "changed_at": datetime.now(timezone.utc).isoformat(), "note": "Seeded"})

        await client.table("applications").insert({
            "student_id":    student_id,
            "program_id":    program_id,
            "consultant_id": consultant_id,
            "agency_id":     agency_id,
            "status":        status,
            "status_history": history,
        }).execute()

    print(f"\nDone! Seeded {len(agency_ids)} agencies, {len(consultant_ids)} consultants, "
          f"{len(student_ids)} students, {len(uni_ids)} universities, "
          f"{len(program_ids)} programs, 50 applications.")


if __name__ == "__main__":
    asyncio.run(seed())
