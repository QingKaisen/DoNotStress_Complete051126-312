# INF1103-P3-Team1-DoNotStress
## Problem
University students often don't notice their stress building until it affects their studies, sleep or wellbeing, and many don't reach out for support early. Existing counselling services rely on students coming forward themselves.

## Objectives
- Give SIT students a quick, private stress check-in based on validated research questions (PSS-4, MSPSS and others) on a 1–5 scale.
- Use Gemini AI to analyse each check-in and return a structured stress score, tier and personalised tips.
- Point students to SIT Counselling and helplines, especially when stress is high or a safety concern is detected.
- Let SIT wellbeing staff view records through an admin-only page to spot students who may need support.

## Target users
SIT students (check-ins) and SIT wellbeing staff (admin records view).

## Industry relevance
Student mental health is a growing priority for universities. DoNotStress shows how AI can support early-warning wellbeing screening, while staying non-diagnostic and protecting student privacy (Student IDs are never sent to the AI).


Student wellbeing app with a campus check-in UI and the team's AI/backend pipeline.

## Run locally

Open this project folder in the VS Code terminal:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Open http://127.0.0.1:5000. If only the Python launcher is available, use `py -m venv .venv` for the first command.

`main.py` is the single entry point for the frontend and backend. For Flask CLI or WSGI tools, use `main:app`, for example:

```powershell
.\.venv\Scripts\python.exe -m flask --app main run
```

## AI configuration

Set `GEMINI_API_KEY` in your local environment or a local `.env` file before starting. A stable `FLASK_SECRET_KEY` is recommended; otherwise each restart generates a fresh key and expires sessions. `PORT` changes the default port. `DONOTSTRESS_DATA_PATH` optionally changes the save-file location.

Do not commit `.env`, API keys, saved student data, or Python cache files. No API key is embedded in the frontend.

The interface opens without a key, but assessment requires Gemini. Missing credentials, provider errors, or invalid responses show a retry message and support contacts; there is no fabricated sample result or Logic-only fallback.

## Evidence questionnaire v3 (single 1–5 scale)

The questionnaire follows section 2 of `donotstress_question_evidence.docx` (9 October 2026).
`survey.py` owns question wording, options, chapter explanations and the reflection safety check. Gemini (via `ai_manager.py`) produces the score; the `logic_manager` package (`LogicManager`) only re-checks it against the formula as an audit, rejecting mismatches over 0.01 (saved as pending), and never substitutes its own score. `logic_manager` also owns context flags and factor cards.
The browser receives the same definitions from Flask. Required answers start unselected, except the sleep slider, which starts at 7 hours and uses that position as the answer.

1. **Your month:** Student ID (seven ASCII digits beginning with 2), then all four PSS-4 items as full sentences, each beginning "In the past month, how often have you felt…". The chapter title is "Start with the bigger picture." Each item is 1 (never) to 5 (very often). Items 2 and 3 are reverse-scored.
2. **Rest and recovery:** typical sleep this week is a 0–14 hour slider in 0.5 steps. Scoring converts hours to 1–5 stress: 8+ hours = 1, 7 to under 8 = 2, 6 to under 7 = 3, 5 to under 6 = 4, under 5 = 5. Sleep quality is 1 (very good) to 5 (very bad).
3. **Study demands:** workload and catch-up items, both required, 1 (strongly disagree) to 5 (strongly agree). Direction is adapted.
4. **Money pressures:** IFDFW item 8 adapted to a 1–5 slider, 1 (no stress at all) to 5 (overwhelming stress). Higher means MORE distress. The displayed position is the answer; there is no separate confirm button. The hint reads "Higher numbers mean more financial stress."
5. **Your support:** MSPSS friends and family items, both required, 1 (strongly disagree) to 5 (strongly agree). Reverse-scored in the stress score.
6. **Reflection:** optional text, up to 2,000 characters; not scored, sent to Gemini, or saved.

Eleven required questions, plus optional reflection. ID is not scored. Each question has equal weight in the average.

### Scoring and interpretation

- Typical sleep is entered in hours and converted to 1–5 only when scoring (8+ hours = 1, 7 to under 8 = 2, 6 to under 7 = 3, 5 to under 6 = 4, under 5 = 5). Every other item is answered on a 1–5 scale. Positively worded items (`pss_2`, `pss_3`, `mspss_friends`, `mspss_family`) are scored as `6 - answer`.
- `stress_score` = average of all 11 required answers after that conversion and reverse scoring, range 1.0–5.0. Each answer has equal weight.
- Team guidance bands: below 2.5 Low ("You're doing ok"), 2.5–3.5 Moderate ("Worth a check-in"), above 3.5 High ("Please reach out"). NOT clinical cut-offs or a diagnosis.
- Context flags (choose tips and factor cards only): sleep under 6 hours OR quality >=4; workload >=4; finance >=4; raw support mean of friends and family <2.5.
- Catch-up counts in the average. It does not raise the workload flag by itself.
- A basic local crisis-language check highlights “Please reach out” and support contacts without changing the stress score. It can miss language or produce false positives; it is not a safety assessment and no person monitors reflections.
- `risk_score` is retained for backend compatibility as `(stress_score - 1) / 4`, NOT a probability. AI cannot replace the computed band. Tips combine relevant context suggestions with validated AI tip IDs.

Sleep items are adapted; PAS and MSPSS are selected items, not complete scales. The combined questionnaire and its guidance bands have not been clinically validated. Factor cards describe rest, study, money, and support. The average score is stored for the admin table.

### Sources and permissions

Questionnaire pages do not show a source line. The home page has a short "Backed by research" note and this compact line: Sources: Cohen et al. (1983); Buysse et al. (1989); Bedewy & Gabriel (2015); Prawitz et al. (2006); Zimet et al. (1988). Full citations:

- Cohen, S., Kamarck, T., & Mermelstein, R. (1983). A global measure of perceived stress. *Journal of Health and Social Behavior, 24*(4), 385–396. https://doi.org/10.2307/2136404. PSS-4 items, adapted to a 1–5 scale. Items 2 and 3 are reverse-scored. Reverse coding checked at https://www.cmu.edu/dietrich/psychology/stress-immunity-disease-lab/scales/html/pssscoring.html.
- Buysse, D. J., Reynolds, C. F., Monk, T. H., Berman, S. R., & Kupfer, D. J. (1989). The Pittsburgh Sleep Quality Index: A new instrument for psychiatric practice and research. *Psychiatry Research, 28*(2), 193–213. https://doi.org/10.1016/0165-1781(89)90047-4. Two sleep items only; recall shortened to one week. This is not a PSQI score.
- Bedewy, D., & Gabriel, A. (2015). Examining perceptions of academic stress and its sources among university students: The Perception of Academic Stress Scale. *Health Psychology Open, 2*(2). https://doi.org/10.1177/2055102915596714. CC BY-NC 3.0. Selected items; response direction adapted to increasing agreement.
- Prawitz, A. D., Garman, E. T., Sorhaindo, B., O'Neill, B., Kim, J., & Drentea, P. (2006). InCharge Financial Distress/Financial Well-Being Scale: Development, administration, and score interpretation. *Financial Counseling and Planning, 17*(1), 34–50. https://www.afcpe.org/wp-content/uploads/2018/10/vol1714.pdf. Item 8, adapted to a 1–5 slider.
- Zimet, G. D., Dahlem, N. W., Zimet, S. G., & Farley, G. K. (1988). The Multidimensional Scale of Perceived Social Support. *Journal of Personality Assessment, 52*(1), 30–41. https://doi.org/10.1207/s15327752jpa5201_2. Friends and family items only, adapted to five points and reverse-scored in the stress score. Not an MSPSS total.

The supplied brief identifies permissions to resolve before distribution: PSS permission through Mapi/ePROVIDE and the copyrighted IFDFW wording. PSQI educational/research use is non-commercial; adaptations and commercial use need appropriate review. Attribution does not itself grant permission. No permission request has been sent by this implementation.

Support contacts are always available, including without an AI result, in the page footer and in the check-in support panels: SIT Counselling 24-hour helpline **6592 2030** (SITCounselling@SingaporeTech.edu.sg), Samaritans of Singapore **1767** and CareText **9151 1767** (WhatsApp), and national mindline **1771**. SOS and mindline are 24-hour services, verified 9 October 2026 at https://www.sos.org.sg/contact-us/ and https://www.moh.gov.sg/newsroom/national-mindline-1771-to-provide--round-the-clock-support-for-mental-health/.

## Flow and storage

`main.py` validates with `io_manager`, runs `ai_manager.analyse_student` (with the prompt rules and score check from `logic_manager.AIScoreVerifier`), then `LogicManager.evaluate`, and saves `EvaluationResult.to_record()`. Student-facing results and tips use the I/O formatters. Support contacts come from the existing I/O module. Assessment is AI-assisted wellbeing guidance, not a medical diagnosis.

Before submission, the review step says that answers are used to share a few suggestions, while the student ID stays private and anything written in the reflection box is not stored. The server checks reflection text then discards it; only the boolean safety flag remains in a result. Numeric answers are sent for suggestions; the ID and reflection are not. Request bodies must not be logged by a deployment proxy. After a successful check-in the result is shown at `/result`. Session cookies contain only opaque identifiers and a CSRF token, not answers. The in-memory result expires after 30 minutes; the saved file is separate. `/garden` redirects to the home page.

Every completed check-in is saved automatically to `data/student_records.json` (or the file named by `DONOTSTRESS_DATA_PATH`) through `data_manager`. Reflection text is never stored. A finished AI result is written with `save_record`. If Gemini cannot complete the check-in, the answers are still saved as a pending record and the student is asked to try again; no result page is shown. Refreshing `/result` does not write a second copy.

This is a single-process local app. A production deployment needs a shared server-side session/record store, authentication and access controls appropriate to student records, and a production server.

## Files

- `main.py`: combined Flask entry point and orchestration.
- `io_manager.py`, `ai_manager.py`, `data_manager.py`: existing team layers.
- `logic_manager/`: object-oriented Logic Manager package (`LogicManager`, business rules, scoring and the score check used by the AI layer).
- `templates/base.html`, `templates/checkin.html`: page shell.
- `static/style.css`, `static/campus.js`: campus UI, sliders, review, and results.
- Legacy result/error templates remain available; the current interface renders these states in the shared campus UI.

## Required functions

| Manager file | Required functions |
| --- | --- |
| `ai_manager.py` | `build_prompt`, `call_api`, `parse_response`, `validate_response` |
| `logic_manager/` | `LogicManager.evaluate`, `LogicManager.score`, `LogicManager.route` |
| `data_manager.py` | `save`, `load`, `query(filter_fn)` |
| `io_manager.py` | `display_record`, `display_list`, `display_result` |

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests inject a simulated Gemini response but run the real schema validator, Logic finalizer, I/O formatters, and data saver. They make no network calls and only save synthetic test data in a temporary directory.

## Saved check-ins and detailed results

The default is **Student view**. Students can complete a check-in and view their own current result at `/result`. Every completed check-in is saved automatically. They cannot open the saved-records table or fetch its data.

Use **Admin sign in** (or `/admin/login`) with the fixed coursework account:

- Username: `admin`
- Password: `DoNotStress2026!`

The credential check runs on the server; `main.py` contains a password hash. Credentials are not embedded in the login page, JavaScript or browser configuration. This shared, documented demo account is for the local prototype, not public deployment with real student records.

Successful sign-in opens **Saved records** at `/records`. The header is rendered from the server session on every page. While that session is valid, Home and Check-in still show **Admin view** and **Log out**. `/records` is admin-only and redirects unauthenticated users to sign-in, and `/api/records` returns 401 before loading any records. Admin access expires after 30 minutes. **Log out** revokes the server-side admin token, clears the current browser session, and returns to Student view. Restarting the app revokes admin sessions. Five failed sign-in attempts within five minutes temporarily block further attempts from that address.

Admins can search any part of a Student ID and combine a tier filter (You're doing ok, Worth a check-in, Please reach out) with the cohort-year filter. Clear Filters restores the full list. Cohort year uses the first two ID digits (26 means 2026); dates display in Singapore time. Saved check-ins are shown, including pending records from a check-in Gemini could not finish. Load errors are distinguished from an empty result. The history endpoint omits free-text concerns and AI reasoning.

The table shows Student ID, stress score out of 5, tier (with the same green, amber and red colours), then all 11 answers as numbers only: Control (pss_1), Coping (pss_2), Going well (pss_3), Piling up (pss_4), sleep in hours, sleep quality, workload, catch-up, finances, friends, family, then status (Evaluated, or Pending when AI could not finish) and date saved. Hovering an answer shows the word label, for example `3 · Sometimes`. A key above the table reads "Answers: 1 = lowest, 5 = highest · Sleep in hours". Records whose `survey_version` is not `evidence-v3` are skipped, including older /10 and evidence-v2 saves. Before a demo, delete `data/student_records.json` (or the file named by `DONOTSTRESS_DATA_PATH`) so the table starts empty. Do not commit that file.

Student results at `/result` show a short wellbeing message, four factor cards, and a few suggestions. A factor shows "Worth some attention" only when it is flagged. The raw stress score stays in the admin table, not on the student page. Colours accompany the tier names. New records carry `survey_version: evidence-v3`.
