from flask import Blueprint, render_template, abort, session, redirect, request
from util import DB, SECRET_KEY, PW, adminLoginCheck

ap = Blueprint('admin_template', __name__, url_prefix='/admin')
ap.secret_key = SECRET_KEY

db = DB(host='localhost', user='root', password=PW, db='image')

#Index 페이지를 위한 url route
@ap.route("/")
@ap.route("/<menu_name>")
def admin_render(menu_name=''):
    menu_list = db("SELECT * FROM menu_admin ORDER BY MENU_ORDR")
    isLogin = adminLoginCheck(session)
    if menu_name == '':
        return render_template('admin/index.html', menu='', menuList=menu_list, isLogin=isLogin)

    isMenu = False
    for m in menu_list:
        if m['menu_name'] == menu_name:
            isMenu = True

    if isMenu:
        if isLogin:
            if menu_name=='request':
                u_id = request.args.get('u_id')
                type = request.args.get('type')
                if u_id:
                    return render_template('admin/{}.html'.format(menu_name), menu=menu_name, menuList=menu_list,
                                           isLogin=isLogin, u_id=u_id)
                elif type:
                    return render_template('admin/{}.html'.format(menu_name), menu=menu_name, menuList=menu_list,
                                           isLogin=isLogin, type=type)


            return render_template('admin/{}.html'.format(menu_name), menu=menu_name, menuList=menu_list, isLogin=isLogin)
        else:
            return redirect('/admin/login?menu={}'.format(menu_name))
    else:
        abort(404)

@ap.route("/login")
def login():
    menu = request.args.get('menu')
    isLogin = adminLoginCheck(session)
    if isLogin:
        return redirect('/admin')
    if menu:
        return render_template('admin/login.html', menu=menu)
    else:
        return render_template('admin/login.html', menu='')