#!/usr/bin/env python3
"""
MAHOUN V2 — Phase 2: Priority Group C Regulatory Ingestion Runner
Ingests all 11 approved regulatory instruments into Staging (port 7688).
Ensures zero Production (port 7687) mutations and collects full audit metrics.
"""

import sys
import os
import subprocess
import json
import time

LAWS_ROOT = "/home/haji/Desktop/KingMahouN/LAWS"
TARGET_URI = "bolt://localhost:7688"

JOBS = [
    {
        "canonical_id": "regulation:administrative_health_art26_1393",
        "law_name": "آیین‌نامه اجرایی ماده ۲۶ قانون ارتقای سلامت نظام اداری و مقابله با فساد مصوب ۱۳۹۳",
        "rel_path": "data/2026-09-13/آیین_نامه_اجرایی_ماده_26_قانون_ارتقای_سلامت_نظام_اداری_و_مقابله_با_فساد_1393_04_15.txt",
        "instrument_type": "regulation",
        "extra_args": []
    },
    {
        "canonical_id": "regulation:country_contracts_database_1392",
        "law_name": "آیین‌نامه اجرایی پایگاه اطلاعات قراردادهای کشور مصوب ۱۳۹۲",
        "rel_path": "data/2026-09-13/آیین_نامه_اجرایی_پایگاه_اطلاعات_قراردادهای_کشور_1392_02_29.txt",
        "instrument_type": "regulation",
        "extra_args": []
    },
    {
        "canonical_id": "regulation:economic_corruption_judges_1403",
        "law_name": "آیین‌نامه شرایط قضات دادسرا و دادگاه در رسیدگی به جرایم مربوط به مفاسد اقتصادی و مالی مصوب ۱۴۰۳",
        "rel_path": "data/2026-09-13/آیین_نامه_شرایط_قضات_دادسرا_و_دادگاه_در_رسیدگی_به_جرایم_مربوط_به_مفاسد_اقتصادی_و_مالی_1403_04_06.txt",
        "instrument_type": "regulation",
        "extra_args": []
    },
    {
        "canonical_id": "regulation:legal_entities_database_1393",
        "law_name": "آیین‌نامه پایگاه اطلاعات اشخاص حقوقی مصوب ۱۳۹۳",
        "rel_path": "data/2026-09-13/آیین_نامه_پایگاه_اطلاعات_اشخاص_حقوقی_1393_11_01.txt",
        "instrument_type": "regulation",
        "extra_args": []
    },
    {
        "canonical_id": "regulation:prevention_bad_debts_1397",
        "law_name": "آیین‌نامه پیشگیری از انباشت مطالبات غیرجاری بانکی مصوب ۱۳۹۷",
        "rel_path": "data/2026-09-13/آیین_نامه_پیشگیری_از_انباشت_مطالبات_غیرجاری_بانکی_1397_12_28.txt",
        "instrument_type": "regulation",
        "extra_args": []
    },
    {
        "canonical_id": "circular:central_bank_bank_duties_1402",
        "law_name": "بخشنامه بانک مرکزی در خصوص اهم احکام و تکالیف بانک‌ها و موسسات اعتباری غیربانکی مصوب ۱۴۰۲",
        "rel_path": "data/2026-09-13/بخشنامه_بانک_مرکزی_اهم_احکام_و_تکالیف_بانکها_و_موسسات_اعتباری_غیربانکی_1402_03_17.txt",
        "instrument_type": "circular",
        "extra_args": ["--source-only"]
    },
    {
        "canonical_id": "circular:free_zones_tax_declaration_1396",
        "law_name": "بخشنامه دستورالعمل نحوه ارائه اظهارنامه مالیاتی و عملکرد مالی مناطق آزاد مصوب ۱۳۹۶",
        "rel_path": "data/2026-09-13/بخشنامه_دستورالعمل_نحوه_ارائه_اظهارنامه_مالیاتی_و_عملکرد_مالی_مناطق_آزاد_1396_04_20.txt",
        "instrument_type": "circular",
        "extra_args": []
    },
    {
        "canonical_id": "resolution:border_trade_anti_corruption_1394",
        "law_name": "تصویب‌نامه برنامه راهبردی ارتقای سلامت نظام اداری و مبارزه با فساد در مبادلات مرزی مصوب ۱۳۹۴",
        "rel_path": "data/2026-09-13/تصویب_نامه_برنامه_راهبردی_ارتقای_سلامت_نظام_اداری_و_مبارزه_با_فساد_در_مبادلات_مرزی_1394_08_17.txt",
        "instrument_type": "regulation",
        "extra_args": ["--source-only"]
    },
    {
        "canonical_id": "directive:financial_statements_system_1402",
        "law_name": "دستورالعمل اجرایی سامانه صورت‌های مالی موضوع ماده ۱۱ آیین‌نامه مطالبات غیرجاری بانکی مصوب ۱۴۰۲",
        "rel_path": "data/2026-09-13/دستورالعمل_اجرایی_سامانه_صورت_های_مالی_موضوع_ماده_11_آیین_نامه_مطالبات_غیرجاری_بانکی_1402_12_23.txt",
        "instrument_type": "directive",
        "extra_args": []
    },
    {
        "canonical_id": "directive:shell_companies_prevention_1403",
        "law_name": "دستورالعمل اجرایی شناسایی و پیشگیری از تشکیل و فعالیت شرکت‌های صوری مصوب ۱۴۰۳",
        "rel_path": "data/2026-09-13/دستورالعمل_اجرایی_شناسایی_و_پیشگیری_از_تشکیل_و_فعالیت_شرکت_های_صوری_1403_04_24.txt",
        "instrument_type": "directive",
        "extra_args": []
    },
    {
        "canonical_id": "regulation:professional_ethics_administrative_1402",
        "law_name": "آیین‌نامه ارتقای اخلاق حرفه‌ای در نظام اداری مصوب ۱۴۰۲",
        "rel_path": "data/2026-09-13/آیین_نامه_ارتقای_اخلاق_حرفه_ای_در_نظام_اداری_1402_11_08_source_snapshot.txt",
        "instrument_type": "regulation",
        "extra_args": []
    }
]

def run():
    print("================================================================================")
    print("  MAHOUN V2 — Priority Group C Regulatory Ingestion Runner")
    print(f"  Target: {TARGET_URI}")
    print("================================================================================")
    
    results = []
    start_all = time.time()
    
    for i, job in enumerate(JOBS, 1):
        cid = job["canonical_id"]
        file_path = os.path.join(LAWS_ROOT, job["rel_path"])
        cmd = [
            "python3", "scripts/build_legal_kg.py",
            "--file", file_path,
            "--default-law-id", cid,
            "--default-law-name", job["law_name"],
            "--instrument-type", job["instrument_type"],
            "--target-uri", TARGET_URI
        ] + job["extra_args"]
        
        print(f"\n[{i}/{len(JOBS)}] Ingesting {cid}...")
        t0 = time.time()
        res = subprocess.run(cmd, capture_output=True, text=True)
        dur = time.time() - t0
        
        if res.returncode == 0:
            print(f"  ✅ SUCCESS ({dur:.2f}s)")
            results.append({"id": cid, "status": "SUCCESS", "duration": dur})
        else:
            print(f"  ❌ FAILED ({dur:.2f}s)")
            print(res.stderr[-1000:])
            results.append({"id": cid, "status": "FAILED", "duration": dur, "error": res.stderr})
            print("Aborting remaining jobs due to fail-closed requirement.")
            break
            
    print("\n================================================================================")
    print(f"  COMPLETED {len(results)}/{len(JOBS)} JOBS in {time.time() - start_all:.2f}s")
    print("================================================================================")
    for r in results:
        print(f"  {r['status']}: {r['id']} ({r['duration']:.2f}s)")

if __name__ == "__main__":
    run()

