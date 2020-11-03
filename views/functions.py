from flask import Blueprint, render_template, abort, session, redirect, request, jsonify, send_file
from util import DB, SECRET_KEY, getToday, PW
import datetime
from PIL import ImageFont, ImageDraw, Image
import easyocr
import six
import cv2
from matplotlib import pyplot as plt
import numpy as np
import requests
import json
import glob
import os
import ntpath
import re
import zipfile
import io
from pathlib import Path
fp = Blueprint('function', __name__, url_prefix='/ajax')
fp.secret_key = SECRET_KEY

db = DB(host='localhost', user='root', password=PW, db='image')
reader = easyocr.Reader(['ch_sim'])

def convert(data):
    return [(d[1], d[0]) for d in data]

def toInt(bounds):
    return [ [int(b) for b in bound] for bound in bounds]

def find_ch(results):
    return [(text, toInt(boundaries), *get_translate(text)) for text, boundaries in results if len(re.findall(r'[\u4e00-\u9fff]+', text)) > 0]


def get_info(data):
    xs = []
    ys = []
    for x, y in data:
        xs.append(int(x))
        ys.append(int(y))
    return {"start": (min(xs) if min(xs) > 0 else 0, min(ys) if min(ys) > 0 else 0),
            "width": max(xs) - (min(xs) if min(xs) > 0 else 0), "height": max(ys) - (min(ys) if min(ys) > 0 else 0)}


def get_image(img_h, img_w, text, color, img, fontpath):
    fontcolor = (0, 0, 0, 0)
    if (color[0] + color[1] + color[2]) // 3 < 128:
        fontcolor = (255, 255, 255, 0)
    font_size = min(img_w // (len(text) - text.count(" ") // 2), img_h)-2
    try:
        f_p = os.path.join(os.path.dirname(__file__), '../'+fontpath)
        with open(f_p, "rb") as f:
            font_bytes = io.BytesIO(f.read())
        font = ImageFont.truetype(font_bytes, font_size)
    except:
        f_p = fontpath
        with open(f_p, "rb") as f:
            font_bytes = io.BytesIO(f.read())
        font = ImageFont.truetype(font_bytes, font_size)
    img_pil = Image.fromarray(img)
    draw = ImageDraw.Draw(img_pil)

    st_x = (img_w - font_size * (len(text) - text.count(" ") // 2)) // 2
    st_y = (img_h - font_size) // 2 - 5

    draw.text((st_x, st_y), text, font=font, fill=fontcolor)

    img = np.array(img_pil)
    return img


def get_translate(text):
    data = {'source': 'zh-CN', 'target': 'en', 'text': text}

    headers = {"X-NCP-APIGW-API-KEY-ID": "cs36gu9j0n", "X-NCP-APIGW-API-KEY": "8Ym3riLwyhOVqkJCChD5az3RUUeGAASJ1zMLanTH"}
    res = requests.post("https://naveropenapi.apigw.ntruss.com/nmt/v1/translation", headers=headers, data=data)
    resj = json.loads(res.text)
    temp = resj["message"]["result"]["translatedText"]

    data["text"] = temp
    data["source"] = 'en'
    data["target"] = 'ko'
    res = requests.post("https://naveropenapi.apigw.ntruss.com/nmt/v1/translation", headers=headers, data=data)
    resj = json.loads(res.text)
    last = resj["message"]["result"]["translatedText"]
    return last, temp


def get_mask(results, img):
    black = np.zeros(img.shape, np.uint8)
    for text, bound, new_text, _ in results:
        if new_text != '#1#2#3#4#5':
            info = get_info(bound)

            x, y = info["start"]
            w, h = info["width"], info["height"]
            try:
                white = np.ones((h, w, 3)) * 255
                white = white.astype(np.int8)
                black[y:y + h, x:x + w] = white
            except:
                continue
    black = cv2.cvtColor(black, cv2.COLOR_BGR2GRAY)
    _, black_binary = cv2.threshold(black, 150, 255, cv2.THRESH_BINARY)

    return black_binary

@fp.route("/isLogin", methods=['POST'])
def isLogin():
    data = dict()
    if "u_sn" in session:
        data["result"] = 1
        data["msg"] = "로그인 되어있습니다."
    else:
        data["result"] = 0
        data["msg"] = "로그인이 필요합니다."
    return data

@fp.route("/login", methods=['POST'])
def login():
    u_id = request.form.get('u_id')
    u_pw = request.form.get('u_pw')
    result = db("SELECT * FROM user WHERE U_ID=%s AND U_PW=%s", (u_id, u_pw))
    if result:
        session['u_sn'] = result[0]['u_sn']
        return jsonify({'result': 1})
    else:
        return jsonify({'result': 0})

@fp.route("/adminLogin", methods=['POST'])
def adminLogin():
    u_id = request.form.get('u_id')
    u_pw = request.form.get('u_pw')
    result = db("SELECT * FROM user WHERE U_ID=%s AND U_PW=%s AND U_RANK=1", (u_id, u_pw))
    if result:
        session['admin'] = result[0]['u_sn']
        return jsonify({'result': 1})
    else:
        return jsonify({'result': 0})

@fp.route('/searchUser', methods=['POST'])
def searchUser():

    page = int(request.form.get("page"))

    type = request.form.get('type')
    if type == 'F':
        where = " AND IFNULL(r.R_TYPE, 'O')='F' AND u.R_SN>0 "
    elif type == 'N':
        where = " AND IFNULL(r.R_TYPE, 'O')='N' AND u.R_SN>0"
    else:
        where = ""
    cond = int(request.form.get('condition'))
    q = request.form.get('query')
    if cond == 1:
        col = "u.U_ID"
    elif cond == 2:
        col = "u.U_NM"
    elif cond == 3:
        col = "u.U_CP"
    elif cond == 4:
        query = "SELECT u.*, IFNULL(r.R_TYPE, 'O') AS R_TYPE, r.REGIST_DTM as dtm FROM user u LEFT OUTER JOIN request r ON u.U_SN=r.U_SN AND r.R_SN=IF(u.R_SN < 0, -u.R_SN, u.R_SN) WHERE 1 {} ORDER BY u.REGIST_DTM DESC".format(where)
        result = db(query + " LIMIT %s OFFSET %s", (10, page * 10))
        count = db(query)

        if len(result) > 0:
            return jsonify({"result": 1, "data": result, "recordsTotal" : len(count)})
        else:
            return jsonify({"result": 0, "recordsTotal" : 0})
    else:
        query = "SELECT u.*, IFNULL(r.R_TYPE, 'O') AS R_TYPE, r.REGIST_DTM as dtm FROM user u LEFT OUTER JOIN request r ON u.U_SN=r.U_SN AND r.R_SN=IF(u.R_SN < 0, -u.R_SN, u.R_SN) WHERE (u.U_ID LIKE %s OR u.U_NM LIKE %s OR u.U_CP LIKE %s) {} ORDER BY u.REGIST_DTM DESC".format(where)
        print(query)
        result = db(query + " LIMIT %s OFFSET %s", ('%{}%'.format(q), '%{}%'.format(q), '%{}%'.format(q), 10, page * 10))
        count = db(query, ('%{}%'.format(q), '%{}%'.format(q), '%{}%'.format(q)))

        if len(result) > 0:
            return jsonify({"result": 1, "data": result, "recordsTotal" : len(count)})
        else:
            return jsonify({"result": 0, "recordsTotal" : 0})

    query = "SELECT u.*, r.R_SN, IFNULL(r.R_TYPE, 'O') AS R_TYPE, r.REGIST_DTM as dtm FROM user u LEFT OUTER JOIN request r ON u.U_SN=r.U_SN AND r.R_SN=IF(u.R_SN < 0, -u.R_SN, u.R_SN) WHERE {} {} LIKE %s".format(col, where)
    result = db(query + " LIMIT %s OFFSET %s", ('%{}%'.format(q), 10, page * 10))
    count = db(query, ('%{}%'.format(q)))

    if len(result) > 0:
        return jsonify({"result": 1, "data": result, "recordsTotal": len(count)})
    else:
        return jsonify({"result": 0, "recordsTotal": 0})


@fp.route("/processRequest", methods=['POST'])
def processRequest():
    u_sns = request.form.getlist('u_sns[]')
    end = request.form.get('end')
    start = request.form.get('start')
    for u_sn in u_sns:
        users = db("SELECT * FROM user WHERE U_SN=%s", u_sn)
        if users:
            user = users[0]
            r_sn = user['r_sn']
            if r_sn > 0:
                r_sn *= -1
            db("UPDATE user SET R_SN=%s, U_START=%s, U_END=%s WHERE U_SN=%s", (r_sn, start, end, u_sn))
    return jsonify({"result" : 1})
@fp.route("/logout", methods=['POST'])
def logout():
    del session['u_sn']
    return jsonify({'result': 1})

@fp.route("/adminLogout", methods=['POST'])
def adminLogout():
    del session['admin']
    return jsonify({'result': 1})

@fp.route('/getOnlyArticle')
def getOnlyArticle():
    where = ""
    params = []


    page = int(request.args.get("page"))

    # queryType = int(request.args.get("queryType"))
    # queries = request.args.getlist("queries[]")

    start = request.args.get("start")
    end = request.args.get("end")
    where += " AND a.REGIST_DTM BETWEEN %s AND %s "
    params += ["{} 00:00:00".format(start), "{} 23:59:59".format(end)]

    status = int(request.args.get("status"))
    if status == 1:
        where += " AND a.A_TYPE = 0 AND c.A_SN IS NULL "
    elif status == 2:
        where += " AND a.A_TYPE = 0 AND c.A_SN IS NOT NULL "
    else:
        where += " AND a.A_TYPE = 0 "


    query = "SELECT a.*, u.U_ID, c.A_SN AS CNNC FROM article a LEFT JOIN user u ON a.U_SN=u.U_SN LEFT OUTER JOIN article c ON c.A_CNNC=a.A_SN WHERE 1=1 {} ORDER BY a.REGIST_DTM".format(where)
    result = db(query+" LIMIT %s OFFSET %s", tuple(params+[10, page*10]))
    count = db(query, tuple(params))
    return jsonify({"data" : result, "recordsTotal" : len(count)})


@fp.route('/getMainAll')
def getMainAll():

    page = int(request.args.get("page"))

    result = db("SELECT * FROM main WHERE M_TYPE=1 ORDER BY REGIST_DTM LIMIT %s OFFSET %s", (10, page*10))
    count = db("SELECT * FROM main WHERE M_TYPE=1")

    return jsonify({"data" : result, "recordsTotal" : len(count)})

@fp.route('/insertMain', methods=['POST'])
def insertMain():
    title = request.form.get('title')
    text = request.form.get('text')
    now = getToday()
    db("INSERT INTO main(M_TYPE, M_TITLE, M_TEXT, REGIST_DTM) VALUES(1, %s, %s, %s)", (title, text, now))
    return jsonify({"result" : 1})


@fp.route('/showInfo', methods=['POST'])
def showInfo():
    u_sn = session['u_sn']
    data = db("SELECT * FROM user WHERE U_SN=%s", u_sn)
    return jsonify({"result" : 1, "data" : data})


@fp.route("/join", methods=['POST'])
def join():
    u_id = request.form.get('u_id')
    u_pw = request.form.get('u_pw')
    u_nm = request.form.get('u_nm')
    u_cp = request.form.get('u_cp')
    u_phone = request.form.get('u_phone')
    u_mail = request.form.get('u_mail')
    result = db("SELECT * FROM user WHERE U_ID=%s", (u_id))
    if result:
        return jsonify({'result': 0, 'msg': '존재하는 아이디입니다.'})
    try:
        now = getToday(time=True)
        u_sn = db("INSERT INTO user(U_ID, U_PW, U_NM, U_CP, U_PHONE, U_MAIL, REGIST_DTM) VALUES (%s, %s, %s, %s, %s, %s, %s)", (u_id, u_pw, u_nm, u_cp, u_phone, u_mail, now))
        session['u_sn'] = u_sn
        return jsonify({'result': 1})
    except Exception as e:
        return jsonify({'result': 0, 'msg': str(e)})


@fp.route('/uploadImage', methods=['POST'])
def uploadImage():
    if 'u_sn' in session:
        u_sn = session['u_sn']
        result = db("SELECT * FROM user WHERE U_SN=%s", u_sn)
        if result:
            user = result[0]

            now = datetime.datetime.strptime(getToday(), '%Y-%m-%d')
            if user['u_start'] and user['u_end']:
                u_start = datetime.datetime.strptime(user['u_start'], '%Y-%m-%d')
                u_end = datetime.datetime.strptime(user['u_end'], '%Y-%m-%d')
                if (u_end-now).total_seconds() >= 0 and (now-u_start).total_seconds() >= 0:
                    font = request.files.get('font')
                    if font:
                        f_ext = font.filename.split(".")[-1]
                        f_path = 'static/files/{}.{}'.format(datetime.datetime.now().strftime("%y_%m_%d_%H_%M_%S"),
                                                             f_ext)
                        font.save('./' + f_path)
                    else:
                        f_path = 'static/files/malgun.ttf'
                    g_sn = db("INSERT INTO grouped(U_SN, F_PATH, REGIST_DTM) VALUES (%s, %s, %s)",
                              (u_sn, f_path, getToday(time=True)))
                    os.makedirs('./static/files/{}'.format(g_sn), exist_ok=True)
                    u_files = request.files.getlist("files[]")
                    data = []
                    for idx, u_file in enumerate(u_files):
                        origin = u_file.filename
                        name, ext = origin.split(".")
                        path = '/static/files/{}/{}_{}_{}.{}'.format(g_sn, g_sn, datetime.datetime.now().strftime(
                            "%y_%m_%d_%H_%M_%S"), idx, ext)
                        u_file.save('.' + path)
                        image = Image.open('.' + path)
                        width, height = image.size
                        w = 300
                        h = int(300 * height / width)
                        i_sn = db("INSERT INTO uploaded(G_SN, PATH) VALUES (%s, %s)", (g_sn, path))
                        data.append({'sn': i_sn, 'height': h})
                    # db("UPDATE ordered SET O_CONFIRM_PATH=%s WHERE O_SN=%s", (path, sn))
                    return jsonify({"result": 1, "msg": "업로드되었습니다.", "data": data, "sn": g_sn})

                else:
                    return jsonify({"result": 0, "msg": "사용권의 사용기간이 만료되었습니다."})
            else:
                return jsonify({"result" : 0, "msg" : "사용권이 없습니다."})


        else:
            return jsonify({"result" : 0, "msg" : "재로그인이 필요합니다."})

    else:
        return jsonify({"result" : 0, "msg" : "재로그인이 필요합니다."})




@fp.route('/imageProcess', methods=['POST'])
def imageProcess():
    sn = request.form.get('sn')
    result = db("SELECT * FROM uploaded WHERE G_SN=%s", (sn))
    if result:
        data = []
        for r in result:
            img_path = r['path']
            e_result = reader.readtext('.'+img_path)
            es_result = convert(e_result)
            results = find_ch(es_result)
            data.append({"path" : img_path, "info" : results, "sn" : r['i_sn']})
        return jsonify({"result" : 1, "data" : data})
    else:
        return jsonify({"result" : 0, "msg" : "이미지를 다시 업로드해주세요!"})

@fp.route('/generateImage', methods=['POST'])
def generateImage():
    json_data = request.get_json()
    print(json_data)
    g_sn = json_data['g_sn']
    group = db("SELECT * FROM grouped WHERE G_SN=%s", g_sn)
    font_path = None
    if group:
        font_path = group[0]['f_path']
    jsd = json_data['data']
    for js in jsd:

        sn = js['sn']

        result = js['info']
        img_path = js['path']
        image = cv2.imread('.'+img_path)
        mask = get_mask(result, image)
        dst = cv2.inpaint(image, mask, 3, cv2.INPAINT_TELEA)
        for text, bound, new_text, _ in result:
            if new_text != "#1#2#3#4#5":
                info = get_info(bound)
                x, y = info["start"]
                w, h = info["width"], info["height"]

                try:
                    sub = Image.fromarray(dst[y:y + h, x:x + w], 'RGB')

                    colors = max(sub.getcolors(sub.size[0] * sub.size[1]))
                    subimg = get_image(h, w, new_text, colors[1], dst[y:y + h, x:x + w], font_path)
                    dst[y:y + h, x:x + w] = subimg
                except Exception as e:
                    print(str(e))
                    continue
            # 저장
        p, ext = img_path.split(".")
        path = "{}_result.{}".format(p, ext)
        cv2.imwrite('./'+path, dst)
        db("UPDATE uploaded SET R_PATH=%s WHERE I_SN=%s", (path, sn))
    return jsonify({"result" : 1, "g_sn" : g_sn})

@fp.route('/getResultImage')
def getResultImage():
    sn = request.args.get('sn')
    result = db("SELECT * FROM uploaded WHERE G_SN=%s", (sn))

    if result:
        path = ["."+r['r_path'] for r in result]
        idx = len(glob.glob("./static/files/{}/result_*.zip".format(sn)))+1
        print(idx)
        zipf = zipfile.ZipFile('./static/files/{}/result_{}.zip'.format(sn, idx), 'w', zipfile.ZIP_DEFLATED)
        for f_name in path:
            zipf.write(f_name, os.path.join(datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S"), os.path.basename(f_name)))
        zipf.close()
        return send_file(
            './static/files/{}/result_{}.zip'.format(sn, idx),
            mimetype='application/zip',
            as_attachment=True,
            attachment_filename='result.zip', cache_timeout=0
        )

@fp.route('/getTp', methods=['POST'])
def getTp():
    u_sn = session['u_sn']
    result = db("SELECT * FROM user WHERE U_SN=%s", u_sn)
    if result:
        user = result[0]
        now = datetime.datetime.strptime(getToday(), '%Y-%m-%d')
        if user['r_sn'] > 0:
            #신청중
            isRequested = 1
        elif user['u_start'] and user['u_end']:
            u_start = datetime.datetime.strptime(user['u_start'], '%Y-%m-%d')
            u_end = datetime.datetime.strptime(user['u_end'], '%Y-%m-%d')
            if (u_end-now).total_seconds() >= 0 and (now-u_start) >= 0:
                #사용중
                isRequested = 2
            else:
                #만료됨
                isRequested = -1
        else:
            #신청한적없음
            isRequested = 0
        if isRequested <= 0:
            req = db("SELECT * FROM request WHERE U_SN=%s AND R_TYPE='F'", u_sn)
            if req:
                return jsonify({'result' : 1, 'isRequested' : isRequested, 'free' : 0})
            else:
                return jsonify({'result': 1, 'isRequested': isRequested, 'free': 1})
        else:
            return jsonify({'result': 1, 'isRequested': isRequested, 'free': 0})

    else:
        return jsonify({'result' : 0})

@fp.route('/setTp', methods=['POST'])
def setTp():
    u_sn = session['u_sn']
    t_type = request.form.get('type')
    now = getToday(time=True)
    result = db("SELECT * FROM user WHERE U_SN=%s", u_sn)

    if result and result[0]['r_sn'] > 0:
        return jsonify({"result" : 0, "msg" : "이미 신청된 상태입니다."})
    else:
        if t_type == 'F':
            req = db("SELECT * FROM request WHERE U_SN=%s AND R_TYPE='F'", u_sn)
            if req:
                return jsonify({"result": 0, "msg": "이미 체험하셨습니다."})

        r_sn = db("INSERT INTO request(U_SN, R_TYPE, REGIST_DTM) VALUES (%s, %s, %s)", (u_sn, t_type, now))
        db("UPDATE user SET R_SN=%s WHERE U_SN=%s", (r_sn, u_sn))
        return jsonify({"result" : 1, "msg" : "신청되었습니다."})

@fp.route('/getArticle')
def getArticle():
    page = int(request.args.get("page"))

    result = db("SELECT a.*, u.U_ID, c.A_SN AS CNNC, 0 AS TYPE FROM article a LEFT JOIN user u ON a.U_SN=u.U_SN LEFT OUTER JOIN article c ON c.A_CNNC=a.A_SN WHERE a.A_CNNC IS NULL ORDER BY a.REGIST_DTM LIMIT %s OFFSET %s", (10, page*10))
    count = db("SELECT * FROM article WHERE A_CNNC IS NULL")

    return jsonify({"data" : result, "recordsTotal" : len(count)})

@fp.route('/insertArticle', methods=['POST'])
def insertArticle():
    if "u_sn" in session:
        u_sn = session["u_sn"]
    else:
        u_sn = 0
    a_type = request.form.get("a_type")
    if a_type is None:
        a_type = 0
    o_sn = request.form.get("o_sn")
    if o_sn is None:
        o_sn = 0
    a_title = request.form.get("a_title")
    a_content = request.form.get("a_content")
    a_cnnc = request.form.get("a_cnnc")
    if not a_cnnc:
        a_cnnc = None
    now = getToday(time=True)
    db("INSERT INTO article(U_SN, A_TYPE, O_SN, A_TITLE, A_CONTENT, A_CNNC, REGIST_DTM) VALUES (%s, %s, %s, %s, %s, %s, %s)", (u_sn, a_type, o_sn, a_title, a_content, a_cnnc, now))
    return '<script>alert("입력되었습니다.");window.opener.reload(0); close();</script>'

@fp.route('/showArticle', methods=['POST'])
def showArticle():
    isLogin = 'u_sn' in session
    if isLogin:
        u_sn = session["u_sn"]
        a_sn = request.form.get('a_sn')
        article = db("SELECT a.*, c.U_SN as U_CNNC_SN, c.A_SN AS A_CNNC_SN FROM article a LEFT JOIN article c ON a.A_CNNC=c.A_SN WHERE a.A_SN=%s", a_sn)
        if article[0]["u_sn"] == int(u_sn) or article[0]["u_cnnc_sn"] == int(u_sn):
            return jsonify({'result' : 1, 'data' : article})
        else:
            return jsonify({'result' : 0, 'msg' : "자신이 작성한 게시글만 확인할 수 있습니다."})
    else:
        return jsonify({'result' : -1, 'msg' : "로그인이 필요합니다."})

@fp.route('/getMain')
def getMain():
    detail = db("SELECT * FROM main WHERE M_TYPE=1 ORDER BY REGIST_DTM DESC LIMIT 5 OFFSET 0")
    if len(detail) > 0:
        return jsonify({"data" : detail})
    else:
        return jsonify({"data" : []})

@fp.route('/isExpired', methods=['POST'])
def isExpired():
    if 'u_sn' in session:
        u_sn = session['u_sn']
        result = db("SELECT * FROM user WHERE U_SN=%s", u_sn)
        if result:
            user = result[0]

            now = datetime.datetime.strptime(getToday(), '%Y-%m-%d')
            if user['u_start'] and user['u_end']:
                u_start = datetime.datetime.strptime(user['u_start'], '%Y-%m-%d')
                u_end = datetime.datetime.strptime(user['u_end'], '%Y-%m-%d')
                if (u_end-now).total_seconds() >= 0 and (now-u_start).total_seconds() >= 0:
                    # 사용가능
                    return jsonify({"data": 1})
                else:
                    # 만료됨
                    return jsonify({"data": -1})
            elif user['r_sn'] > 0:
                # 승인대기
                return jsonify({"data" : -2})
            else:
                # 사용권 신청하지 않음
                return jsonify({"data" : 0})

    return jsonify({"data" : -3})


@fp.route('/getAlerts')
def getAlerts():

    where = ""
    where += "AND r.R_TYPE = 'N'"
    query = "SELECT u.*, r.R_TYPE, r.REGIST_DTM as dtm FROM user u LEFT OUTER JOIN request r ON u.U_SN=r.U_SN AND r.R_SN=u.R_SN WHERE 1=1 {} ORDER BY r.REGIST_DTM DESC".format(where)
    money = db(query+" LIMIT 3 OFFSET 0")
    moneyCount = len(db(query))

    where = ""
    where += "AND r.R_TYPE = 0"
    query = "SELECT u.*, r.R_TYPE, r.REGIST_DTM as dtm FROM user u LEFT OUTER JOIN request r ON u.U_SN=r.U_SN AND r.R_SN=u.R_SN WHERE 1=1 {} ORDER BY r.REGIST_DTM DESC".format(where)
    free = db(query+" LIMIT 3 OFFSET 0")
    freeCount = len(db(query))

    return jsonify({"money" : money, "moneyCount": moneyCount, "free" : free, "freeCount" : freeCount})