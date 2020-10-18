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



fp = Blueprint('function', __name__, url_prefix='/ajax')
fp.secret_key = SECRET_KEY

db = DB(host='localhost', user='root', password=PW, db='image')
reader = easyocr.Reader(['ch_sim'])

def convert(data):
    return [(d[1], d[0]) for d in data]

def toInt(bounds):
    return [ [int(b) for b in bound] for bound in bounds]

def find_ch(results):
    return [(text, toInt(boundaries), get_translate(text)) for text, boundaries in results if len(re.findall(r'[\u4e00-\u9fff]+', text)) > 0]


def get_info(data):
    xs = []
    ys = []
    for x, y in data:
        xs.append(int(x))
        ys.append(int(y))
    return {"start": (min(xs) if min(xs) > 0 else 0, min(ys) if min(ys) > 0 else 0),
            "width": max(xs) - (min(xs) if min(xs) > 0 else 0), "height": max(ys) - (min(ys) if min(ys) > 0 else 0)}


def get_image(img_h, img_w, text, color, img):
    fontcolor = (0, 0, 0, 0)
    if (color[0] + color[1] + color[2]) // 3 < 128:
        fontcolor = (255, 255, 255, 0)

    fontpath = "./fonts/H2GTRM.TTF"

    font_size = min(img_w // (len(text) - text.count(" ") // 2), img_h)
    font = ImageFont.truetype(fontpath, font_size)
    img_pil = Image.fromarray(img)
    draw = ImageDraw.Draw(img_pil)

    st_x = (img_w - font_size * (len(text) - text.count(" ") // 2)) // 2
    st_y = (img_h - font_size) // 2

    draw.text((st_x, st_y), text, font=font, fill=fontcolor)

    img = np.array(img_pil)
    return img


def get_translate(text):
    data = {'source': 'zh-CN', 'target': 'en', 'text': text}

    headers = {"X-Naver-Client-Id": "FrFyv031pxHA6LvisJJC", "X-Naver-Client-Secret": "dkY2WOLZL3"}
    res = requests.post("https://openapi.naver.com/v1/papago/n2mt", headers=headers, data=data)
    resj = json.loads(res.text)
    temp = resj["message"]["result"]["translatedText"]

    data["text"] = temp
    data["source"] = 'en'
    data["target"] = 'ko'
    res = requests.post("https://openapi.naver.com/v1/papago/n2mt", headers=headers, data=data)
    resj = json.loads(res.text)
    last = resj["message"]["result"]["translatedText"]
    return last


def get_mask(results, img):
    black = np.zeros(img.shape, np.uint8)
    for text, bound, new_text in results:
        if new_text.strip() != '':
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
    cond = int(request.form.get('condition'))
    q = request.form.get('query')
    if cond == 1:
        col = "u.U_ID"
    elif cond == 2:
        col = "u.U_NM"
    elif cond == 3:
        col = "u.U_CP"
    elif cond == 4:
        result = db(
            "SELECT u.*, r.R_SN, IFNULL(r.R_TYPE, -1) AS R_TYPE, r.regist_dtm as dtm FROM user u LEFT OUTER JOIN request r ON u.U_SN=r.U_SN AND r.R_STTUS=0 WHERE 1")
        if len(result) > 0:
            return jsonify({"result": 1, "data": result})
        else:
            return jsonify({"result": 0})
    else:
        result = db(
            "SELECT u.*, r.R_SN, IFNULL(r.R_TYPE, -1) AS R_TYPE, r.regist_dtm as dtm FROM user u LEFT OUTER JOIN request r ON u.U_SN=r.U_SN AND r.R_STTUS=0 WHERE u.U_ID LIKE %s OR u.U_NM LIKE %s OR u.U_CP LIKE %s", ('%{}%'.format(q), '%{}%'.format(q), '%{}%'.format(q)))
        if len(result) > 0:
            return jsonify({"result": 1, "data": result})
        else:
            return jsonify({"result": 0})


    result = db("SELECT u.*, r.R_SN, IFNULL(r.R_TYPE, -1) AS R_TYPE, r.regist_dtm as dtm FROM user u LEFT OUTER JOIN request r ON u.U_SN=r.U_SN AND r.R_STTUS=0 WHERE {} LIKE %s".format(col), '%{}%'.format(q))
    if len(result) > 0:
        return jsonify({"result" : 1, "data" : result})
    else:
        return jsonify({"result" : 0})

@fp.route("/processRequest", methods=['POST'])
def processRequest():
    r_sn = request.form.get('sn')
    end = request.form.get('end')
    result = db("SELECT * FROM request WHERE R_SN=%s", r_sn)
    if result:
        u_sn = result[0]['u_sn']
        r_type = result[0]['r_type']
        if r_type == 0:
            db("UPDATE user SET U_TP=0, U_DTM=%s WHERE U_SN=%s", (end, u_sn))
        else:
            db("UPDATE user SET U_DTM=%s WHERE U_SN=%s", (u_sn))
        db("UPDATE request SET R_STTUS=1 WHERE R_SN=%s", r_sn)
        return jsonify({"result" : 1})
    else:
        return jsonify({"result" : 0, "msg" : "오류가 발생했습니다."})
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
    result = db("SELECT * FROM user WHERE U_ID=%s", (u_id))
    if result:
        return jsonify({'result': 0, 'msg': '존재하는 아이디입니다.'})
    try:
        now = getToday(time=True)
        u_sn = db("INSERT INTO user(U_ID, U_PW, U_NM, U_CP, U_DTM, REGIST_DTM) VALUES (%s, %s, %s, %s, NULL, %s)", (u_id, u_pw, u_nm, u_cp, now))
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
            if user['u_dtm']:
                limit = datetime.datetime.strptime(user['u_dtm'], '%Y-%m-%d')
                if (limit-now).total_seconds() >= 0:
                    expired = 0
                else:
                    expired = 2
            else:
                expired = 1
            if expired == 1:
                return jsonify({"result" : 0, "msg" : "사용권이 없습니다."})
            elif expired == 2:
                return jsonify({"result" : 0, "msg" : "사용권의 사용기간이 만료되었습니다."})

            else:
                u_file = request.files.get('file')

                origin = u_file.filename
                name, ext = origin.split(".")
                path_template = '/static/files/{}_{}{}.{}'.format(name,
                                                                  datetime.datetime.now().strftime("%y_%m_%d_%H_%M_%S"),
                                                                  '{}', ext)
                path = path_template.format('')
                resize_path = path_template.format('_resized')
                u_file.save('.' + path)
                image = Image.open('.' + path)
                width, height = image.size
                w = 300
                h = int(300 * height / width)
                resize_image = image.resize((w, h))
                resize_image.save('.' + resize_path)
                u_sn = session["u_sn"]
                i_sn = db("INSERT INTO uploaded(U_SN, PATH) VALUES (%s, %s)", (u_sn, path))
                # db("UPDATE ordered SET O_CONFIRM_PATH=%s WHERE O_SN=%s", (path, sn))
                return jsonify({"result": 1, "msg": "업로드되었습니다.", "sn": i_sn, "height": h})
        else:
            return jsonify({"result" : 0, "msg" : "재로그인이 필요합니다."})

    else:
        return jsonify({"result" : 0, "msg" : "재로그인이 필요합니다."})


@fp.route('/getImagePath', methods=['POST'])
def getImagePath():
    sn = request.form.get('sn')
    u_sn = session['u_sn']
    result = db("SELECT * FROM uploaded WHERE I_SN=%s AND U_SN=%s", (sn, u_sn))
    if result:
        return jsonify({"result" : 1, "data" : result[0]})
    else:
        return jsonify({"result" : 0, "msg" : "새로고침이 필요합니다."})

@fp.route('/imageProcess', methods=['POST'])
def imageProcess():
    sn = request.form.get('sn')
    u_sn = session['u_sn']
    result = db("SELECT * FROM uploaded WHERE I_SN=%s AND U_SN=%s", (sn, u_sn))
    if result:
        img_path = result[0]['path']
        e_result = reader.readtext('.'+img_path)
        es_result = convert(e_result)
        results = find_ch(es_result)
        print(results)
        return jsonify({"result" : 1, "data" : results})
    else:
        return jsonify({"result" : 0, "msg" : "이미지를 다시 업로드해주세요!"})

@fp.route('/generateImage', methods=['POST'])
def generateImage():
    json_data = request.get_json()
    print(json_data)
    sn = json_data['sn']
    result = json_data['data']
    data = db("SELECT * FROM uploaded WHERE I_SN=%s", sn)
    if data:
        img_path = data[0]['path']
    else:
        return jsonify({"result" : 0, "msg" : "처음부터 다시 시도해주세요."})
    image = cv2.imread('.'+img_path)
    mask = get_mask(result, image)
    dst = cv2.inpaint(image, mask, 3, cv2.INPAINT_TELEA)
    for text, bound, new_text in result:
        if new_text.strip() != '':
            info = get_info(bound)
            x, y = info["start"]
            w, h = info["width"], info["height"]

            try:
                sub = Image.fromarray(dst[y:y + h, x:x + w], 'RGB')

                colors = max(sub.getcolors(sub.size[0] * sub.size[1]))
                subimg = get_image(h, w, new_text, colors[1], dst[y:y + h, x:x + w])
                dst[y:y + h, x:x + w] = subimg
            except:
                continue
        # 저장
    p, ext = img_path.split(".")
    path = "{}_result.{}".format(p, ext)
    cv2.imwrite('.'+path, dst)
    u_sn = session['u_sn']
    i_sn = db("INSERT INTO uploaded(U_SN, PATH) VALUES (%s, %s)", (u_sn, path))
    return jsonify({"result" : 1, "sn" : i_sn})

@fp.route('/getResultImage')
def getResultImage():
    sn = request.args.get('sn')
    u_sn = session['u_sn']
    result = db("SELECT * FROM uploaded WHERE I_SN=%s AND U_SN=%s", (sn, u_sn))
    if result:
        file_name = result[0]['path']
    ext = file_name.split(".")[-1]
    return send_file("."+file_name,
                     mimetype='text/{}'.format(ext),
                     attachment_filename='result.{}'.format(ext),# 다운받아지는 파일 이름.
                     as_attachment=True)

@fp.route('/getTp', methods=['POST'])
def getTp():
    u_sn = session['u_sn']
    result = db("SELECT * FROM user WHERE U_SN=%s", u_sn)
    if result:
        user = result[0]
        now = datetime.datetime.strptime(getToday(), '%Y-%m-%d')
        if user['u_dtm']:
            limit = datetime.datetime.strptime(user['u_dtm'], '%Y-%m-%d')
            if (limit-now).total_seconds() >= 0:
                expired = 0
            else:
                expired = 1
        else:
            expired = 1
        return jsonify({'result' : 1, 'free' : user['u_tp'], 'non' : expired})
    else:
        return jsonify({'result' : 0})

@fp.route('/setTp', methods=['POST'])
def setTp():
    u_sn = session['u_sn']
    t_type = request.form.get('type')
    now = getToday(time=True)
    result = db("SELECT * FROM request WHERE U_SN=%s AND R_STTUS=0", u_sn)
    if result:
        return jsonify({"result" : 0, "msg" : "이미 신청된 상태입니다."})
    else:
        if int(t_type) == 0:
            users = db("SELECT * FROM user WHERE U_SN=%s", u_sn)
            if users and users[0]['u_tp'] != -1:
                return jsonify({"result": 0, "msg": "이미 체험하셨습니다."})

        db("INSERT INTO request(U_SN, R_TYPE, R_STTUS, REGIST_DTM) VALUES (%s, %s, %s, %s)", (u_sn, t_type, 0, now))
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