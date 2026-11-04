"""DoNotStress entry point: campus UI → I/O → Gemini → Logic → saved records.

Collaborators are injected as instances:
  * GeminiAIManager  (AI)
  * LogicManager     (Logic)
  * JsonRecordRepository (Data)
  * StudentIO        (I/O formatting and validation)
"""

import hashlib
import json
import logging
import os
import secrets
import time
import uuid
from threading import RLock

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from ai_manager import AIProcessingError, GeminiAIManager
from data_manager import DataStoreError, JsonRecordRepository, TIER_TO_CATEGORY
from io_manager import StudentIO
import survey
from logic_manager import AIScoreVerifier, LogicManager, LogicManagerError, ScoreCalculator

load_dotenv()
logger = logging.getLogger(__name__)

# Logic Manager (Phase 2, object-oriented). One ScoreCalculator is shared by
# the evaluator and by the verifier the AI layer uses, so the Gemini prompt,
# the check on Gemini's reply and the final evaluation always use the same
# rules. These objects never change after they are created, so every request
# can share them.
SCORE_CALCULATOR = ScoreCalculator()
LOGIC_MANAGER = LogicManager(calculator=SCORE_CALCULATOR)
SCORE_VERIFIER = AIScoreVerifier(SCORE_CALCULATOR)
# Shared AI and I/O instances. The repository is created per app because
# its path comes from configuration.
AI_MANAGER = GeminiAIManager(verifier=SCORE_VERIFIER)
STUDENT_IO = StudentIO()

# Fixed coursework/demo account. Only the hash lives in server code; never
# include credentials in templates, JavaScript or the browser boot payload.
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD_HASH = 'scrypt:32768:8:1$zoikUrXAJEAJCQlR$83ec3b2a32cedeb5721031e22f7fedc19ed5eea40c5995aa11d2c2ea1cc40845b393de85d68cda54706b5714293fc49ec360a477913186f00b46be7a6c31e8c1'


def submission_fingerprint(record):
    """sha256 of student_id, the 11 answers, and survey_version.

    The same answers are one submission. A changed answer is a new one.
    """
    answers = [record.get(question['key']) for question in survey.QUESTIONS]
    payload = json.dumps(
        [record.get('student_id'), answers, record.get('survey_version')],
        separators=(',', ':'), ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def process_checkin(record, *, generate_fn=None, max_attempts=3, retry_delay_sec=0.5,
                    logic=LOGIC_MANAGER, ai=AI_MANAGER):
    """AI must succeed before Logic may finalize an assessment.

    Returns (True, evaluated record dict) or (False, error code). ``logic``
    and ``ai`` can be replaced in tests.
    """
    try:
        # Use a temporary AI manager when the caller supplies test overrides.
        worker = ai
        if generate_fn is not None or max_attempts != 3 or retry_delay_sec != 0.5:
            worker = GeminiAIManager(
                verifier=SCORE_VERIFIER,
                generate_fn=generate_fn,
                max_attempts=max_attempts,
                retry_delay_sec=retry_delay_sec,
            )
        enriched = worker.analyse(record)
    except AIProcessingError as exc:
        logger.warning('Check-in could not complete: %s', exc.code)
        return False, exc.code
    if not isinstance(enriched, dict):
        logger.warning('Check-in could not complete: unavailable')
        return False, 'unavailable'
    try:
        result = logic.evaluate(enriched)
    except LogicManagerError as exc:
        logger.warning('Logic rejected the check-in: %s', exc.code)
        return False, 'unavailable'
    return True, result.to_record()


def result_view(record, saved=False, io=STUDENT_IO):
    """Only send allow-listed, student-facing copy to the browser."""
    advisor = io.format_advisor(record['speak_prominence'])
    advisor.pop('cta', None)
    return {
        'soft': io.format_soft_label(record['soft_label']),
        'tips': io.format_tips(record['tips']),
        'advisor': advisor,
        'saved': saved,
        'insights': {
            'risk_category': record.get('risk_category', 'Unknown'),
            'explanation': str(record.get('reasoning', '')).split(' Logic adjusted:')[0],
            'stressors': record.get('primary_stressors', []),
            'survey_version': record.get('survey_version', 'legacy'),
            'stress_score': record.get('stress_score'),
            'support_mean': record.get('support_mean'),
            'context_flags': record.get('context_flags', {}),
            'factors': record.get('factor_insights', []),
            'safety_flag': record.get('safety_flag', False),
            'snapshot': {key: record.get(key) for key in (
                'sleep_hours', 'stress_level', 'academic_workload',
                'financial_stress', 'social_support', *survey.QUESTION_MAP)},
        },
    }


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get('FLASK_SECRET_KEY') or secrets.token_hex(32),
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        DATA_PATH=os.environ.get('DONOTSTRESS_DATA_PATH') or None,
        AI_GENERATE_FN=None, AI_MAX_ATTEMPTS=3, AI_RETRY_DELAY_SEC=0.5,
        PENDING_TTL_SECONDS=1800, MAX_CONTENT_LENGTH=64 * 1024,
        ADMIN_SESSION_SECONDS=1800, ADMIN_LOGIN_MAX_ATTEMPTS=5,
        ADMIN_LOGIN_WINDOW_SECONDS=300,
    )
    if test_config:
        app.config.update(test_config)
    # Injected collaborators. The repository uses the configured data path.
    store = JsonRecordRepository(app.config['DATA_PATH'])
    io = STUDENT_IO
    ai = GeminiAIManager(
        verifier=SCORE_VERIFIER,
        generate_fn=app.config['AI_GENERATE_FN'],
        max_attempts=app.config['AI_MAX_ATTEMPTS'],
        retry_delay_sec=app.config['AI_RETRY_DELAY_SEC'],
    )
    app.extensions['store'] = store
    app.extensions['io'] = io
    app.extensions['ai'] = ai
    # Single-process local app: retain records temporarily in server memory,
    # never inside Flask's client-readable signed session cookie.
    pending = {}
    # csrf token -> {fingerprint, record_id} for the submission in this session.
    # The session cookie is not visible to a second request until the first
    # response is sent, so the lock-protected claim stops a rapid pair of
    # posts from appending two rows.
    submissions = {}
    lock = RLock()
    app.extensions['pending_checkins'] = pending
    app.extensions['pending_submissions'] = submissions
    # Server-side tokens make logout/expiry revoke access even if a previous
    # signed session cookie is replayed. No role is trusted from client input.
    admin_sessions = {}
    login_attempts = {}
    app.extensions['admin_sessions'] = admin_sessions

    def is_admin():
        token = session.get('admin_token')
        with lock:
            expires = admin_sessions.get(token, 0)
            if expires > time.monotonic():
                return True
            admin_sessions.pop(token, None)
        session.pop('admin_token', None)
        return False

    def revoke_admin():
        with lock:
            admin_sessions.pop(session.pop('admin_token', None), None)

    def clear_pending():
        with lock:
            pending.pop(session.pop('checkin_token', None), None)

    def matched_pending_id(fingerprint):
        """Id of the pending row for this submission, if this session already saved one."""
        record_id = session.get('pending_record_id')
        if (session.get('pending_fingerprint') == fingerprint
                and isinstance(record_id, str) and record_id.strip()):
            return record_id.strip()
        claim = submissions.get(session.get('csrf_token'))
        if isinstance(claim, dict) and claim.get('fingerprint') == fingerprint:
            found = claim.get('record_id')
            if isinstance(found, str) and found.strip():
                return found.strip()
        return None

    def remember_submission(fingerprint, record_id, *, pending_save):
        """Keep the submission id. Pending saves also go in the session cookie."""
        token = session.get('csrf_token')
        if token:
            submissions[token] = {'fingerprint': fingerprint, 'record_id': record_id}
        if pending_save:
            session['pending_fingerprint'] = fingerprint
            session['pending_record_id'] = record_id
        else:
            session.pop('pending_fingerprint', None)
            session.pop('pending_record_id', None)

    def current_entry():
        with lock:
            return pending.get(session.get('checkin_token'))

    @app.before_request
    def expire_records_and_check_csrf():
        with lock:
            cutoff = time.monotonic() - app.config['PENDING_TTL_SECONDS']
            for key in [key for key, item in pending.items() if item['created'] < cutoff]:
                del pending[key]
            now = time.monotonic()
            for key in [key for key, expiry in admin_sessions.items() if expiry <= now]:
                del admin_sessions[key]
            for key in list(login_attempts):
                login_attempts[key] = [stamp for stamp in login_attempts[key]
                                       if stamp > now - app.config['ADMIN_LOGIN_WINDOW_SECONDS']]
                if not login_attempts[key]:
                    del login_attempts[key]
        if request.method == 'POST':
            expected = session.get('csrf_token', '')
            provided = request.headers.get('X-CSRF-Token', '')
            if not provided and not request.is_json:
                provided = request.form.get('csrf_token', '')
            if not expected or not secrets.compare_digest(provided.encode('utf-8'), expected.encode('utf-8')):
                return jsonify(message='This page has expired. Reload and try again.'), 403

    def render_campus(page='home'):
        session.setdefault('csrf_token', secrets.token_urlsafe(32))
        entry = current_entry()
        return render_template('checkin.html', boot={
            'page': page, 'survey': survey.public_config(),
            'isAdmin': is_admin(), 'adminLoginUrl': url_for('admin_login'),
            'result': result_view(entry['record'], entry['saved']) if entry else None,
            'csrfToken': session['csrf_token'],
            'submitUrl': url_for('submit_checkin'), 'saveUrl': url_for('save_checkin'),
            'newUrl': url_for('new_checkin'), 'homeUrl': url_for('checkin'),
            'resultUrl': url_for('result'), 'recordsPageUrl': url_for('records_page'),
            'recordsUrl': url_for('saved_records'),
        })

    @app.get('/')
    def checkin():
        return render_campus()

    # Legacy URL from the removed garden page; send visitors home.
    @app.get('/garden')
    def retired_page():
        return redirect(url_for('checkin'))

    @app.route('/admin/login', methods=['GET', 'POST'])
    def admin_login():
        if is_admin():
            return redirect(url_for('records_page'))
        session.setdefault('csrf_token', secrets.token_urlsafe(32))
        error, status = None, 200
        if request.method == 'POST':
            values = request.get_json(silent=True) if request.is_json else request.form
            values = values if isinstance(values, dict) or hasattr(values, 'get') else {}
            username, password = values.get('username', ''), values.get('password', '')
            address = request.remote_addr or 'local'
            with lock:
                attempts = login_attempts.setdefault(address, [])
                if len(attempts) >= app.config['ADMIN_LOGIN_MAX_ATTEMPTS']:
                    error, status = 'Too many sign-in attempts. Please try again in five minutes.', 429
                else:
                    attempts.append(time.monotonic())
            if not error:
                valid_password = isinstance(password, str) and len(password) <= 256 and check_password_hash(ADMIN_PASSWORD_HASH, password)
                if username == ADMIN_USERNAME and valid_password:
                    revoke_admin()
                    token = secrets.token_urlsafe(32)
                    with lock:
                        admin_sessions[token] = time.monotonic() + app.config['ADMIN_SESSION_SECONDS']
                        login_attempts.pop(address, None)
                    session['admin_token'] = token
                    session['csrf_token'] = secrets.token_urlsafe(32)
                    return redirect(url_for('records_page'))
                error, status = 'Incorrect username or password.', 401
        return render_template('admin_login.html', error=error, csrf_token=session['csrf_token']), status

    @app.post('/admin/logout')
    def admin_logout():
        revoke_admin()
        clear_pending()
        with lock:
            submissions.pop(session.get('csrf_token'), None)
        session.clear()
        return redirect(url_for('checkin'))

    @app.post('/')
    def submit_checkin():
        values = request.get_json(silent=True) if request.is_json else request.form
        if not hasattr(values, 'get'):
            return jsonify(message='Please submit a check-in form.'), 400
        safety = survey.safety_check(values.get('feelings_text', ''))
        ok, record = io.validate_form(values)
        if not ok:
            return jsonify(errors=record, safety_flag=safety,
                           advisor=io.format_advisor('high') if safety else None), 400
        clear_pending()
        fingerprint = submission_fingerprint(record)
        try:
            ok, outcome = process_checkin(
                record,
                generate_fn=app.config['AI_GENERATE_FN'],
                max_attempts=app.config['AI_MAX_ATTEMPTS'],
                retry_delay_sec=app.config['AI_RETRY_DELAY_SEC'],
                ai=ai,
            )
        except Exception:
            logger.warning('Check-in pipeline could not complete')
            ok, outcome = False, 'unavailable'
        if not ok:
            # AI did not finish. The same answers in this session are one
            # pending row. A refresh does not write, and a later success
            # upgrades that row instead of appending another.
            try:
                with lock:
                    pending_id = matched_pending_id(fingerprint)
                    if pending_id is None:
                        record_id = uuid.uuid4().hex
                        try:
                            stored = store.save_pending({**record, 'record_id': record_id})
                            remember_submission(
                                fingerprint,
                                stored.get('record_id') or record_id,
                                pending_save=True,
                            )
                        except DataStoreError:
                            logger.warning('Pending check-in could not be saved')
                    else:
                        remember_submission(fingerprint, pending_id, pending_save=True)
            except Exception:
                logger.warning('Pending check-in could not be saved')
            copy = io.format_ai_error(outcome)
            return jsonify(
                message='We could not complete your check-in right now. Your answers are still here; please try again.',
                error_code=outcome, safety_flag=safety, advisor=copy['speak_to_advisor'],
            ), 503
        try:
            with lock:
                pending_id = matched_pending_id(fingerprint)
                try:
                    if pending_id:
                        outcome = {**outcome, 'record_id': pending_id}
                        stored = store.replace_pending(pending_id, outcome)
                    else:
                        stored = store.save(outcome)
                    stored_id = stored.get('record_id')
                    if stored_id:
                        remember_submission(fingerprint, stored_id, pending_save=False)
                    saved = {'ok': True, 'record': stored}
                except DataStoreError as exc:
                    logger.warning("Saving the check-in failed: %s", type(exc).__name__)
                    saved = {'ok': False}
        except Exception as exc:
            logger.warning("Saving the check-in failed: %s", type(exc).__name__)
            saved = {'ok': False}
        if not saved.get('ok'):
            return jsonify(message='We could not save your check-in just now. Your answers are still here; please try again.'), 500
        token = secrets.token_urlsafe(32)
        with lock:
            pending[token] = {'record': outcome, 'saved': True, 'created': time.monotonic()}
        session['checkin_token'] = token
        return jsonify(ok=True, result=result_view(outcome, saved=True, io=io))

    @app.get('/records')
    def records_page():
        if not is_admin():
            return redirect(url_for('admin_login'))
        return render_campus('records')

    @app.get('/api/records')
    def saved_records():
        """Read only explicitly saved check-ins; never expose free text or keys."""
        if not is_admin():
            return jsonify(message='Admin sign-in is required to view saved records.'), 401
        try:
            with lock:
                loaded = store.load_all()
        except Exception as exc:
            logger.warning("Loading saved records failed: %s", type(exc).__name__)
            loaded = {'ok': False}
        if not loaded.get('ok') or loaded.get('error'):
            return jsonify(message='Saved records could not be loaded. Please try again.'), 500
        records = [item for item in loaded.get('records', [])
                   if isinstance(item, dict) and item.get('survey_version') == survey.VERSION]
        cohorts = sorted({str(item.get('student_id', ''))[:2] for item in records
                          if len(str(item.get('student_id', ''))) >= 2
                          and str(item.get('student_id', ''))[:2].isascii()
                          and str(item.get('student_id', ''))[:2].isdigit()}, reverse=True)
        query = request.args.get('student_id', '').strip()
        tier = request.args.get('tier', '').strip()
        cohort = request.args.get('cohort_year', '').strip()
        if tier and tier not in TIER_TO_CATEGORY:
            return jsonify(message="Choose a tier: You're doing ok, Worth a check-in, or Please reach out."), 400
        if cohort and (len(cohort) not in (2, 4) or not cohort.isascii() or not cohort.isdigit()):
            return jsonify(message='Choose a valid cohort year.'), 400
        filtered = store.filter(records, **{
            key: value for key, value in {'tier': tier, 'cohort_year': cohort}.items() if value
        })
        filtered = [item for item in filtered if query in str(item.get('student_id', ''))]
        columns = ('student_id', 'stress_score', 'risk_category', 'soft_label',
                   'pss_1', 'pss_2', 'pss_3', 'pss_4',
                   'sleep_hours_avg', 'sleep_quality', 'pas_workload', 'pas_catchup',
                   'fin_stress', 'mspss_friends', 'mspss_family', 'saved_at', 'survey_version')
        rows = []
        for item in filtered:
            row = {key: item.get(key) for key in columns}
            if not row.get('soft_label'):
                row['soft_label'] = {value: name for name, value in TIER_TO_CATEGORY.items()}.get(row.get('risk_category'))
            source = str(item.get('source', '')).lower()
            processed = item.get('ai_ok') is True or source in {
                'gemini', 'ai', 'ai_manager', 'gemini+logic', 'ai_logic'}
            pending = str(item.get('status', '')).strip().lower() == 'pending'
            row['status'] = 'Pending' if pending or not processed else 'Evaluated'
            rows.append(row)
        rows.sort(key=lambda row: str(row.get('saved_at') or ''), reverse=True)
        return jsonify(records=rows, total=len(records), matching=len(rows), cohorts=cohorts)

    @app.get('/result')
    def result():
        # Refreshing the result only reads the session. The check-in was
        # already written once, when it was submitted.
        if not current_entry():
            return redirect(url_for('checkin'))
        return render_campus('result')

    @app.post('/save')
    def save_checkin():
        """Retry a missed write. A result that is already saved is left as-is."""
        with lock:
            entry = current_entry()
            if not entry:
                return jsonify(message='Your result has expired. Please start a new check-in.'), 409
            if entry['saved']:
                return jsonify(ok=True, saved=True)
            try:
                store.save(entry['record'])
                entry['saved'] = True
            except DataStoreError as exc:
                logger.warning("Retrying the pending save failed: %s", type(exc).__name__)
                return jsonify(message='Your check-in could not be saved. Please try again.'), 500
            except Exception as exc:
                logger.warning("Retrying the pending save failed: %s", type(exc).__name__)
                return jsonify(message='Your check-in could not be saved. Please try again.'), 500
        return jsonify(ok=True, saved=True)

    @app.get('/new')
    def new_checkin():
        clear_pending()
        return redirect(url_for('checkin'))

    @app.errorhandler(413)
    def oversized_request(error):
        return jsonify(message='Your response is too long. Please shorten it and try again.'), 413

    @app.after_request
    def prevent_answer_caching(response):
        if request.endpoint != 'static':
            response.headers['Cache-Control'] = 'no-store'
        return response

    return app


app = create_app()

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.environ.get('PORT', '5000')),
            debug=os.environ.get('FLASK_DEBUG', '0').lower() in {'1', 'true', 'yes'})
