"""DoNotStress desktop GUI.

A calm, multi-step check-in that reuses the same managers as the web app:
  StudentIO / survey  →  GeminiAIManager  →  LogicManager  →  JsonRecordRepository

Run:
    python gui.py

If GEMINI_API_KEY is set, the real AI path is used. Otherwise the app
runs in clearly-labelled demo mode so the check-in still completes.
"""

from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from dotenv import load_dotenv

import survey
from ai_manager import AIProcessingError, GeminiAIManager
from data_manager import DataStoreError, JsonRecordRepository
from io_manager import ADVISOR_CONTACTS, SOFT_LABEL_COPY, StudentIO, TIPS_ALLOWLIST
from logic_manager import AIScoreVerifier, LogicManager, LogicManagerError, ScoreCalculator

load_dotenv()

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

# SGH-inspired institutional theme. Light is the default; dark is available.
THEMES = {
    "light": {
        "bg": "#fafafa", "panel": "#ffffff", "ink": "#202020", "sub": "#5c656b",
        "accent": "#009639", "soft": "#f0f7f2", "line": "#e4e7ea",
        "low": "#e8f5e9", "mod": "#fff8e1", "high": "#fdecea", "flag": "#f5f5f5",
    },
    "dark": {
        "bg": "#141816", "panel": "#1c2420", "ink": "#edf4ec", "sub": "#b4c4b8",
        "accent": "#4caf6e", "soft": "#243029", "line": "#3a4540",
        "low": "#1e3a24", "mod": "#3d3520", "high": "#3d2420", "flag": "#2a2a2a",
    },
}
# Active palette. toggle_theme() reassigns these so existing widgets pick up the theme.
BG = THEMES["light"]["bg"]
PANEL = THEMES["light"]["panel"]
INK = THEMES["light"]["ink"]
SUB = THEMES["light"]["sub"]
ACCENT = THEMES["light"]["accent"]
SOFT = THEMES["light"]["soft"]
LILAC = THEMES["light"]["soft"]
LINE = THEMES["light"]["line"]
LOW = THEMES["light"]["low"]
MOD = THEMES["light"]["mod"]
HIGH = THEMES["light"]["high"]
FLAG = THEMES["light"]["flag"]


def _tier_color(category: str) -> str:
    return {"Low": LOW, "Moderate": MOD, "High": HIGH}.get(category, LILAC)


# ---------------------------------------------------------------------------
# Demo AI (used only when no API key is available)
# ---------------------------------------------------------------------------

def _demo_reply(answers: dict, calculator: ScoreCalculator) -> dict:
    """Build a schema-valid reply from Logic's own arithmetic.

    Clearly a stand-in. The real app never invents an AI result; the desktop
    GUI uses this only so a check-in can finish without a key.
    """
    from logic_manager import StudentAnswers

    student = StudentAnswers.from_mapping(answers)
    items = calculator.scored_items(student)
    score = calculator.stress_score(student)
    tier = calculator.tier_for(score)
    stressors = []
    if answers.get("sleep_hours_avg", 8) < 6 or answers.get("sleep_quality", 1) >= 4:
        stressors.append("sleep_deprivation")
    if answers.get("pas_workload", 1) >= 4:
        stressors.append("academic_overload")
    if answers.get("fin_stress", 1) >= 4:
        stressors.append("financial_pressure")
    if calculator.support_mean(student) < 2.5:
        stressors.append("low_social_support")
    tips = []
    if "sleep_deprivation" in stressors:
        tips.append("sleep_routine")
    if "academic_overload" in stressors:
        tips.append("workload_chunks")
    if "financial_pressure" in stressors:
        tips.append("money_worries")
    if not tips:
        tips.append("short_breaks")
    return {
        "scored_items": items,
        "stress_score": score,
        "risk_category": tier.category,
        "primary_stressors": stressors,
        "confidence": 0.7,
        "reasoning": (
            "This is a local demo summary based on your answers. "
            "It is not a clinical assessment. Look after the basics that help you most."
        ),
        "soft_label": tier.soft_label,
        "tips": tips[:3],
        "speak_prominence": tier.speak_prominence,
        "source": "demo",
    }


class DemoAI:
    """Minimal stand-in that satisfies the same analyse() shape."""

    def __init__(self, calculator: ScoreCalculator, verifier: AIScoreVerifier) -> None:
        self._calculator = calculator
        self._verifier = verifier

    def analyse(self, student: dict) -> dict:
        reply = _demo_reply(student, self._calculator)
        problem = self._verifier.verify(reply, student)
        if problem:
            raise AIProcessingError("invalid_response", problem)
        return {**student, **reply}


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

class DoNotStressApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("DoNotStress · Campus check-in")
        self.geometry("980x720")
        self.minsize(820, 600)
        self.configure(bg=BG)

        # Institutional accent bar, in the spirit of a hospital site header.
        accent = tk.Frame(self, bg=ACCENT, height=4)
        accent.pack(fill="x")

        self.calculator = ScoreCalculator()
        self.logic = LogicManager(calculator=self.calculator)
        self.verifier = AIScoreVerifier(self.calculator)
        self.io = StudentIO()
        self.store = JsonRecordRepository(os.environ.get("DONOTSTRESS_DATA_PATH"))
        self.demo_mode = not bool(os.environ.get("GEMINI_API_KEY", "").strip())
        self.ai = (
            DemoAI(self.calculator, self.verifier)
            if self.demo_mode
            else GeminiAIManager(verifier=self.verifier)
        )

        self.answers: dict = {}
        self.step = 0
        self.result_record: dict | None = None
        self.theme_name = "light"
        self.colors = THEMES[self.theme_name]

        self._build_chrome()
        self.show_home()

    # -- chrome -------------------------------------------------------------

    def _build_chrome(self) -> None:
        header = tk.Frame(self, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        header.pack(fill="x")
        tk.Label(
            header, text="+  DoNotStress", font=("Segoe UI", 16, "bold"),
            bg=PANEL, fg=INK,
        ).pack(side="left", padx=18, pady=12)
        mode = "Demo mode · no API key" if self.demo_mode else "AI-assisted check-in"
        tk.Label(header, text=mode, font=("Segoe UI", 10), bg=PANEL, fg=SUB).pack(side="left", padx=8)
        tk.Button(
            header, text="Home", command=self.show_home,
            bg=PANEL, fg=INK, relief="flat", padx=12, pady=6, font=("Segoe UI", 10),
        ).pack(side="right", padx=8, pady=10)
        tk.Button(
            header, text="Records", command=self.show_records,
            bg=self.colors["panel"], fg=self.colors["ink"], relief="flat", padx=12, pady=6, font=("Segoe UI", 10),
        ).pack(side="right", padx=4, pady=10)
        self.theme_btn = tk.Button(
            header, text="Dark", command=self.toggle_theme,
            bg=self.colors["panel"], fg=self.colors["ink"], relief="flat", padx=12, pady=6, font=("Segoe UI", 10),
        )
        self.theme_btn.pack(side="right", padx=4, pady=10)

        self.body = tk.Frame(self, bg=BG)
        self.body.pack(fill="both", expand=True, padx=18, pady=12)

        footer = tk.Frame(self, bg=PANEL)
        footer.pack(fill="x")
        tk.Label(
            footer,
            text=(
                f"Need to talk?  SIT Counselling {ADVISOR_CONTACTS['helpline']}  ·  "
                f"{ADVISOR_CONTACTS['email']}  ·  SOS {ADVISOR_CONTACTS['sos']}  ·  "
                f"mindline {ADVISOR_CONTACTS['mindline']}"
            ),
            font=("Segoe UI", 9), bg=PANEL, fg=SUB,
        ).pack(pady=8)

    def toggle_theme(self) -> None:
        global BG, PANEL, INK, SUB, ACCENT, SOFT, LILAC, LINE, LOW, MOD, HIGH, FLAG
        self.theme_name = "dark" if self.theme_name == "light" else "light"
        c = THEMES[self.theme_name]
        self.colors = c
        BG, PANEL, INK, SUB = c["bg"], c["panel"], c["ink"], c["sub"]
        ACCENT, SOFT, LINE = c["accent"], c["soft"], c["line"]
        LILAC = c["soft"]
        LOW, MOD, HIGH, FLAG = c["low"], c["mod"], c["high"], c["flag"]
        self.theme_btn.config(text="Light" if self.theme_name == "dark" else "Dark")
        # Rebuild chrome and the current view so the new palette applies.
        for child in self.winfo_children():
            child.destroy()
        self.configure(bg=BG)
        accent = tk.Frame(self, bg=ACCENT, height=4)
        accent.pack(fill="x")
        self._build_chrome()
        if self.result_record:
            self.show_result(self.result_record, demo=self.demo_mode)
        elif self.answers:
            self.show_step()
        else:
            self.show_home()

    def _clear(self) -> None:
        for child in self.body.winfo_children():
            child.destroy()

    # -- home ---------------------------------------------------------------

    def show_home(self) -> None:
        self._clear()
        self.answers = {}
        self.step = 0
        self.result_record = None

        card = tk.Frame(self.body, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        card.pack(fill="both", expand=True, padx=20, pady=12)

        # Hero video section
        video_frame = tk.Frame(card, bg="#000", height=200)
        video_frame.pack(fill="x", padx=20, pady=(12, 8))
        video_frame.pack_propagate(False)
        try:
            from tkinter import PhotoImage
            poster = PhotoImage(file="static/video/poster.png")
            poster = poster.subsample(2, 2)
            self._poster = poster
            tk.Label(video_frame, image=poster, bg="#000").pack(fill="both", expand=True)
        except Exception:
            tk.Label(video_frame, text="A calm moment for your wellbeing", font=("Segoe UI", 14), bg="#000", fg="#fff").pack(expand=True)
        tk.Label(card, text="A private check-in, grounded in research.", font=("Segoe UI", 10), bg=PANEL, fg=SUB).pack(anchor="w", padx=28, pady=(0, 8))

        top = tk.Frame(card, bg=PANEL)
        top.pack(fill="x", padx=20, pady=(20, 8))

        left = tk.Frame(top, bg=PANEL)
        left.pack(side="left", fill="both", expand=True, padx=(8, 16))
        tk.Label(left, text="STUDENT WELLBEING", font=("Segoe UI", 9, "bold"), bg=PANEL, fg=ACCENT).pack(anchor="w")
        tk.Label(left, text="A private stress check-in\nfor SIT students.", font=("Segoe UI", 22, "bold"), bg=PANEL, fg=INK, justify="left").pack(anchor="w", pady=(4, 10))
        tk.Label(left, text="Notice how stress, sleep, study load and support are affecting you. Get a structured summary and a few practical next steps. Not a diagnosis.", font=("Segoe UI", 11), bg=PANEL, fg=SUB, wraplength=380, justify="left").pack(anchor="w")
        actions = tk.Frame(left, bg=PANEL)
        actions.pack(anchor="w", pady=(14, 4))
        tk.Button(actions, text="Start check-in", command=self.start_checkin, bg=ACCENT, fg="white", relief="flat", font=("Segoe UI", 11, "bold"), padx=16, pady=8).pack(side="left", padx=(0, 8))
        tk.Label(actions, text="11 questions · about 3 minutes", font=("Segoe UI", 9), bg=PANEL, fg=SUB).pack(side="left")

        right = tk.Frame(top, bg=SOFT, width=280)
        right.pack(side="right", fill="y", padx=(8, 8))
        right.pack_propagate(False)
        tk.Label(right, text="What you can expect", font=("Segoe UI", 12, "bold"), bg=SOFT, fg=INK).pack(anchor="w", padx=12, pady=(12, 8))
        for title, body in (
            ("Private answers", "Research-based questions on stress, rest, study, finances and support."),
            ("Clear summary", "A structured score, tier and suggestions. Wellbeing guidance only."),
            ("Support nearby", "SIT Counselling and national helplines are always one tap away."),
        ):
            tk.Label(right, text=title, font=("Segoe UI", 10, "bold"), bg=SOFT, fg=INK).pack(anchor="w", padx=12, pady=(6, 0))
            tk.Label(right, text=body, font=("Segoe UI", 9), bg=SOFT, fg=SUB, wraplength=240, justify="left").pack(anchor="w", padx=12, pady=(0, 4))

        features = tk.Frame(card, bg=PANEL)
        features.pack(fill="x", padx=20, pady=(8, 8))
        for title, body in (
            ("01  Early check-in", "Spot building stress before it affects studies, sleep or wellbeing."),
            ("02  Research-based", "Questions adapted from PSS-4, PSQI, PAS, IFDFW and MSPSS."),
            ("03  Privacy first", "Your ID stays with SIT staff. It is never sent to the AI."),
        ):
            box = tk.Frame(features, bg=SOFT)
            box.pack(side="left", fill="both", expand=True, padx=4)
            tk.Label(box, text=title, font=("Segoe UI", 10, "bold"), bg=SOFT, fg=INK).pack(anchor="w", padx=12, pady=(10, 2))
            tk.Label(box, text=body, font=("Segoe UI", 9), bg=SOFT, fg=SUB, wraplength=200, justify="left").pack(anchor="w", padx=12, pady=(0, 10))

        note = tk.Frame(card, bg=SOFT)
        note.pack(fill="x", padx=28, pady=(4, 16))
        tk.Label(note, text="Wellbeing guidance only. Not a medical diagnosis. Student IDs are never sent to the AI.", font=("Segoe UI", 10), bg=SOFT, fg=INK).pack(anchor="w", padx=14, pady=10)

    # -- check-in -----------------------------------------------------------

    def start_checkin(self) -> None:
        self.answers = {"student_id": "", "feelings_text": ""}
        for q in survey.QUESTIONS:
            self.answers[q["key"]] = None
        self.step = 0
        self.show_step()

    def show_step(self) -> None:
        self._clear()
        review = self.step >= len(survey.SECTIONS)
        if review:
            self._show_review()
            return

        section = survey.SECTIONS[self.step]
        outer = tk.Frame(self.body, bg=BG)
        outer.pack(fill="both", expand=True)

        rail = tk.Frame(outer, bg=PANEL, width=200, highlightbackground=LINE, highlightthickness=1)
        rail.pack(side="left", fill="y", padx=(0, 12))
        rail.pack_propagate(False)
        tk.Label(
            rail, text="CHAPTERS", font=("Segoe UI", 9, "bold"), bg=PANEL, fg=ACCENT,
        ).pack(anchor="w", padx=12, pady=(14, 8))
        for i, sec in enumerate(survey.SECTIONS):
            mark = "✓" if i < self.step else str(i + 1)
            color = ACCENT if i == self.step else (INK if i < self.step else SUB)
            weight = "bold" if i == self.step else "normal"
            tk.Label(
                rail, text=f"  {mark}   {sec['title']}",
                font=("Segoe UI", 10, weight),
                bg=PANEL, fg=color, anchor="w",
            ).pack(fill="x", padx=8, pady=4)
        progress = tk.Frame(rail, bg=PANEL)
        progress.pack(fill="x", padx=12, pady=(20, 8))
        tk.Frame(progress, bg=LINE, height=1).pack(fill="x", pady=(0, 8))
        pct = int(self.step / len(survey.SECTIONS) * 100)
        tk.Label(progress, text=f"{pct}%", font=("Segoe UI", 18, "bold"), bg=PANEL, fg=ACCENT).pack(anchor="w")
        tk.Label(progress, text="complete", font=("Segoe UI", 9), bg=PANEL, fg=SUB).pack(anchor="w")

        form = tk.Frame(outer, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        form.pack(side="left", fill="both", expand=True)

        canvas = tk.Canvas(form, bg=PANEL, highlightthickness=0)
        scroll = ttk.Scrollbar(form, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=PANEL)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        tk.Label(inner, text=section["period"], font=("Segoe UI", 10), bg=SOFT, fg=INK).pack(anchor="w", padx=20, pady=(16, 4))
        tk.Label(inner, text=section["heading"], font=("Segoe UI", 18, "bold"), bg=PANEL, fg=INK).pack(anchor="w", padx=20, pady=(4, 6))
        tk.Label(inner, text=section["intro"], font=("Segoe UI", 11), bg=PANEL, fg=SUB, wraplength=560, justify="left").pack(anchor="w", padx=20, pady=(0, 8))

        if self.step == 0:
            self._student_id_field(inner)

        self._widgets = {}
        for key in section["keys"]:
            self._question_field(inner, survey.QUESTION_MAP[key])

        if self.step == 5:
            self._reflection_field(inner)

        self._error = tk.Label(inner, text="", font=("Segoe UI", 10), bg=PANEL, fg="#ac342c")
        self._error.pack(anchor="w", padx=20, pady=(4, 0))

        nav = tk.Frame(inner, bg=PANEL)
        nav.pack(fill="x", padx=20, pady=16)
        back_label = "← Home" if self.step == 0 else "← Back"
        tk.Button(nav, text=back_label, command=self._back, bg=SOFT, fg=INK, relief="flat", padx=12, pady=8).pack(side="left")
        next_label = "Review my check-in →" if self.step == len(survey.SECTIONS) - 1 else "Continue →"
        tk.Button(nav, text=next_label, command=self._next, bg=ACCENT, fg="white", relief="flat", padx=14, pady=8).pack(side="right")

    def _student_id_field(self, parent: tk.Frame) -> None:
        box = tk.Frame(parent, bg=PANEL)
        box.pack(fill="x", padx=20, pady=8)
        tk.Label(box, text="Student ID", font=("Segoe UI", 11, "bold"), bg=PANEL, fg=INK).pack(anchor="w")
        entry = tk.Entry(box, font=("Segoe UI", 12), width=20)
        entry.insert(0, self.answers.get("student_id", ""))
        entry.pack(anchor="w", pady=4)
        tk.Label(box, text="7 digits starting with 2. Never sent to the AI.", font=("Segoe UI", 9), bg=PANEL, fg=SUB).pack(anchor="w")
        self._id_entry = entry

    def _question_field(self, parent: tk.Frame, q: dict) -> None:
        card = tk.Frame(parent, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        card.pack(fill="x", padx=20, pady=8)
        tk.Label(card, text=q["prompt"], font=("Segoe UI", 11, "bold"), bg=PANEL, fg=INK, wraplength=540, justify="left").pack(anchor="w", padx=12, pady=(10, 6))

        if q.get("kind") == "slider":
            value = self.answers.get(q["key"])
            if value is None:
                value = q.get("default", q["min"])
            var = tk.DoubleVar(value=float(value))
            shown = tk.Label(card, text=self._slider_text(q, var.get()), font=("Segoe UI", 16), bg=PANEL, fg=INK)
            shown.pack(anchor="w", padx=12)
            scale = tk.Scale(
                card, from_=q["min"], to=q["max"], resolution=q.get("step", 1),
                orient="horizontal", variable=var, showvalue=False, length=420,
                bg=PANEL, highlightthickness=0, troughcolor=SOFT,
                command=lambda v, qq=q, lab=shown: lab.config(text=self._slider_text(qq, float(v))),
            )
            scale.pack(anchor="w", padx=12, pady=(0, 6))
            ends = tk.Frame(card, bg=PANEL)
            ends.pack(fill="x", padx=12, pady=(0, 10))
            tk.Label(ends, text=f"{q['min']} · {q.get('low', '')}", font=("Segoe UI", 9), bg=PANEL, fg=SUB).pack(side="left")
            tk.Label(ends, text=f"{q['max']} · {q.get('high', '')}", font=("Segoe UI", 9), bg=PANEL, fg=SUB).pack(side="right")
            self._widgets[q["key"]] = var
        else:
            var = tk.IntVar(value=self.answers.get(q["key"]) or 0)
            row = tk.Frame(card, bg=PANEL)
            row.pack(fill="x", padx=8, pady=(0, 10))
            for i, label in enumerate(q["options"]):
                value = i + q["min"]
                rb = tk.Radiobutton(
                    row, text=f"{value}\n{label}", value=value, variable=var,
                    bg=PANEL, fg=INK, selectcolor=SOFT, indicatoron=False,
                    font=("Segoe UI", 9), width=12, pady=6, relief="flat",
                )
                rb.pack(side="left", padx=3)
            self._widgets[q["key"]] = var

    def _slider_text(self, q: dict, value: float) -> str:
        unit = q.get("unit", "")
        shown = int(value) if float(value).is_integer() else value
        return f"{shown} {unit}".strip()

    def _reflection_field(self, parent: tk.Frame) -> None:
        box = tk.Frame(parent, bg=PANEL)
        box.pack(fill="x", padx=20, pady=8)
        tk.Label(box, text="Anything on your mind? (optional)", font=("Segoe UI", 11, "bold"), bg=PANEL, fg=INK).pack(anchor="w")
        text = tk.Text(box, height=4, width=60, font=("Segoe UI", 11), wrap="word")
        text.insert("1.0", self.answers.get("feelings_text", ""))
        text.pack(anchor="w", pady=4)
        tk.Label(
            box,
            text="This space is just for you. It isn't scored or saved. A basic word check can show support contacts.",
            font=("Segoe UI", 9), bg=PANEL, fg=SUB, wraplength=540, justify="left",
        ).pack(anchor="w")
        self._reflection = text

    def _collect_step(self) -> str:
        if self.step == 0 and hasattr(self, "_id_entry"):
            self.answers["student_id"] = self._id_entry.get().strip()
        if self.step == 5 and hasattr(self, "_reflection"):
            self.answers["feelings_text"] = self._reflection.get("1.0", "end").strip()
        section = survey.SECTIONS[self.step]
        for key in section["keys"]:
            widget = self._widgets.get(key)
            if widget is None:
                continue
            value = widget.get()
            if isinstance(value, float) and value.is_integer() and survey.QUESTION_MAP[key].get("kind") != "slider":
                value = int(value)
            if survey.QUESTION_MAP[key].get("kind") != "slider" and value == 0:
                return f"Please answer “{survey.QUESTION_MAP[key]['label']}”."
            self.answers[key] = value
        return ""

    def _back(self) -> None:
        if self.step == 0:
            self.show_home()
            return
        self._collect_step()
        self.step -= 1
        self.show_step()

    def _next(self) -> None:
        problem = self._collect_step()
        if problem:
            self._error.config(text=problem)
            return
        if self.step == 0:
            ok, sid = self.io.validate_form({"student_id": self.answers["student_id"], **{k: 1 for k in survey.QUESTION_MAP}})
            # validate_form needs all answers; check ID alone
            if not __import__("re").fullmatch(r"2\d{6}", self.answers["student_id"]):
                self._error.config(text="Enter a 7-digit student ID starting with 2.")
                return
        self.step += 1
        self.show_step()

    def _show_review(self) -> None:
        outer = tk.Frame(self.body, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text="A moment to look back.", font=("Segoe UI", 18, "bold"), bg=PANEL, fg=INK).pack(anchor="w", padx=20, pady=(16, 4))
        tk.Label(
            outer,
            text="Check your answers. After you submit, we'll look at them and share a few suggestions. Your ID is never sent to the AI. Reflection text is not stored.",
            font=("Segoe UI", 11), bg=PANEL, fg=SUB, wraplength=700, justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 10))
        tk.Label(outer, text=f"Student ID: {self.answers.get('student_id', '')}", font=("Segoe UI", 11, "bold"), bg=PANEL, fg=INK).pack(anchor="w", padx=20)

        canvas = tk.Canvas(outer, bg=PANEL, highlightthickness=0)
        scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=PANEL)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True, padx=12)
        scroll.pack(side="right", fill="y")

        for section in survey.SECTIONS:
            tk.Label(inner, text=section["title"], font=("Segoe UI", 12, "bold"), bg=PANEL, fg=INK).pack(anchor="w", pady=(10, 2))
            for key in section["keys"]:
                q = survey.QUESTION_MAP[key]
                value = self.answers.get(key)
                shown = value if value is not None else "—"
                tk.Label(inner, text=f"{q['label']}:  {shown}", font=("Segoe UI", 10), bg=PANEL, fg=SUB).pack(anchor="w")

        nav = tk.Frame(self.body, bg=BG)
        nav.pack(fill="x", pady=8)
        tk.Button(nav, text="← Back", command=lambda: self._go_step(len(survey.SECTIONS) - 1), bg=SOFT, fg=INK, relief="flat", padx=12, pady=8).pack(side="left", padx=8)
        tk.Button(nav, text="Get my check-in →", command=self.submit, bg=ACCENT, fg="white", relief="flat", padx=14, pady=8).pack(side="right", padx=8)

    def _go_step(self, step: int) -> None:
        self.step = step
        self.show_step()

    # -- submit -------------------------------------------------------------

    def submit(self) -> None:
        ok, clean = self.io.validate_form(self.answers)
        if not ok:
            messagebox.showerror("Check your answers", "\n".join(f"{k}: {v}" for k, v in clean.items()))
            return
        self._show_busy()
        threading.Thread(target=self._run_pipeline, args=(clean,), daemon=True).start()

    def _show_busy(self) -> None:
        self._clear()
        tk.Label(
            self.body, text="Taking a moment to understand your check-in…",
            font=("Segoe UI", 14), bg=BG, fg=INK,
        ).pack(pady=80)

    def _run_pipeline(self, record: dict) -> None:
        try:
            enriched = self.ai.analyse(record)
            result = self.logic.evaluate(enriched)
            stored = result.to_record()
            try:
                saved = self.store.save(stored)
                stored = {**stored, "record_id": saved.get("record_id")}
            except DataStoreError:
                pass
            self.after(0, lambda: self.show_result(stored, demo=self.demo_mode))
        except (AIProcessingError, LogicManagerError) as exc:
            self.after(0, lambda: self._show_failure(getattr(exc, "code", "unavailable")))
        except Exception:
            self.after(0, lambda: self._show_failure("unavailable"))

    def _show_failure(self, code: str) -> None:
        self._clear()
        copy = self.io.format_ai_error(code)
        card = tk.Frame(self.body, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        card.pack(fill="both", expand=True, padx=40, pady=30)
        tk.Label(card, text=copy["heading"], font=("Segoe UI", 16, "bold"), bg=PANEL, fg=INK).pack(anchor="w", padx=20, pady=(20, 6))
        tk.Label(card, text=copy["body"], font=("Segoe UI", 11), bg=PANEL, fg=SUB, wraplength=560, justify="left").pack(anchor="w", padx=20)
        advisor = copy["speak_to_advisor"]
        tk.Label(card, text=advisor["heading"], font=("Segoe UI", 12, "bold"), bg=PANEL, fg=INK).pack(anchor="w", padx=20, pady=(16, 4))
        tk.Label(
            card,
            text=f"SIT Counselling {ADVISOR_CONTACTS['helpline']}\n{ADVISOR_CONTACTS['email']}\nSOS {ADVISOR_CONTACTS['sos']} · mindline {ADVISOR_CONTACTS['mindline']}",
            font=("Segoe UI", 11), bg=PANEL, fg=INK, justify="left",
        ).pack(anchor="w", padx=20)
        tk.Button(card, text="Back to check-in", command=self.show_step, bg=ACCENT, fg="white", relief="flat", padx=12, pady=8).pack(anchor="w", padx=20, pady=16)

    # -- result -------------------------------------------------------------

    def show_result(self, record: dict, demo: bool = False) -> None:
        self._clear()
        self.result_record = record
        category = record.get("risk_category", "Moderate")
        soft = SOFT_LABEL_COPY.get(record.get("soft_label"), SOFT_LABEL_COPY["Worth a check-in"])

        canvas = tk.Canvas(self.body, bg=BG, highlightthickness=0)
        scroll = ttk.Scrollbar(self.body, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        hero = tk.Frame(inner, bg=_tier_color(category))
        hero.pack(fill="x", padx=8, pady=8)
        tk.Label(hero, text="Your check-in", font=("Segoe UI", 10), bg=_tier_color(category), fg=SUB).pack(anchor="w", padx=16, pady=(12, 0))
        tk.Label(hero, text=soft["heading"], font=("Segoe UI", 20, "bold"), bg=_tier_color(category), fg=INK).pack(anchor="w", padx=16)
        tk.Label(hero, text=soft["body"], font=("Segoe UI", 12), bg=_tier_color(category), fg=INK, wraplength=640, justify="left").pack(anchor="w", padx=16, pady=(0, 8))
        note = "Demo mode — local summary, not a clinical assessment." if demo else "Wellbeing guidance, not a medical diagnosis. Your ID was not sent to the AI."
        tk.Label(hero, text=note, font=("Segoe UI", 9), bg=_tier_color(category), fg=SUB).pack(anchor="w", padx=16, pady=(0, 12))

        if record.get("safety_flag"):
            warn = tk.Frame(inner, bg=HIGH)
            warn.pack(fill="x", padx=8, pady=4)
            tk.Label(warn, text="Please reach out", font=("Segoe UI", 12, "bold"), bg=HIGH, fg=INK).pack(anchor="w", padx=12, pady=(8, 0))
            tk.Label(
                warn,
                text=f"SIT Counselling {ADVISOR_CONTACTS['helpline']} · SOS {ADVISOR_CONTACTS['sos']} · mindline {ADVISOR_CONTACTS['mindline']}",
                font=("Segoe UI", 10), bg=HIGH, fg=INK,
            ).pack(anchor="w", padx=12, pady=(0, 8))

        tk.Label(inner, text="How the pieces fit together", font=("Segoe UI", 13, "bold"), bg=BG, fg=INK).pack(anchor="w", padx=12, pady=(12, 4))
        grid = tk.Frame(inner, bg=BG)
        grid.pack(fill="x", padx=8)
        for i, card in enumerate(record.get("factor_insights", [])):
            self._factor_card(grid, card).grid(row=i // 2, column=i % 2, sticky="nsew", padx=6, pady=6)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        tips = self.io.format_tips(record.get("tips", []))
        tk.Label(inner, text=tips["heading"], font=("Segoe UI", 13, "bold"), bg=BG, fg=INK).pack(anchor="w", padx=12, pady=(14, 4))
        for item in tips["items"]:
            row = tk.Frame(inner, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
            row.pack(fill="x", padx=12, pady=3)
            tk.Label(row, text=item["text"], font=("Segoe UI", 11), bg=PANEL, fg=INK, wraplength=640, justify="left").pack(anchor="w", padx=12, pady=8)

        advisor = self.io.format_advisor(record.get("speak_prominence", "medium"))
        box = tk.Frame(inner, bg=SOFT)
        box.pack(fill="x", padx=12, pady=12)
        tk.Label(box, text=advisor["heading"], font=("Segoe UI", 12, "bold"), bg=SOFT, fg=INK).pack(anchor="w", padx=12, pady=(10, 2))
        tk.Label(box, text=advisor["body"], font=("Segoe UI", 10), bg=SOFT, fg=INK, wraplength=640, justify="left").pack(anchor="w", padx=12)
        tk.Label(
            box,
            text=f"{ADVISOR_CONTACTS['helpline']}  ·  {ADVISOR_CONTACTS['email']}",
            font=("Segoe UI", 10), bg=SOFT, fg=INK,
        ).pack(anchor="w", padx=12, pady=(0, 10))

        tk.Button(inner, text="Back to homepage", command=self.show_home, bg=ACCENT, fg="white", relief="flat", padx=14, pady=8).pack(anchor="w", padx=12, pady=(0, 16))

    def _factor_card(self, parent: tk.Frame, card: dict) -> tk.Frame:
        bg = FLAG if card.get("flagged") else PANEL
        frame = tk.Frame(parent, bg=bg, highlightbackground=LINE, highlightthickness=1)
        tk.Label(frame, text=card.get("title", ""), font=("Segoe UI", 11, "bold"), bg=bg, fg=INK).pack(anchor="w", padx=10, pady=(8, 0))
        if card.get("flagged"):
            tk.Label(frame, text="Worth some attention", font=("Segoe UI", 9), bg=bg, fg=SUB).pack(anchor="w", padx=10)
        tk.Label(frame, text=card.get("value", ""), font=("Segoe UI", 10, "bold"), bg=bg, fg=INK).pack(anchor="w", padx=10, pady=(4, 0))
        tk.Label(frame, text=card.get("text", ""), font=("Segoe UI", 9), bg=bg, fg=SUB, wraplength=300, justify="left").pack(anchor="w", padx=10, pady=(2, 10))
        return frame

    # -- records ------------------------------------------------------------

    def show_records(self) -> None:
        self._clear()
        loaded = self.store.load_all()
        records = loaded.get("records", []) if loaded.get("ok") else []
        tk.Label(self.body, text="Saved check-ins · staff view", font=("Segoe UI", 16, "bold"), bg=BG, fg=INK).pack(anchor="w", pady=(4, 2))
        tk.Label(self.body, text="Student IDs are visible here only. They are never sent to the AI.", font=("Segoe UI", 10), bg=BG, fg=SUB).pack(anchor="w", pady=(0, 8))
        if not records:
            tk.Label(self.body, text="No records yet.", font=("Segoe UI", 11), bg=BG, fg=SUB).pack(anchor="w")
            return

        cols = ("student_id", "stress_score", "risk_category", "soft_label", "status", "saved_at")
        tree = ttk.Treeview(self.body, columns=cols, show="headings", height=18)
        headings = {
            "student_id": "Student ID",
            "stress_score": "Score",
            "risk_category": "Tier",
            "soft_label": "Label",
            "status": "Status",
            "saved_at": "Saved",
        }
        for col in cols:
            tree.heading(col, text=headings[col])
            tree.column(col, width=120, anchor="center")
        tree.column("student_id", width=100)
        tree.column("saved_at", width=180)
        tree.pack(fill="both", expand=True)

        for item in sorted(records, key=lambda r: str(r.get("saved_at") or ""), reverse=True):
            status = "Pending" if str(item.get("status", "")).lower() == "pending" or item.get("ai_ok") is not True else "Evaluated"
            tree.insert("", "end", values=(
                item.get("student_id", ""),
                item.get("stress_score", ""),
                item.get("risk_category", ""),
                item.get("soft_label", ""),
                status,
                str(item.get("saved_at", ""))[:19],
            ))


def main() -> None:
    app = DoNotStressApp()
    app.mainloop()


if __name__ == "__main__":
    main()
