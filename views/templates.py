from flask import Blueprint, render_template, abort, session, redirect, request
from util import DB, loginCheck, SECRET_KEY, PW, getLoginId

bp = Blueprint('template', __name__, url_prefix='/')
bp.secret_key = SECRET_KEY

db = DB(host='localhost', user='root', password=PW, db='image')



#Index 페이지를 위한 url route
@bp.route("/")
@bp.route("/<menu_name>")
def render(menu_name=''):
    menu_list = db("SELECT * FROM menu ORDER BY MENU_ORDR")
    isLogin = loginCheck(session)
    if menu_name == '':
        u_id = getLoginId(session)
        return render_template('index.html', menu='', menuList=menu_list, isLogin=isLogin, u_id=u_id)

    isMenu = False
    for m in menu_list:
        if m['menu_name'] == menu_name:
            isMenu = True

    if isMenu:
        if isLogin:
            u_id = getLoginId(session)
            return render_template('{}.html'.format(menu_name), menu=menu_name, menuList=menu_list, isLogin=isLogin, u_id=u_id)
        else:
            return redirect('/login?menu={}'.format(menu_name))
    else:
        abort(404)

@bp.route("/login", methods=['GET', 'POST'])
def login():
    menu = request.args.get('menu')
    isLogin = loginCheck(session)
    if isLogin:
        return redirect('/')
    if menu:
        return render_template('login.html', menu=menu)
    else:
        return render_template('login.html', menu='')

@bp.route("/popup/image")
def image():
    sn = request.args.get('sn')
    isLogin = loginCheck(session)
    if isLogin:
        return render_template('popup/{}.html'.format('image'), sn=sn)
    else:
        return redirect('/login?menu={}'.format('image'))

@bp.route("/popup/ask")
def ask():
    isLogin = loginCheck(session)
    if isLogin:
        return render_template('popup/{}.html'.format('ask'))
    else:
        return redirect('/login?menu={}'.format('ask'))

@bp.route("/popup/showAsk")
def showAsk():
    isLogin = loginCheck(session)
    if not isLogin:
        return redirect('/login')
    else:
        u_sn = session["u_sn"]
        return render_template("popup/show.html")
