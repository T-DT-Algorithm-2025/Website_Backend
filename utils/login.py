from core.global_params import redis_pool
import uuid

login_expire = 7 * 24 * 60 * 60  # 7 days in seconds

def create_session(uid):
    session_id = str(uuid.uuid4())
    while redis_pool.exists(f'session:{session_id}'):
        session_id = str(uuid.uuid4())
    redis_pool.setex(f'session:{session_id}', login_expire, uid)
    return session_id

def pop_session(session_id):
    redis_pool.delete(f'session:{session_id}')

def get_user_id(session_id):
    return redis_pool.get(f'session:{session_id}')

def get_user_id(session, request):
    if 'session_id' in session:
        return get_user_id(session['session_id'])
    elif 'session_id' in request.cookies:
        session['session_id'] = request.cookies['session_id']
        return get_user_id(request.cookies['session_id'])
    return None