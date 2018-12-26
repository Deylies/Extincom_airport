# encoding:utf-8
# __author__:DeyLies,WangYu
from flask import Flask, request, render_template, url_for, redirect, jsonify
from flask_login import login_user, login_required, LoginManager, current_user, logout_user
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.exceptions import HTTPException, default_exceptions
import os
import argparse
import requests

MAX_LOAD_G = 1800  # 限重 :1.8 kg
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = True
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SECRET_KEY'] = os.urandom(24)
Session(app)
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.session_protection = 'strong'
login_manager.login_view = 'login'

STATUS = {"CONFIRMED": "订单收到并在处理中",
          "SHIPPED": "订单货物已安排航班发送",
          "DELIVERED": "订单已运送完毕",
          "DELAYED": "订单因为不可抗因素推迟",
          "CANCELED": "订单被取消因为⽆法满⾜运送条件"}


# @app.errorhandler(Exception)
# def handle_error(e):
#     code = 500
#     if isinstance(e, HTTPException):
#         code = e.code
#     return jsonify(error=str(e)), code


# for ex in default_exceptions:
#     app.register_error_handler(ex, handle_error)


class User(db.Model):
    User_ID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    User_Name = db.Column(db.String, nullable=False)
    User_Passwd = db.Column(db.String, nullable=False)

    def todict(self):
        return self.__dict__

    # 下面这4个方法是flask_login需要的4个验证方式
    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return self.User_ID


class Order(db.Model):
    ID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Flights = db.Column(db.String, nullable=False)
    State = db.Column(db.String, nullable=False)
    Receive_Time = db.Column(db.Integer, nullable=False)
    User_ID = db.Column(db.Integer, nullable=False)

    def todict(self):
        return self.__dict__


class ErrorUser():
    def __init__(self):
        pass

    def todict(self):
        return self.__dict__

    # 下面这4个方法是flask_login需要的4个验证方式
    def is_authenticated(self):
        return False

    def is_active(self):
        return False

    def is_anonymous(self):
        return False

    def get_id(self):
        return 1


@login_manager.user_loader
def load_user(user_id):
    sess = db.session()
    find = sess.query(User).filter(User.User_ID == user_id).all()
    if len(find):
        return find[0]
    else:
        return ErrorUser()


@app.route("/", methods=["POST", "GET"])
def index():
    if request.method == "GET":
        msg = request.args.get('msg')
        return redirect(url_for("login", msg=msg))


@app.route("/flight", methods=["POST", "GET"])
@login_required
def flight():
    if request.method == "GET":
        inventory = requests.get("http://localhost:12345/inventory").json()
        hospitals = requests.get("http://localhost:12345/hospitals").json()
        msg = request.args.get('msg')
        return render_template("flight.html", msg=msg, inventory=inventory, hospitals=hospitals)
    elif request.method == "POST":
        hospital, flight_time_s = request.form.get("hospital").split('-')
        if hospital:
            hospital = int(hospital)
        else:
            return redirect(url_for("flight", msg="请选择医院"))
        req = {"hospital": hospital, "products": []}
        mass = 0
        flights = []
        for k, v in request.form.items():
            if k == "hospital" or int(v.split('-')[0]) == 0:
                continue
            query_id, quantity, mass_g = [i for i in map(float, k.split('-'))]
            query_num = int(v)
            if query_num > quantity:
                return redirect(url_for("flight", msg="不能超过剩余数量"))
            for _ in range(query_num):
                if mass + mass_g >= MAX_LOAD_G:
                    stats = requests.post("http://localhost:12345/flight", json=req).json()  # 起飞
                    print(stats)
                    flight_ID = stats.get('id')
                    ret = requests.post("http://localhost:12345/flight/%s/confirm" % flight_ID).json()
                    print(ret)
                    flights.append(flight_ID)
                    req = {"hospital": hospital, "products": []}  # 重新初始化订单
                    mass = 0  # 重新初始化货物重量
                req['products'].append(int(query_id))
                mass += mass_g
        if len(req['products']):
            stats = requests.post("http://localhost:12345/flight", json=req).json()
            print(req)
            print(stats)
            flight_ID = stats.get('id')
            ret = requests.post("http://localhost:12345/flight/%s/confirm" % flight_ID).json()
            print(ret)
            flights.append(flight_ID)
        if len(flights):
            user_id = current_user.get_id()
            order = Order()
            order.Flights = ",".join([str(i) for i in flights])
            order.Receive_Time = requests.get("http://localhost:12345/time").json() + int(flight_time_s)
            order.State = "CONFIRMED"
            order.User_ID = user_id
            sess = db.session()
            sess.add(order)
            sess.commit()
            sess.close()
            return redirect(url_for("query"))
        else:
            return redirect(url_for("flight", msg="产品数量不能全为0"))


@app.route("/rootquery", methods=["GET"])
@login_required
def rootquery():
    sess = db.session()
    user_id = current_user.get_id()
    user = sess.query(User).filter(User.User_ID == user_id).first()
    if not user.User_Name == 'root':
        logout_user()
        return redirect(url_for('login', msg="请重新登陆"))
    tasks = sess.query(Order).all()
    ret = []
    hospital_info = requests.get("http://localhost:12345/hospitals").json() # 获取医院信息
    for task in tasks:
        js = {"id": task.ID,
              "state": "",
              "products": [],
              "hospital": "",
              "rctime": 0,
              "bktime": 0}
        flights = task.Flights.split(',')
        new_state = task.State
        # if len(flights) > 1:
        # 多飞机逻辑
        Shipped = 0
        Delayed = 0
        Product_Num = 0
        for f in flights:
            state = requests.get("http://localhost:12345/flight/%s" % f).json()  # 查询状态
            print(state)
            new_state = state.get("state")
            js['products'] += state.get('products')
            js['hospital'] = state.get('hospital')
            cnt = len(state.get('products'))
            if state.get("state") == "SHIPPED":
                Shipped += cnt
            elif state.get("state") == "DELAYED":
                Delayed += cnt
            Product_Num += cnt
        if Shipped or Delayed:
            new_state = ""
            if Shipped:
                new_state += "%s SHIPPED;" % (str(int(Shipped / Product_Num * 100)) + "%")
            if Delayed:
                new_state += "%s DELAYED" % (str(int(Delayed / Product_Num * 100)) + "%")
            task.State = new_state
            sess.add(task)
            sess.commit()
        js['products'] = ",".join(["产品ID:%s,数量:%s"%(i,js['products'].count(i)) for i in set(js['products'])])
        js['state'] = new_state
        js['rctime'] = task.Receive_Time
        for i in hospital_info:
            if i['id'] == int(js['hospital']):
                flight_time_s = i['flight_time_s']
                break
        js['bktime'] = int(task.Receive_Time) + int(flight_time_s)
        ret.append(js)
    msg = request.args.get('msg')
    return render_template("rootquery.html", msg=msg, ret=ret)


@app.route("/query", methods=["GET"])
@login_required
def query():
    sess = db.session()
    user_id = current_user.get_id()
    user = sess.query(User).filter(User.User_ID == user_id).first()
    if not user:
        logout_user()
        return redirect(url_for('login', msg="请重新登陆"))
    tasks = sess.query(Order).filter(Order.User_ID == user_id).all()
    ret = []
    for task in tasks:
        js = {"id": task.ID,
              "state": "",
              "rctime": 0}
        flights = task.Flights.split(',')
        new_state = task.State
        if len(flights) > 1:
            # 多飞机逻辑
            Shipped = 0
            Delayed = 0
            Product_Num = 0
            for f in flights:
                state = requests.get("http://localhost:12345/flight/%s" % f).json()  # 查询状态
                print(state)
                new_state = state.get("state")
                cnt = len(state.get('products'))
                if state.get("state") == "SHIPPED":
                    Shipped += cnt
                elif state.get("state") == "DELAYED":
                    Delayed += cnt
                Product_Num += cnt
            if Shipped or Delayed:
                new_state = ""
                if Shipped:
                    new_state += "%s SHIPPED;" % (str(int(Shipped / Product_Num * 100)) + "%")
                if Delayed:
                    new_state += "%s DELAYED" % (str(int(Delayed / Product_Num * 100)) + "%")
            task.State = new_state
            sess.add(task)
            sess.commit()
        js['state'] = new_state
        now = requests.get("http://localhost:12345/time").json()
        if task.Receive_Time - now <= 300:  # 5分钟以内
            if js['state'] == "DELIVERED":
                js['rctime'] = "DELIVERED"
            else:
                js['rctime'] = "订单⻢上到达"
        else:
            js['rctime'] = task.Receive_Time - now
        ret.append(js)
    msg = request.args.get('msg')
    return render_template("query.html", msg=msg, ret=ret)


@app.route("/login", methods=["POST", "GET"])
def login():
    if request.method == "GET":
        msg = request.args.get('msg')
        return render_template("login.html", msg=msg)
    elif request.method == "POST":
        # 获取前端表单数据
        username = request.form.get("username")
        passwd = request.form.get("passwd")
        if username and passwd:  # 判断输入是否为空
            sess = db.session()
            user = sess.query(User).filter(User.User_Name == username).all()
            if len(user):
                user = user[0]
                if passwd == user.User_Passwd:  # 检查密码是否正确
                    login_user(user, remember=True)
                    if username=="root": #管理员登陆
                        return redirect(url_for("rootquery", msg="登陆成功"))
                    else:
                        return redirect(url_for("flight", msg="登陆成功"))
            else:
                return redirect(url_for("login", msg="用户不存在"))
        else:
            return redirect(url_for("login", msg="输入不能为空"))


@app.route("/regist", methods=["POST", "GET"])
def regist():
    if request.method == "GET":
        msg = request.args.get('msg')
        return render_template("regist.html", msg=msg)
    elif request.method == "POST":
        # 获取表单信息
        username = request.form.get("username")
        passwd = request.form.get("passwd")
        confirm = request.form.get("confirm")
        if username and passwd and confirm:
            if username.isalnum():  # 判断是否只有数字+英文
                if passwd == confirm:  # 判断两次密码是否相同
                    sess = db.session()
                    check = sess.query(User).filter(User.User_Name == username).all()
                    if len(check):  # 检查是否存在相同用户名
                        return redirect(url_for('regist', msg="用户已存在"))
                    else:
                        # 数据库提交用户
                        user = User()
                        user.User_Name = username
                        user.User_Passwd = passwd
                        sess.add(user)
                        sess.commit()
                        sess.close()
                        return redirect(url_for('login', msg="注册成功"))
                else:
                    return redirect(url_for('regist', msg="两次密码不一致"))
            else:
                return redirect(url_for('regist', msg="用户名只能数字和英文"))
        else:
            return redirect(url_for('regist', msg="输入信息不能为空"))
        # return render_template("regist.html")


def main():
    parser = argparse.ArgumentParser(description="Run a simulated nest environment")
    parser.add_argument('--addr', default='0.0.0.0', help="Which address to bind to")
    parser.add_argument('--port', default=6662, help="Which port to run the server on")
    parser.add_argument('--debug', default=True, help="Which port to run the server on")

    args = parser.parse_args()

    with app.app_context():
        db.create_all()
        sess = db.session()
        sess.commit()
        root = User()
        root.User_Name = "root"
        root.User_Passwd = "123"
        sess.add(root)
        sess.commit()
        sess.close()

    app.run(host=args.addr, port=args.port, debug=True)


if __name__ == '__main__':
    main()
