import pymysql
import datetime
from pytz import timezone, utc
PW = 'P@ssw0rd'
SECRET_KEY = 'hello,python'

def loginCheck(session):
    return 'u_sn' in session

def adminLoginCheck(session):
    return 'admin' in session


class DB:
    RESULT_EXIST = 0
    RESULT_EXIST_ID = 1
    RESULT_NOT_EXIST = 2

    def __init__(self, host, user, password, db, port=3306):
        self.host = host
        self.user = user
        self.password = password
        self.db = db
        self.port = port

    def _cursor(self, _conn):
        return _conn.cursor(pymysql.cursors.DictCursor)

    def _getValue(self, value):
        if type(value) is datetime.datetime:
            return str(value)
        elif type(value) is datetime.date:
            return str(value)
        else:
            return value

    def _getResult(self, resultSet):
        _resultSet = []
        for result in resultSet:
            _keys = result.keys()
            _result = dict()
            for key in _keys:
                value = self._getValue(result[key])
                _result[key.lower()] = value
            _resultSet.append(_result)
        return _resultSet

    def _getQueryType(self, sql):
        _sql = sql.upper()
        if _sql.startswith('SELECT'):
            return DB.RESULT_EXIST
        elif _sql.startswith('INSERT'):
            return DB.RESULT_EXIST_ID
        else:
            return DB.RESULT_NOT_EXIST

    def __call__(self, sql, params=None):
        _conn = pymysql.connect(self.host, self.user, self.password, self.db, port=self.port)
        _curs = self._cursor(_conn)
        if params:
            _curs.execute(sql, params)
        else:
            _curs.execute(sql)
        if self._getQueryType(sql) is DB.RESULT_EXIST:
            _result = _curs.fetchall()
            _conn.close()
            return self._getResult(_result)
        elif self._getQueryType(sql) is DB.RESULT_EXIST_ID:
            _rowId = _curs.lastrowid
            _conn.commit()
            _conn.close()
            return _rowId
        else:
            _conn.commit()
            _conn.close()
            return None


def getToday(time=False, delta=0):
    KST = timezone('Asia/Seoul')
    now = datetime.datetime.utcnow()
    now = utc.localize(now).astimezone(KST)
    if time:
        return str(now)[:19]
    return str(now.date() - datetime.timedelta(days=delta))


