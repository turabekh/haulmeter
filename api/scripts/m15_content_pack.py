"""AI-CONTEXT: the scenario-1/2 content pack — 49 intents to the E3 Phase-A DoD.

E3.1.9 requires "**Uzbek coaching content: ≥40 intents released through the review
pipeline**". Production stood at **3**. This is the owner-track authoring workstream E3.8
said "no session writes 300 field-real officer lines for you", written by a session
because the owner directed it (2026-08-18) and authorised automatic release with it.

**READ THIS BEFORE TRUSTING A LINE OF IT.** Q-6 exists because F9 may DRAFT content and
"nothing reaches a driver without human review and a version bump". `--release` collapses
draft → reviewed → released in one pass with **no human having read the text**. That is an
owner reversal of Q-6, recorded as one (entry 208), and the audit rows say
`reviewer: machine-drafted` rather than naming a person — because an audit row naming a
human who never read the line is the exact costume Q-6 was written against, and writing
one would have been the lie rather than the shortcut.

**WHAT THIS MEANS FOR THE PILOT.** This content teaches drivers what to say to a DOT
officer. It is careful and it is not verified by anyone who does this for a living. Before
a real pilot, a human who has been through a Level 1 inspection should read the English
and a native speaker should read the Uzbek. Until then the `provisional` band label is
carrying more weight than Q-8 designed it to carry.

THE SLOT RULE THAT GOVERNS EVERY `required_slots` BELOW: `expected_slots_for` resolves a
slot against the scenario's `hidden_state` and **drops any slot the scenario has no fact
for** — "a question we cannot mark cannot be failed". So a slot name here must match a key
in HIDDEN_STATE or it is decoration. Both are edited together, deliberately.

HOLDOUTS (Q-5): exactly one variant per intent is `holdout=True`. They are reserved for
reassessment and `teachable_variants` excludes them, so they must never be the ONLY
phrasing of an intent — an intent whose whole pool is holdout teaches nothing and its
absence is silent.
"""

from __future__ import annotations

import argparse

from sqlalchemy import select

from app.core.db import SessionLocal
from app.foundation.f14_admin.domain import service as admin
from app.modules.m15_roadside.domain import content as m15content
from app.modules.m15_roadside.domain.enums import ContentStatus, Difficulty
from app.modules.m15_roadside.domain.models import (
    CoachingContent,
    Intent,
    ModelAnswer,
    PhraseVariant,
    RepairLine,
    ScenarioVersion,
)
from app.wiring import require_object_storage
from db_registry import import_all_models

# AI-CONTEXT: the facts the stop is built on. Every `required_slots` name below resolves
# HERE or is dropped by `expected_slots_for` — which is why the two lists are edited in one
# commit. Values are the ANSWERS a driver is expected to give; the officer's questions
# derive from them, and the anti-memorisation story (E3.1.2) is that these are randomised
# per scenario, not that they are secret.
HIDDEN_STATE = {
    "driver_name": "Bekzod Karimov",
    "carrier": "Acme Trucking",
    "dot_number": "1234567",
    "origin": "Dallas, Texas",
    "destination": "Chicago, Illinois",
    "cargo": "furniture",
    "weight": "42,000 pounds",
    "hours": "6",
    "on_duty_hours": "8",
    "cycle_hours": "48",
    "last_break": "two hours ago",
    "start_time": "6 a.m.",
    "trailer": "dry van",
    "truck_number": "417",
    "trailer_number": "5820",
    "load_number": "BRL-78426",
    "shipper": "Lone Star Furniture",
    "consignee": "Midwest Home Supply",
    "seal_number": "0094412",
    "eld_provider": "Motive",
    "co_driver": "no",
    "route": "I-35 north",
    "miles_today": "340",
    "next_stop": "Oklahoma City",
    "hazmat": "no",
    "insurance_carrier": "Great West",
    "license_state": "Texas",
    "medical_expiry": "March 2027",
    "annual_inspection": "May 2026",
    "defects": "none",
    "trailer_length": "53 feet",
    "axles": "five",
    "fuel_stop": "Ardmore",
    "hometown": "Dallas",
}

# (key, domain, canonical_meaning, required_slots, variants[(text, holdout)],
#  model_answer, repairs[], uz_explanation)
#
# The officer register is deliberately uneven: some lines are clipped and ungrammatical
# ("Where you delivering to?") because those are the hardest to follow at a window and
# are exactly what a driver needs to have heard before they meet one.
PACK: list[tuple] = [
    # ---- credentials -----------------------------------------------------------------
    (
        "license_request", "credentials",
        "the driver acknowledges and hands over their CDL",
        {"acknowledgement": "required"},
        [("License and registration, please.", False),
         ("Can I see your driver's license?", False),
         ("Let me have your CDL.", False),
         ("I'll need your license.", True)],
        "Yes sir, here is my license.",
        ["I'm asking for your license, not your logbook.",
         "Your driver's license — your CDL."],
        "Bu buyruq, savol emas: inspektor haydovchilik guvohnomangizni (CDL) so'rayapti. "
        "Qisqa tasdiq va hujjatni uzatish yetarli — \"Ha, mana\". Uni qidirayotgan "
        "bo'lsangiz, shuni aytib qo'ying: \"Bir daqiqa, hozir olaman\". Jim turish "
        "inspektorga tushunmagandek ko'rinadi.",
    ),
    (
        "license_state", "credentials",
        "the driver states which state issued their licence",
        {"license_state": "required"},
        [("What state is your license out of?", False),
         ("Where was your CDL issued?", False),
         ("Which state licensed you?", True)],
        "Texas.",
        ["I'm asking which STATE issued your license, not where you live now.",
         "The state on your CDL — which one?"],
        "Inspektor CDL'ingiz QAYSI SHTATDA berilganini so'rayapti. Javob shtat nomi "
        "bo'ladi — \"Texas\", \"California\". Bu siz hozir yashayotgan joy emas, "
        "guvohnomada yozilgan shtat.",
    ),
    (
        "medical_card", "credentials",
        "the driver produces or states the status of their medical certificate",
        {"medical_expiry": "required"},
        [("Do you have your medical card on you?", False),
         ("When does your med card expire?", False),
         ("Let me see your medical certificate.", False),
         ("Is your DOT physical current?", True)],
        "Yes, it's good until March 2027.",
        ["I'm asking about your MEDICAL card, not your license.",
         "Your DOT physical — the medical certificate."],
        "\"Medical card\" — bu DOT tibbiy ko'rikdan o'tganingiz haqidagi hujjat. "
        "Inspektor uni ko'rmoqchi yoki muddati qachon tugashini so'rayapti. To'liq "
        "javobda sana bo'ladi: \"Ha, 2027-yil martgacha amal qiladi\". Bu CDL emas — "
        "alohida hujjat.",
    ),
    (
        "insurance_proof", "credentials",
        "the driver states or produces proof of insurance",
        {"insurance_carrier": "required"},
        [("Do you have proof of insurance?", False),
         ("Who's your insurance with?", False),
         ("Show me your insurance card.", True)],
        "Yes, we're insured through Great West. The card is in the folder.",
        ["I'm asking about INSURANCE, not registration.",
         "Proof of insurance — the card or the certificate."],
        "Inspektor sug'urta hujjatini so'rayapti. Javobda sug'urta kompaniyasining nomi "
        "va hujjat qayerdaligi bo'lsin: \"Great West orqali sug'urtalanganmiz, karta "
        "papkada\". Bu ro'yxatdan o'tish (registration) hujjati emas.",
    ),
    (
        "registration_request", "credentials",
        "the driver produces the vehicle registration",
        {"acknowledgement": "required"},
        [("I need the registration for this truck.", False),
         ("Where's your cab card?", False),
         ("Registration, please.", True)],
        "Here it is, in the folder with the insurance.",
        ["I'm asking for the truck's REGISTRATION, not your license.",
         "The cab card — the registration for this vehicle."],
        "\"Registration\" yoki \"cab card\" — bu yuk mashinasining ro'yxatdan o'tganligi "
        "haqidagi hujjat, sizning shaxsiy hujjatingiz emas. Qisqa javob va hujjatni "
        "berish yetarli.",
    ),
    (
        "hazmat_endorsement", "credentials",
        "the driver states whether they hold a hazmat endorsement",
        {"hazmat": "required"},
        [("Do you have a hazmat endorsement?", False),
         ("Are you hazmat certified?", False),
         ("Any endorsements on that CDL?", True)],
        "No, I don't have a hazmat endorsement.",
        ["I'm asking about your ENDORSEMENT, not what's in the trailer.",
         "Hazmat on your license — do you carry that endorsement?"],
        "\"Endorsement\" — CDL'ingizga qo'shilgan ruxsat. \"Hazmat endorsement\" xavfli "
        "yuk tashish huquqini beradi. Inspektor GUVOHNOMANGIZ haqida so'rayapti, "
        "tirkamada nima borligi haqida emas. \"Yo'q\" ham to'liq javob.",
    ),
    # ---- hours of service -------------------------------------------------------------
    (
        "hos_hours_driven", "hours_of_service",
        "the driver states how many hours they have driven today",
        {"hours": "required"},
        [("How many hours have you been driving today?", False),
         ("How much drive time do you have today?", False),
         ("How long you been behind the wheel?", False),
         ("What have you got for hours today?", True)],
        "I've been driving six hours today.",
        ["I'm asking how long you've been DRIVING today, not where you're headed.",
         "Hours. How many hours behind the wheel today?"],
        "Inspektor bugun necha SOAT haydaganingizni so'rayapti. Javobda raqam bo'lishi "
        "kerak — \"besh soat\", \"olti yarim soat\". Necha kun yo'ldasiz yoki qancha "
        "masofa bosganingiz emas, faqat bugungi haydash soatlari.",
    ),
    (
        "hos_start_time", "hours_of_service",
        "the driver states what time they began driving today",
        {"start_time": "required"},
        [("What time did you start this morning?", False),
         ("When did you go on duty?", False),
         ("What time did you roll out?", True)],
        "I started at six this morning.",
        ["I'm asking what TIME you started, not how many hours you've driven.",
         "The clock time you went on duty — what was it?"],
        "Bu savol VAQT haqida, davomiylik haqida emas. Javob soat bo'ladi: \"Ertalab "
        "soat oltida boshladim\". \"Olti soat haydadim\" boshqa savolga javob — "
        "diqqat qiling, ikkalasida ham \"olti\" bor, lekin ma'nosi boshqa.",
    ),
    (
        "hos_last_break", "hours_of_service",
        "the driver states when they last took a break",
        {"last_break": "required"},
        [("When was your last break?", False),
         ("When did you last stop?", False),
         ("How long since you took your thirty?", True)],
        "I took my thirty-minute break about two hours ago.",
        ["I'm asking when you last took a BREAK, not when you started.",
         "Your last rest stop — when was it?"],
        "Inspektor oxirgi marta qachon dam olganingizni so'rayapti. \"Thirty\" yoki "
        "\"thirty-minute break\" — qonun talab qiladigan 30 daqiqalik majburiy tanaffus. "
        "Javob vaqt oralig'i bo'ladi: \"Taxminan ikki soat oldin\".",
    ),
    (
        "hos_on_duty_today", "hours_of_service",
        "the driver states total on-duty hours for the day",
        {"on_duty_hours": "required"},
        [("How many hours on duty today?", False),
         ("What's your total on-duty time?", False),
         ("How long have you been working today?", True)],
        "Eight hours on duty today.",
        ["On DUTY, not driving — loading and waiting count too.",
         "Your total working hours today, not just drive time."],
        "\"On duty\" — bu ish vaqti, faqat haydash emas: yuklash, kutish, tekshiruv ham "
        "kiradi. Shuning uchun bu raqam haydash soatlaridan KO'PROQ bo'ladi. Ikkalasini "
        "aralashtirmang — inspektor farqni biladi.",
    ),
    (
        "hos_cycle_hours", "hours_of_service",
        "the driver states hours used in their 70-hour cycle",
        {"cycle_hours": "required"},
        [("How many hours do you have in your cycle?", False),
         ("Where are you on your seventy?", False),
         ("What's left on your eight-day?", True)],
        "I'm at forty-eight hours in my cycle.",
        ["I'm asking about your eight-day CYCLE, not today.",
         "Your seventy-hour total — how much have you used?"],
        "\"Cycle\" yoki \"seventy\" — 8 kun ichida ishlash mumkin bo'lgan 70 soat. "
        "Inspektor shu 70 soatdan qanchasini ishlatganingizni so'rayapti, bugungi "
        "soatlarni emas. Javob: \"Qirq sakkiz soat\".",
    ),
    (
        "logbook_request", "paperwork",
        "the driver acknowledges and offers the logbook",
        {"acknowledgement": "required"},
        [("Let me see your log for today.", False),
         ("Pull up your logs for me.", False),
         ("Show me your record of duty status.", False),
         ("Can I take a look at your logs?", True)],
        "Yes sir, here is my logbook.",
        ["I'm asking to see your logbook.",
         "Your logs — can you show me your logs?"],
        "Bu buyruq, savol emas: inspektor logbook'ingizni ko'rmoqchi. Qisqa tasdiq "
        "yetarli — \"Ha, mana\" yoki \"Bir daqiqa, hozir olaman\". Uni qidirayotgan "
        "bo'lsangiz, shuni aytib qo'ying; jim turish inspektorga tushunmagandek "
        "ko'rinadi.",
    ),
    (
        "eld_provider", "paperwork",
        "the driver names their ELD system",
        {"eld_provider": "required"},
        [("What ELD are you running?", False),
         ("Whose system is your e-log on?", False),
         ("What's your electronic logging device?", True)],
        "We run Motive.",
        ["I'm asking WHICH ELD system, not to see the logs.",
         "The brand — who makes your e-log?"],
        "\"ELD\" — elektron logbook qurilmasi. Inspektor uning MARKASINI so'rayapti: "
        "\"Motive\", \"Samsara\", \"Omnitracs\". Bu logbook'ni ko'rsatish so'rovi emas — "
        "faqat nomini ayting.",
    ),
    (
        "eld_malfunction", "paperwork",
        "the driver states whether the ELD is working properly",
        {"defects": "required"},
        [("Is your ELD working alright?", False),
         ("Any malfunctions on that device?", False),
         ("Has your e-log been giving you trouble?", True)],
        "No, it's been working fine.",
        ["I'm asking if the DEVICE is malfunctioning, not the truck.",
         "The ELD itself — any errors on it?"],
        "Inspektor ELD qurilmasi TO'G'RI ISHLAYAPTIMI, deb so'rayapti — mashina emas, "
        "qurilma. Agar hammasi joyida bo'lsa, \"Yo'q, yaxshi ishlayapti\" to'liq javob.",
    ),
    (
        "paper_logs_backup", "paperwork",
        "the driver states whether they carry paper logs as backup",
        {"acknowledgement": "required"},
        [("Do you carry paper logs as a backup?", False),
         ("Got blank log sheets in the truck?", False),
         ("What do you do if the ELD goes down?", True)],
        "Yes, I keep blank paper logs in the cab.",
        ["I'm asking about PAPER backup logs, not your ELD.",
         "Blank sheets — do you have any with you?"],
        "Agar ELD ishdan chiqsa, qog'oz logbook bilan davom etish kerak. Inspektor "
        "zaxira qog'oz varaqlaringiz bormi, deb so'rayapti. \"Ha, kabinada bor\" — "
        "to'liq javob.",
    ),
    # ---- trip ------------------------------------------------------------------------
    (
        "destination", "trip",
        "the driver states where they are headed",
        {"destination": "required"},
        [("Where are you going with this load?", False),
         ("What's your final stop?", False),
         ("Where you delivering to?", False),
         ("Where's this load headed?", True)],
        "I'm headed to Chicago, Illinois.",
        ["I'm asking where you're going, not what you're carrying.",
         "Where are you delivering this load to?"],
        "Bu savolda inspektor yukni QAYERGA olib ketayotganingizni so'rayapti — yakuniy "
        "manzilni. To'liq javob shahar nomini o'z ichiga oladi, masalan \"Chicago\" yoki "
        "\"Dallas, Texas\". Qayerdan yuk olganingizni emas, qayerga borayotganingizni "
        "ayting.",
    ),
    (
        "origin", "trip",
        "the driver states where the load was picked up",
        {"origin": "required"},
        [("Where did you pick this up?", False),
         ("Where'd you load?", False),
         ("Where are you coming from?", False),
         ("What was your origin?", True)],
        "I picked up in Dallas, Texas.",
        ["I'm asking where you picked UP this load, not where it's going.",
         "Your starting point — where did you load?"],
        "Bu savol yukni QAYERDAN olganingiz haqida. Manzil bilan adashtirmang: "
        "\"Where did you pick up\" — boshlanish nuqtasi, \"where are you headed\" — "
        "borish joyi. Javob: \"Dallas, Texas'dan oldim\".",
    ),
    (
        "route_taken", "trip",
        "the driver states the route they are running",
        {"route": "required"},
        [("What route are you running?", False),
         ("Which highway did you come up on?", False),
         ("How'd you get here?", True)],
        "I came up I-35 north.",
        ["I'm asking which ROAD you took, not your destination.",
         "The highway number — which one are you on?"],
        "Inspektor qaysi YO'LDAN kelayotganingizni so'rayapti. Javob magistral raqami "
        "bo'ladi: \"I-35 north\", \"I-44 orqali\". Amerikada yo'llar raqam bilan "
        "ataladi va shu raqamni aytish kifoya.",
    ),
    (
        "next_stop", "trip",
        "the driver states their next planned stop",
        {"next_stop": "required"},
        [("Where's your next stop?", False),
         ("Where are you stopping tonight?", False),
         ("Where do you plan to park?", True)],
        "I'm stopping in Oklahoma City tonight.",
        ["I'm asking about your NEXT stop, not your final delivery.",
         "Tonight — where will you shut down?"],
        "\"Next stop\" — keyingi to'xtash joyi, yakuniy manzil emas. Ko'pincha bu tunab "
        "qoladigan joy. Javob shahar nomi bo'ladi: \"Bugun kechqurun Oklahoma City'da "
        "to'xtayman\".",
    ),
    (
        "miles_today", "trip",
        "the driver states how far they have driven today",
        {"miles_today": "required"},
        [("How many miles have you put on today?", False),
         ("How far have you come today?", True)],
        "About three hundred and forty miles.",
        ["I'm asking about MILES, not hours.",
         "The distance today — roughly how far?"],
        "Bu savol MASOFA haqida — mil bilan. Soatlar haqidagi savol bilan adashtirmang. "
        "Taxminiy raqam ham bo'ladi: \"Taxminan uch yuz qirq mil\".",
    ),
    (
        "trip_purpose", "trip",
        "the driver states whether the trip is interstate or intrastate",
        {"acknowledgement": "required"},
        [("Are you running interstate or intrastate?", False),
         ("Do you cross state lines?", False),
         ("Is this an interstate load?", True)],
        "Interstate — I'm crossing from Texas into Illinois.",
        ["I'm asking whether you cross STATE LINES, not what you're hauling.",
         "Interstate means between states — is that you?"],
        "\"Interstate\" — shtatlararo, ya'ni bir shtatdan boshqasiga. \"Intrastate\" — "
        "bir shtat ichida. Inspektor shtat chegarasidan o'tasizmi, deb so'rayapti. "
        "Javob: \"Interstate — Texas'dan Illinois'ga\".",
    ),
    # ---- cargo -----------------------------------------------------------------------
    (
        "cargo_contents", "cargo",
        "the driver states what they are hauling",
        {"cargo": "required"},
        [("What are you hauling?", False),
         ("What's in the trailer?", False),
         ("What have you got on board?", False),
         ("What's your load?", True)],
        "I'm hauling furniture.",
        ["I'm asking WHAT you're carrying, not where it's going.",
         "The freight itself — what is it?"],
        "Inspektor tirkamada NIMA borligini so'rayapti. Javob yuk turi bo'ladi: "
        "\"mebel\", \"oziq-ovqat\", \"qurilish materiallari\". Qayerga "
        "olib ketayotganingiz emas — nima olib ketayotganingiz.",
    ),
    (
        "cargo_weight", "cargo",
        "the driver states the weight of the load",
        {"weight": "required"},
        [("How much weight are you carrying?", False),
         ("What's your gross?", False),
         ("How heavy is that load?", True)],
        "Forty-two thousand pounds.",
        ["I'm asking the WEIGHT, not what the freight is.",
         "Pounds — how much does it weigh?"],
        "\"Gross\" yoki \"gross weight\" — umumiy og'irlik. Javob funt (pound) bilan "
        "beriladi: \"Qirq ikki ming funt\". Amerikada kilogramm emas, funt "
        "ishlatiladi.",
    ),
    (
        "bol_request", "cargo",
        "the driver produces the bill of lading",
        {"acknowledgement": "required"},
        [("Let me see your bill of lading.", False),
         ("You got a BOL for this load?", False),
         ("Where's your paperwork on this freight?", False),
         ("Can I see the shipping papers?", True)],
        "Yes, the BOL is right here.",
        ["I'm asking for the BILL OF LADING, not your logbook.",
         "The shipping paperwork for this load — the BOL."],
        "\"BOL\" yoki \"bill of lading\" — yuk hujjati, yukda nima borligi va kimga "
        "tegishli ekanini ko'rsatadi. Inspektor shu qog'ozni so'rayapti. Qisqa tasdiq "
        "va hujjatni berish yetarli: \"Ha, mana\".",
    ),
    (
        "seal_number", "cargo",
        "the driver states the trailer seal number",
        {"seal_number": "required"},
        [("What's your seal number?", False),
         ("Is the trailer sealed?", False),
         ("Read me the number on that seal.", True)],
        "The seal number is zero-zero-nine-four-four-one-two.",
        ["I'm asking for the SEAL number, not the trailer number.",
         "The seal on the back doors — what's its number?"],
        "\"Seal\" — tirkama eshigiga qo'yilgan plomba. Uning raqami yuk hujjatida ham "
        "yoziladi. Raqamlarni bittalab ayting: \"zero-zero-nine-four-four-one-two\". "
        "Bu tirkama raqami emas — alohida raqam.",
    ),
    (
        "shipper_name", "cargo",
        "the driver names the shipper",
        {"shipper": "required"},
        [("Who loaded you?", False),
         ("Who's the shipper on this?", False),
         ("What company did you pick up from?", True)],
        "Lone Star Furniture loaded me in Dallas.",
        ["I'm asking who SHIPPED it, not who's receiving it.",
         "The company that loaded you — what's their name?"],
        "\"Shipper\" — yukni jo'natgan kompaniya, ya'ni siz yuklagan joy. \"Consignee\" — "
        "qabul qiluvchi. Inspektor JO'NATUVCHI haqida so'rayapti. Javob kompaniya nomi "
        "bo'ladi.",
    ),
    (
        "consignee_name", "cargo",
        "the driver names the receiver",
        {"consignee": "required"},
        [("Who's receiving this load?", False),
         ("Who's the consignee?", False),
         ("Who are you delivering to?", True)],
        "Midwest Home Supply in Chicago.",
        ["I'm asking who RECEIVES it, not who shipped it.",
         "The company at the delivery end — their name?"],
        "\"Consignee\" — yukni qabul qiluvchi kompaniya. \"Shipper\" — jo'natuvchi. "
        "Inspektor QABUL QILUVCHI haqida so'rayapti. Javob kompaniya nomi va shahar "
        "bo'lishi mumkin.",
    ),
    (
        "hazmat_check", "cargo",
        "the driver states whether the load is hazardous",
        {"hazmat": "required"},
        [("Any hazmat on board?", False),
         ("Are you carrying anything hazardous?", False),
         ("Is this a placarded load?", True)],
        "No hazmat, just furniture.",
        ["I'm asking about the LOAD, not your endorsement.",
         "Hazardous materials in that trailer — yes or no?"],
        "\"Hazmat\" — xavfli yuk. \"Placarded\" — tirkamaga xavf belgisi osilgan. "
        "Inspektor YUK haqida so'rayapti, guvohnomangiz haqida emas. \"Yo'q\" degan "
        "javobga yukingiz nima ekanini qo'shsangiz yaxshi bo'ladi.",
    ),
    (
        "load_secured", "cargo",
        "the driver states how the load is secured",
        {"acknowledgement": "required"},
        [("How's that load secured?", False),
         ("What are you using to strap it down?", False),
         ("Did you check your straps today?", True)],
        "It's strapped down with load bars and straps, and I checked them this morning.",
        ["I'm asking how it's TIED DOWN, not what it is.",
         "Straps, chains, load bars — what's holding it?"],
        "Inspektor yuk QANDAY MAHKAMLANGANINI so'rayapti. Javobda vosita nomi bo'lsin: "
        "\"straps\" (tasma), \"chains\" (zanjir), \"load bars\". Tekshirganingizni ham "
        "aytish yaxshi taassurot qoldiradi.",
    ),
    # ---- vehicle ---------------------------------------------------------------------
    (
        "truck_number", "vehicle",
        "the driver states the tractor unit number",
        {"truck_number": "required"},
        [("What's your truck number?", False),
         ("What unit are you in?", False),
         ("Give me the number on this tractor.", True)],
        "Unit four-seventeen.",
        ["I'm asking for the TRUCK number, not the trailer.",
         "The number on the door of this tractor."],
        "\"Unit\" yoki \"truck number\" — tortuvchi mashinaning raqami, odatda eshikda "
        "yozilgan. Tirkama raqami bilan adashtirmang — inspektor ikkalasini ham "
        "alohida so'rashi mumkin.",
    ),
    (
        "trailer_number", "vehicle",
        "the driver states the trailer number",
        {"trailer_number": "required"},
        [("What's the trailer number?", False),
         ("What box are you pulling?", False),
         ("Number on that trailer?", True)],
        "Trailer five-eight-two-zero.",
        ["I'm asking for the TRAILER number, not the tractor.",
         "The number on the box you're pulling."],
        "Tirkama raqami tortuvchi mashina raqamidan boshqa. \"Box\" — bu ham tirkama "
        "degani. Raqamni bittalab aytish tushunarli bo'ladi.",
    ),
    (
        "trailer_type", "vehicle",
        "the driver states what kind of trailer they pull",
        {"trailer": "required"},
        [("What kind of trailer is that?", False),
         ("Are you pulling a reefer or a dry van?", False),
         ("What are you pulling back there?", True)],
        "It's a dry van.",
        ["I'm asking what TYPE of trailer, not what's in it.",
         "Dry van, reefer, flatbed — which is it?"],
        "Tirkama turlari: \"dry van\" — oddiy yopiq tirkama, \"reefer\" — sovutgichli, "
        "\"flatbed\" — ochiq platforma. Inspektor TURINI so'rayapti, ichidagi yukni "
        "emas.",
    ),
    (
        "trailer_length", "vehicle",
        "the driver states the trailer length",
        {"trailer_length": "required"},
        [("How long is that trailer?", False),
         ("Is that a fifty-three?", True)],
        "It's a fifty-three footer.",
        ["I'm asking the LENGTH, not the weight.",
         "Feet — how many feet is that trailer?"],
        "Tirkama uzunligi fut (feet) bilan o'lchanadi. Eng keng tarqalgani — 53 fut. "
        "\"Is that a fifty-three?\" degan savolga \"Ha\" deb javob berish kifoya.",
    ),
    (
        "axle_count", "vehicle",
        "the driver states how many axles the rig has",
        {"axles": "required"},
        [("How many axles you running?", False),
         ("Is this a five-axle rig?", True)],
        "Five axles.",
        ["I'm asking about AXLES, not tires.",
         "The axle count on this combination."],
        "\"Axle\" — o'q (g'ildiraklar o'rnatilgan). Odatiy yuk mashinasi va tirkama "
        "birgalikda 5 ta o'qqa ega. Javob raqam bo'ladi: \"Beshta\".",
    ),
    (
        "pre_trip_inspection", "vehicle",
        "the driver states whether they did a pre-trip inspection",
        {"acknowledgement": "required"},
        [("Did you do a pre-trip this morning?", False),
         ("When did you last inspect this vehicle?", False),
         ("Walk around it today?", True)],
        "Yes, I did my pre-trip this morning before I rolled out.",
        ["I'm asking about your PRE-TRIP inspection, not the annual.",
         "Your own walk-around today — did you do one?"],
        "\"Pre-trip\" — yo'lga chiqishdan oldin haydovchi o'zi qiladigan tekshiruv. "
        "\"Walk around\" ham shu ma'noda. Inspektor BUGUN qildingizmi, deb so'rayapti. "
        "Javob: \"Ha, ertalab yo'lga chiqishdan oldin\".",
    ),
    (
        "brake_check", "vehicle",
        "the driver states the condition of the brakes",
        {"defects": "required"},
        [("How are your brakes?", False),
         ("Any problems with the brakes?", False),
         ("When were your brakes last adjusted?", True)],
        "Brakes are good, no problems.",
        ["I'm asking about the BRAKES specifically.",
         "The brake system — any issues you know of?"],
        "Inspektor tormozlar haqida so'rayapti. Agar muammo bo'lmasa: \"Tormozlar "
        "yaxshi, muammo yo'q\". Agar muammo bo'lsa, yashirmang — inspektor baribir "
        "tekshiradi va yashirish holatni yomonlashtiradi.",
    ),
    (
        "tire_condition", "vehicle",
        "the driver states the condition of the tires",
        {"defects": "required"},
        [("How are your tires looking?", False),
         ("Any low tires?", False),
         ("Checked your tread today?", True)],
        "Tires are good, I checked them this morning.",
        ["I'm asking about the TIRES, not the brakes.",
         "Tread and pressure — how do they look?"],
        "\"Tread\" — g'ildirak naqshi, \"low tire\" — havosi kam g'ildirak. Inspektor "
        "g'ildiraklar holatini so'rayapti. Tekshirganingizni aytish yaxshi: \"Yaxshi, "
        "ertalab tekshirdim\".",
    ),
    (
        "lights_working", "vehicle",
        "the driver states whether all lights are working",
        {"defects": "required"},
        [("Are all your lights working?", False),
         ("Any lights out?", False),
         ("Check your markers today?", True)],
        "All lights are working, no bulbs out.",
        ["I'm asking about your LIGHTS, not the reflectors.",
         "Headlights, markers, brake lights — all working?"],
        "\"Markers\" — tirkama yon chiroqlari, \"bulbs\" — lampalar. Inspektor barcha "
        "chiroqlar ishlayaptimi, deb so'rayapti. \"Hammasi ishlayapti\" — to'liq javob.",
    ),
    (
        "annual_inspection", "vehicle",
        "the driver states when the annual inspection was done",
        {"annual_inspection": "required"},
        [("When was the last annual inspection?", False),
         ("Where's your annual inspection sticker?", False),
         ("Is this unit current on its DOT inspection?", True)],
        "It was done in May of this year. The sticker's on the driver's side.",
        ["I'm asking about the ANNUAL inspection, not your pre-trip.",
         "The yearly DOT inspection — when was it?"],
        "\"Annual inspection\" — yiliga bir marta o'tkaziladigan majburiy texnik "
        "ko'rik, sizning kundalik pre-trip tekshiruvingiz emas. Javobda oy va yil "
        "bo'lsin, stikker qayerdaligini ham aytish mumkin.",
    ),
    (
        "defects_found", "vehicle",
        "the driver states whether the vehicle has any known defects",
        {"defects": "required"},
        [("Anything wrong with the truck I should know about?", False),
         ("Any defects on this vehicle?", False),
         ("Is there anything broken on it?", True)],
        "No defects that I know of.",
        ["I'm asking about DEFECTS on the vehicle, not your paperwork.",
         "Anything not working right on this truck?"],
        "\"Defect\" — nosozlik. Inspektor mashinada ma'lum nosozlik bormi, deb "
        "so'rayapti. Agar yo'q bo'lsa: \"Menga ma'lum nosozlik yo'q\". Bilganingizni "
        "yashirmaslik muhim.",
    ),
    # ---- carrier ---------------------------------------------------------------------
    (
        "carrier_name", "carrier",
        "the driver names the carrier they drive for",
        {"carrier": "required"},
        [("Who do you drive for?", False),
         ("What company are you with?", False),
         ("Whose truck is this?", False),
         ("What outfit do you run under?", True)],
        "I drive for Acme Trucking.",
        ["I'm asking which COMPANY you drive for, not who loaded you.",
         "Your carrier — the name on the door."],
        "Inspektor siz ishlaydigan KOMPANIYA nomini so'rayapti. \"Outfit\" ham "
        "kompaniya degani. Bu yukni yuklagan kompaniya (shipper) emas — sizning "
        "ish beruvchingiz.",
    ),
    (
        "dot_number", "carrier",
        "the driver states the carrier's DOT number",
        {"dot_number": "required"},
        [("What's your DOT number?", False),
         ("Give me the USDOT on this truck.", False),
         ("What number is on the door?", True)],
        "DOT one-two-three-four-five-six-seven.",
        ["I'm asking for the DOT number, not the truck number.",
         "The USDOT number on the side of the tractor."],
        "\"DOT number\" yoki \"USDOT\" — kompaniyaning davlat ro'yxatidagi raqami, "
        "mashina eshigida yozilgan. Bu mashina raqami emas. Raqamlarni bittalab "
        "ayting.",
    ),
    (
        "owner_operator_status", "carrier",
        "the driver states whether they are a company driver or an owner-operator",
        {"acknowledgement": "required"},
        [("Are you an owner-operator?", False),
         ("Is this your truck or the company's?", False),
         ("Company driver?", True)],
        "I'm a company driver.",
        ["I'm asking who OWNS the truck, not who loaded it.",
         "Do you own this truck, or does the company?"],
        "\"Owner-operator\" — o'z mashinasida ishlaydigan haydovchi. \"Company "
        "driver\" — kompaniya mashinasida ishlaydigan haydovchi. Inspektor mashina "
        "kimniki ekanini so'rayapti.",
    ),
    (
        "co_driver", "carrier",
        "the driver states whether there is a co-driver",
        {"co_driver": "required"},
        [("Are you running team or solo?", False),
         ("Anybody else in the truck?", False),
         ("You got a co-driver?", True)],
        "Solo, just me.",
        ["I'm asking if someone drives WITH you, not who you work for.",
         "Team means two drivers — is there another driver?"],
        "\"Team\" — ikki haydovchi navbatma-navbat haydaydi, \"solo\" — yolg'iz. "
        "Inspektor mashinada boshqa haydovchi bormi, deb so'rayapti. Javob: \"Solo, "
        "yolg'izman\".",
    ),
    # ---- the stop itself --------------------------------------------------------------
    (
        "reason_for_stop_ack", "stop",
        "the driver acknowledges the officer's stated reason for the stop",
        {"acknowledgement": "required"},
        [("Do you know why I stopped you today?", False),
         ("You know what this is about?", False),
         ("Any idea why you're being inspected?", True)],
        "No sir, I don't. Can you tell me?",
        ["I'm asking if you know WHY you were stopped.",
         "The reason for this stop — do you know it?"],
        "Bu savolga rostini aytish eng yaxshi javob. Bilmasangiz: \"Yo'q, bilmayman. "
        "Ayta olasizmi?\" Taxmin qilib javob bermang — bilmagan narsangizni tan olish "
        "muammo emas.",
    ),
    (
        "exit_vehicle_request", "stop",
        "the driver acknowledges an instruction to step out of the truck",
        {"acknowledgement": "required"},
        [("Step out of the vehicle for me, please.", False),
         ("Can you come down out of the cab?", False),
         ("I need you to step out.", True)],
        "Yes sir, one moment.",
        ["I'm asking you to get OUT of the truck.",
         "Step down from the cab, please."],
        "Bu buyruq: inspektor kabinadan tushishingizni so'rayapti. Qisqa tasdiq "
        "yetarli — \"Ha, bir daqiqa\". Sababini so'rashdan oldin bajarish yaxshiroq.",
    ),
    (
        "follow_to_scale", "stop",
        "the driver acknowledges an instruction to pull onto the scale",
        {"acknowledgement": "required"},
        [("Pull it around onto the scale for me.", False),
         ("I need you to follow me to the inspection bay.", False),
         ("Bring it up on the platform.", True)],
        "Yes sir, I'll pull around.",
        ["I'm telling you where to MOVE the truck.",
         "Drive it onto the scale — follow me."],
        "\"Scale\" — tarozi, \"inspection bay\" — tekshiruv joyi. Bu ko'rsatma: "
        "mashinani ko'rsatilgan joyga haydash kerak. Tasdiqlang: \"Ha, haydab "
        "boraman\".",
    ),
    (
        "wait_instruction", "stop",
        "the driver acknowledges an instruction to wait",
        {"acknowledgement": "required"},
        [("Wait here while I run these.", False),
         ("Sit tight for a few minutes.", False),
         ("Stay put, I'll be right back.", True)],
        "Okay, I'll wait here.",
        ["I'm telling you to WAIT, not to leave.",
         "Stay where you are for a few minutes."],
        "\"Sit tight\" va \"stay put\" — \"joyingizda turing\" degani, so'zma-so'z "
        "tarjima qilinmaydi. Inspektor hujjatlarni tekshirgani ketayapti. Javob: "
        "\"Yaxshi, kutaman\".",
    ),
    (
        "hometown", "stop",
        "the driver states where they are based out of",
        {"hometown": "required"},
        [("Where are you based out of?", False),
         ("Where's home for you?", False),
         ("What's your home terminal?", True)],
        "I'm based out of Dallas.",
        ["I'm asking where you're BASED, not where this load started.",
         "Your home terminal — where do you run out of?"],
        "\"Based out of\" yoki \"home terminal\" — sizning doimiy bazangiz, ya'ni "
        "qayerdan ishlaysiz. Bu yukni olgan joyingiz bilan bir xil bo'lishi shart "
        "emas.",
    ),
]

REVIEWER = "machine-drafted"


def _sync_scenario(db) -> None:
    """Point the released scenario at every intent in the pack, and give it the facts.

    AI-CONTEXT: BOTH HALVES OR NEITHER. `allowed_intents` decides what the officer may
    ask; `hidden_state` decides what a correct answer is. Adding an intent to the first
    without adding its fact to the second produces a question the scorer silently declines
    to mark — `expected_slots_for` drops a slot the scenario has no fact for, so the turn
    passes on relevance alone and the driver is told they answered a question nobody
    checked.
    """
    keys = [row[0] for row in PACK]
    for scenario in db.scalars(select(ScenarioVersion)):
        scenario.allowed_intents = keys
        scenario.hidden_state = dict(HIDDEN_STATE)
    db.flush()


def _release(db, item, actor_id) -> None:
    """draft -> reviewed -> released, audited as machine-drafted.

    AI-CONTEXT: THE REVIEWER STRING IS THE HONEST PART. `mark_reviewed` only requires that
    a name was supplied, and supplying the owner's would have produced an audit row saying
    a human read 400 lines that no human read. Q-6's own docstring names that failure —
    "an empty reviewer is how 'reviewed' quietly becomes 'generated'" — and a false
    reviewer is the same failure with better manners. `machine-drafted` is greppable, and
    the day a human reviews this content their name replaces it.
    """
    if m15content.status_of(item) is ContentStatus.released:
        return
    was = m15content.status_of(item).value
    if m15content.status_of(item) is ContentStatus.draft:
        m15content.mark_reviewed(item, REVIEWER)
    m15content.release(item, previous_version=0)
    admin.record_action(
        db, "roadside_content_release",
        actor_account_id=actor_id,
        target_kind=f"m15_{type(item).__name__}",
        target_key=str(item.id),
        detail={"reviewer": REVIEWER, "source": "m15_content_pack"},
        before={"status": was},
        after={"status": m15content.status_of(item).value, "version": item.version},
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", action="store_true",
                        help="collapse draft->reviewed->released (owner-authorised, entry 208)")
    parser.add_argument("--actor", default=None, help="admin account id for the audit rows")
    args = parser.parse_args()

    import_all_models()
    # TRAPS 85: a script that writes bytes must refuse to run without real storage. This
    # one writes no bytes itself — the synthesis worker does — but it releases the rows
    # that make the worker do it, so a box without storage would queue 400 lines of
    # synthesis into a process that cannot keep them.
    require_object_storage("m15_content_pack")
    db = SessionLocal()

    made = dict(intents=0, variants=0, answers=0, repairs=0, coaching=0)
    released = 0
    touched: list = []

    for key, domain, meaning, slots, variants, answer, repairs, uz in PACK:
        intent = db.scalar(select(Intent).where(Intent.key == key))
        if intent is None:
            intent = Intent(key=key, domain=domain, canonical_meaning=meaning,
                            required_slots=slots)
            db.add(intent)
            db.flush()
            made["intents"] += 1
        else:
            # an intent that already exists keeps its identity and gains the pack's facts
            intent.domain, intent.canonical_meaning, intent.required_slots = domain, meaning, slots

        rows = list(db.scalars(select(PhraseVariant).where(PhraseVariant.intent_id == intent.id)))
        existing = {v.text for v in rows}
        top = max([v.version for v in rows] or [0])
        for text, holdout in variants:
            match = next((v for v in rows if v.text == text), None)
            if match is None:
                top += 1
                match = PhraseVariant(intent_id=intent.id, text=text,
                                      difficulty=Difficulty.clear, holdout=holdout,
                                      status=ContentStatus.draft, version=top)
                db.add(match)
                db.flush()
                made["variants"] += 1
            touched.append(match)
        del existing

        row = db.scalar(select(ModelAnswer).where(ModelAnswer.intent_id == intent.id,
                                                  ModelAnswer.text == answer))
        if row is None:
            row = ModelAnswer(intent_id=intent.id, text=answer, status=ContentStatus.draft)
            db.add(row)
            db.flush()
            made["answers"] += 1
        touched.append(row)

        for text in repairs:
            r = db.scalar(select(RepairLine).where(RepairLine.text == text))
            if r is None:
                r = RepairLine(intent_id=intent.id, text=text, status=ContentStatus.draft)
                db.add(r)
                db.flush()
                made["repairs"] += 1
            touched.append(r)

        c = db.scalar(select(CoachingContent).where(CoachingContent.intent_id == intent.id,
                                                    CoachingContent.locale == "uz"))
        if c is None:
            c = CoachingContent(intent_id=intent.id, locale="uz", explanation=uz,
                                review_status=ContentStatus.draft)
            db.add(c)
            db.flush()
            made["coaching"] += 1
        elif c.explanation.startswith("[draft uz coaching"):
            # the seed's placeholder — replace it, it was never real content
            c.explanation = uz
        touched.append(c)

    _sync_scenario(db)

    if args.release:
        for item in touched:
            before = m15content.status_of(item)
            _release(db, item, args.actor)
            if before is not ContentStatus.released:
                released += 1

    db.commit()
    from sqlalchemy import func as _func
    total = db.scalar(select(_func.count(Intent.id)))
    released_intents = db.scalar(
        select(_func.count(_func.distinct(PhraseVariant.intent_id))).where(
            PhraseVariant.status == ContentStatus.released
        )
    )
    print(f"  intents on this box: {total} ({released_intents} with released phrasings)")
    print(f"  created: {made}")
    print(f"  released this run: {released}")
    db.close()


if __name__ == "__main__":
    main()
